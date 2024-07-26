#!/usr/bin/env python3

# Copyright  ©  2020-2024 IntelliProp Inc.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import argparse
import networkx as nx
import matplotlib.pyplot as plt
import posixpath
import random
import requests
import json
import flask_fat
import socket
import os
from threading import Thread
from queue import Queue, Empty
from pathlib import Path
from uuid import UUID, uuid4
from zeroconf import IPVersion, ServiceBrowser, ServiceInfo, Zeroconf
from pdb import set_trace, post_mortem
import traceback

class FM():
    def __init__(self, info: ServiceInfo):
        self.is_subscribed = False
        self.info = info
        self.addresses = info.parsed_scoped_addresses()
        self.set_properties()
        self.bridges = []

    def update(self, info: ServiceInfo):
        self.info = info
        self.set_properties()

    def set_properties(self):
        if self.info.properties:
            self.fab_uuid = UUID(bytes=self.info.properties[b'fab_uuid'])
            self.mgr_uuid = UUID(bytes=self.info.properties[b'mgr_uuid'])
            self.pfm = bool(int(self.info.properties[b'pfm']))

    @property
    def port(self):
        return self.info.port

    @property
    def name(self):
        return self.info.name

    def __hash__(self): # Revisit: do we need this?
        return hash(self.name)


class FMServer(flask_fat.APIBaseline):
    def __init__(self, config, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.conf = config
        # self.callbacks = Callbacks() # Revisit
        self.fms = {}
        self.init_socket()
        self.pfm = None
        self.sfm = None
        self.uuid = uuid4()
        self.q = Queue()

    def get_endpoints(self, consumers, mgr_type, name):
        endpoints = []
        for con in consumers:
            try:
                endpoints.append(self.callbacks.get_endpoints(con, mgr_type)['callbacks'][name])
            except KeyError:
                print(f'consumer {con} has no subscribed {name} endpoint')
        # end for
        return endpoints

    def init_socket(self):
        # choose a random available port by setting config PORT to 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(('0.0.0.0', 0))
        self.sock.listen()
        # tell the underlying WERKZEUG server to use the socket we just created
        os.environ['WERKZEUG_SERVER_FD'] = str(self.sock.fileno())
        _, self.port = self.sock.getsockname()
        self.hostname = socket.gethostname()
        self.ip = socket.gethostbyname(self.hostname)

    def zeroconf_setup(self):
        self.zeroconf = Zeroconf(ip_version=IPVersion.V4Only) # Revisit: ip6
        services = ['_genz-fm._tcp.local.']
        self.zeroconfBrowser = ServiceBrowser(self.zeroconf, services, self)

    def endpoints_url(self, fm: 'FM', fm_endpoint=None):
        cfg = self.config
        port = self.port
        eps = cfg['ENDPOINTS']
        mainapp_eps = self.kwargs.get('endpoints', None)
        if mainapp_eps is not None:
            eps = mainapp_eps
        if fm_endpoint is None:
            fm_endpoint = self.config.get('SFM_SUBSCRIBE', 'subscribe/sfm')
        # Revisit: multiple FM addresses
        url = (f'http://{fm.addresses[0]}:{fm.port}/{fm_endpoint}' if fm is not None
               else None)

        this_hostname = self.config.get('THIS_HOSTNAME', None)
        if this_hostname is None:
            this_hostname = f'http://{self.hostname}:{port}'

        endpoints = {}
        for k, v in eps.items():
            endpoints[k] = posixpath.join(this_hostname, v)

        return (url, endpoints)

    def subscribe_mgr(self, pfm: 'FM', unsubscribe=False):
        if unsubscribe:
            if not pfm.is_subscribed: # not subscribed
                return
        else: # subscribe
            if pfm.is_subscribed: # already subscribed
                return
        fm_ep = 'subscribe/unsubscribe' if unsubscribe else None
        url, callback_endpoints = self.endpoints_url(pfm, fm_endpoint=fm_ep)
        data = {
            'callbacks' : callback_endpoints,
            'alias'     : None,
            'bridges'   : [str(self.uuid)],
            'mgr_type'  : 'genz-topo'
        }

        print(f'subscribe_mgr: url={url}, data={data}, unsubscribe={unsubscribe}') # Revisit: temp debug
        try:
            resp = requests.post(url, json=data)
        except Exception as err:
            resp = None
            print(f'subscribe_mgr(): {err}')

        is_success = resp is not None and resp.status_code < 300

        if is_success:
            pfm.is_subscribed = not unsubscribe
            print(f'--- {"Unsub" if unsubscribe else "Sub"}scribed to {url}, callbacks at {callback_endpoints}')
        else:
            print(f'---- Failed to {"Unsub" if unsubscribe else "Sub"}scribe to FM event! {url} {callback_endpoints} ---- ')
            if resp is not None:
                # Revisit: log the actual status message from the response
                print(f'subscription error reason [{resp.status_code}]: {resp.reason}')

    def update_topo(self):
        print('update_topo')
        updated = False
        draw_all = False
        if self.url is not None:
            (new_hx, new_pos, new_edge_colors, color_map,
             new_node_cnt, new_link_cnt) = get_graph(url=self.url, nn=self.nn,
                                                prev_node_cnt=self.node_cnt,
                                                prev_link_cnt=self.link_cnt,
                                                prev_pfm=self.pfm,
                                                prev_sfm=self.sfm)
            new_pfm = new_hx.graph.get('pfm', None)
            new_sfm = new_hx.graph.get('sfm', None)
            if new_pfm != self.pfm or new_sfm != self.sfm:
                print(f'FM changed: pfm:{self.pfm}->{new_pfm}, sfm:{self.sfm}->{new_sfm}')
                self.pfm = new_pfm
                self.sfm = new_sfm
                self.hx = new_hx
                self.pos = new_pos
                updated = True
                draw_all = True
            if new_edge_colors != self.edge_colors:
                self.edge_colors = new_edge_colors
                updated = True
            if new_node_cnt != self.node_cnt or new_link_cnt != self.link_cnt:
                self.node_cnt = new_node_cnt
                self.link_cnt = new_link_cnt
                self.hx = new_hx
                self.pos = new_pos
                updated = True
                draw_all = True
        else: # Revisit: should not happen
            raise ValueError('self.url is None')
        if draw_all:
            plt.clf()
            nx_draw(self.hx, self.pos, self.edge_colors, color_map)
        for edge, color in zip(self.hx.edges(data=True), self.edge_colors):
            nx.draw_networkx_edges(self.hx, self.pos,
                                   edgelist=[(edge[0],edge[1])], width=5.0,
                                   connectionstyle=f'arc3, rad={edge[2]["rad"]}',
                                   edge_color=color, node_size=args.node_size,
                                   arrows=True, arrowstyle='-')
        return updated

    def promote_sfm_to_pfm(self, sfm: 'FM'):
        self.pfm_fm = sfm
        self.sfm_fm = None
        self.url, _ = self.endpoints_url(self.pfm_fm,
                                         fm_endpoint='fabric/topology')
        # Revisit: finish this

    # zeroconf ServiceBrowser service handlers
    def add_service(self, zeroconf: Zeroconf, type: str, name: str) -> None:
        print(f'Service {name} of type {type} Added')
        info = zeroconf.get_service_info(type, name)
        print(f'Info from zeroconf.get_service_info: {info}')
        if name in self.fms:
            print(f'duplicate FM name {name}')
            return
        fm = FM(info)
        self.fms[name] = fm
        if fm.pfm:
            self.subscribe_mgr(fm)
            self.pfm_fm = fm
            self.url, _ = self.endpoints_url(self.pfm_fm,
                                             fm_endpoint='fabric/topology')
            self.q.put_nowait("new pfm")
        else: # SFM
            self.sfm_fm = fm

    def remove_service(self, zeroconf: Zeroconf, type: str, name: str) -> None:
        print(f'Service {name} of type {type} Removed')
        try:
            fm = self.fms[name]
        except KeyError:
            print(f'attempt to remove unknown FM {name}')
            return
        if fm == self.pfm_fm:
            self.pfm_fm = None
        elif fm == self.sfm_fm:
            self.sfm_fm = None
        del self.fms[name]

    def update_service(self, zeroconf: Zeroconf, type: str, name: str) -> None:
        print(f'Service {name} of type {type} Updated')
        info = zeroconf.get_service_info(type, name)
        print(f'Info from zeroconf.get_service_info: {info}')
        unknown = False
        try:
            fm = self.fms[name]
            fm.update(info)
        except KeyError:
            print(f'attempt to update unknown FM {name}')
            unknown = True
            fm = FM(info) # treat as if this was an 'add'
        if fm == self.sfm_fm and fm.pfm == True:
            self.promote_sfm_to_pfm(fm)
        # Revisit: finish this

def node_color(node, color_map):
    if node == 'PFM':
        color_map.append('orange')
    elif node == 'SFM':
        color_map.append('#df5edf') # pink
    elif node[0:2] == 'SW':
        color_map.append('#2ca02c') # green
    elif node[0:2] == 'MB':
        color_map.append('#17becf') # cyan
    elif node[0:3] == 'ZMM':
        color_map.append('#ae7adf') # purple
    elif node[0:3] == 'ACC':
        color_map.append('#efef00') # yellow
    elif node[0:4] == 'host' or node[0:3] == 'cxl' or node[0:3] == 'ali':
        color_map.append('#1f77b4') # blue
    else:
        color_map.append('#b96949') # brownish

link_colors = { 'I-Down':'red', 'I-CFG':'purple',
                'I-Up':'green', 'I-LP':'blue', 'LWR':'orange' }

def edge_color(edge, color_map):
    for k in edge.keys():
        try:
            uu = UUID(k)
        except ValueError:
            continue
        i_state = edge[k]['state']
        phy = edge[k]['phy']
        phy_status = phy['status']  # Revisit: not currently using this field
        phy_tx_lwr = phy['tx_LWR']
        phy_rx_lwr = phy['rx_LWR']
        if args.verbosity > 1:
            print(k, i_state, phy_status)
        if i_state != 'I-Up':
            color = link_colors[i_state]
            break
        elif phy_tx_lwr or phy_rx_lwr:
            color = link_colors['LWR']
            break
        else:
            color = link_colors[i_state]
            # no break
        # end if
    # end for k
    color_map.append(color)

def hyperX_pos(num_zmms, directed=None):
    pos = { 'PFM':    (-1.20,   0.15),
            'soc3':   (-1.20,  -0.05),
            'SFM':    (-1.20, -0.45),
            'soc4':   (-1.20, -0.45),
            'soc6':   (-1.20, -0.45),
            'cxl1':   (-0.5,  -0.25),
            'ali':    (-1.1,  -0.35),
            'ACC1':   (1.25,  -0.10),
            'ACC2':   (1.25,  -0.40),
            'MB0.0a': (-0.75, -0.5),
            'MB0.0b': (-0.5, -0.5),
            'MB1.0a': (-0.75,  0.0),
            'MB1.0b': (-0.5,  0.0),
            'MB0.1a': ( 0, -0.85),
            'MB0.1b': ( 0.25, -0.85),
            'MB1.1a': ( 0,  0.35),
            'MB1.1b': ( 0.25,  0.35),
            'MB2.1a': ( 0,  1.25),
            'MB2.1b': ( 0.25,  1.15),
            'MB0.2a': ( 0.75, -0.5),
            'MB0.2b': ( 1, -0.5),
            'MB1.2a': ( 0.75,  0.0),
            'MB1.2b': ( 1,  0.0),
            'MB2.2a': ( 1,  1),
            'MB2.2b': ( 1.25,  0.75),
            # Revisit: extra "generic" components in case not in _mapping
            'SW0':    ( 0,    -0.25),
            'ZMM0':   ( 1,    -0.25),
            'host0':  ( 0,    -0.00),
            'ACC0':   ( 1.20, -0.6),
           }
    graph = nx.Graph(directed) # convert to non-directed
    zmm_x = -1.35
    extra = 0.1
    gap = zmm_x - extra
    half = num_zmms // 2
    for z in range(num_zmms):
        if directed is None:
            zmm = f'ZMM{z}'
        else:
            row = z // half
            col = ((z // 4) % 3)
            ab = 'a' if (z % 4) in (0, 1) else 'b'
            mb = f'MB{row}.{col}{ab}'
            try:
                mb_zmms = [n for n in filter(lambda n: n[0:3] == 'ZMM',
                                             graph.neighbors(mb))]
                zmm = mb_zmms[z % 2]
            except nx.exception.NetworkXError:
                zmm = 'None'
            except IndexError:
                if len(mb_zmms) == 0:
                    zmm = 'None'
                else:
                    partner = mb_zmms[0]
                    partner_zmms = [n for n in filter(lambda n: n[0:3] == 'ZMM',
                                                      graph.neighbors(partner))]
                    if len(partner_zmms) == 1:
                        zmm = partner_zmms[0]
                    else:
                        zmm = 'None'
        if z % 4 == 0:
            gap += extra
        if z < half: # ZMMs 0 - half-1
            pos[zmm] = ((0.25*(z)) + gap, -1.25)
        else: # ZMMs half - num_zmms-1
            if z == half:
                gap = zmm_x
            pos[zmm] = ((0.25*(z-half)) + gap, 0.75)
    # end for
    return pos


def build_hyperX_graph():
    hx = nx.MultiDiGraph() # Revisit: "Di" required to make arcs work
    host_edges = [('PFM',   'SFM'),    ('PFM',   'MB1.0a'),
                  ('SFM',   'PFM'),    ('SFM',   'MB0.0a'),
                  ('cxl1',  'MB1.1a'), ('cxl1',  'MB0.1a')]
    hx.add_edges_from(host_edges, rad=0)
    sw_edges = [('MB0.0a', 'MB0.0b'), # cross hemisphere
                ('MB0.0a', 'MB1.0a'), # column
                ('MB0.0b', 'MB0.1a'), ('MB0.0b', 'MB0.2a'), # row
                ('MB1.0a', 'MB1.0b'), # cross hemisphere
                ('MB1.0a', 'MB0.0a'), # column
                ('MB1.0b', 'MB1.1a'), ('MB1.0b', 'MB1.2a'), # row
                ('MB0.1a', 'MB0.1b'), # cross hemisphere
                ('MB0.1b', 'MB1.1b'), # column
                ('MB0.1a', 'MB0.0b'), ('MB0.1b', 'MB0.2b'), # row
                ('MB1.1a', 'MB1.1b'), # cross hemisphere
                ('MB1.1b', 'MB0.1b'), # column
                ('MB1.1a', 'MB1.0b'), ('MB1.1b', 'MB1.2b'), # row
                ('MB0.2a', 'MB0.2b'), # cross hemisphere
                ('MB0.2a', 'MB1.2a'), # column
                ('MB0.2a', 'MB0.0b'), ('MB0.2b', 'MB0.1b'), # row
                ('MB1.2a', 'MB1.2b'), # cross hemisphere
                ('MB1.2a', 'MB0.2a'), # column
                ('MB1.2a', 'MB1.0b'), ('MB1.2b', 'MB1.1b'),
                ]
    hx.add_edges_from(sw_edges, rad=0)
    num_zmms = 24
    half = num_zmms // 2
    zmms = []
    for z in range(num_zmms):
        row = z // half
        col = ((z // 4) % 3)
        ab = 'a' if (z % 4) in (0, 1) else 'b'
        zmms.append((f'ZMM{z}', f'MB{row}.{col}{ab}'))
        if z % 2 == 0:  # ZMM backplane links
            zmms.append((f'ZMM{z}', f'ZMM{z+1}'))
    hx.add_edges_from(zmms, rad=0)
    color_map = []
    for node in hx:
        node_color(node, color_map)
    if args.pos:
        pos = hyperX_pos(num_zmms)
    else:
        pos = nx.drawing.layout.spring_layout(hx, k=1.0)
    spt = nx.minimum_spanning_tree(hx.to_undirected()) # Revisit
    edge_colors = []
    for e in hx.edges:
        if e in spt.edges: # Revisit
            edge_colors.append('green') # link is in spanning tree
        else:
            edge_colors.append('orange') # not in spanning tree
    return (hx, pos, edge_colors, color_map)

def update_links(hx, pos, edge_colors, url=None, nn=None, node_cnt=0, link_cnt=0):
    updated = False
    draw_all = False
    if url is not None:
        (new_hx, new_pos, new_edge_colors, color_map,
         new_node_cnt, new_link_cnt) = get_graph(url=url, nn=nn,
                                                 prev_node_cnt=node_cnt,
                                                 prev_link_cnt=link_cnt)
        if new_edge_colors != edge_colors:
            edge_colors = new_edge_colors
            updated = True
        if new_node_cnt != node_cnt or new_link_cnt != link_cnt:
            node_cnt = new_node_cnt
            link_cnt = new_link_cnt
            hx = new_hx
            pos = new_pos
            updated = True
            draw_all = True
    else:
        nlinks = len(edge_colors)
        lprob = 1.0 # probability of changing a link state
        aprob = 0.1 # probablility of all links returning to 'black'
        r = random.random()
        if r < aprob:
            for i in range(0, nlinks):
                edge_colors[i] = 'black'
        elif r > lprob:
            return False
        r = random.randrange(0, nlinks)
        edge_colors[r] = 'red' if edge_colors[r] == 'black' else 'black'
        updated = True
    # end if url
    if draw_all:
        plt.clf()
        nx_draw(hx, pos, edge_colors, color_map)
    else:
        nx.draw_networkx_edges(hx, pos, arrows=True, arrowstyle='-',
                               edge_color=edge_colors,
                               node_size=args.node_size, width=5.0)
    return (updated, node_cnt, link_cnt)

class NodeName():
    cclass_map = { 2: 'ZMM', 5: 'SW', 8: 'ACC', 20: 'host', 21: 'host' }

    def __init__(self):
        self.index = {}
        self.index['host'] = 0
        self.index['ZMM'] = 0
        self.index['SW'] = 0
        self.index['ACC'] = 0
        self._mapping = {
            # California soc1/2 fabric
            'e3331770-6648-4def-8100-404d844298d3:0x013a4a851c81a185': 'soc1',
            'e3331770-6648-4def-8100-404d844298d3:0x013a4a862d106045': 'soc2',
            '859be62c-b435-49fe-bf18-c2ac4a50f9c4:0x013a25e54c31c285': 'ZMM0',
            '859be62c-b435-49fe-bf18-c2ac4a50f9c4:0x013a25e54c31e285': 'ZMM1',
            '859be62c-b435-49fe-bf18-c2ac4a50f9c5:0x014dc70934a162c5': 'ZMM2',
            # Colorado soc3/4/cxl1 fabric
            'e3331770-6648-4def-8100-404d844298d3:0x013a4a851c810045': 'soc3',
            'e3331770-6648-4def-8100-404d844298d3:0x013a4a851d408245': 'soc4',
            'e3331770-6648-4def-8100-404d844298d3:0x013a4a851c8141c5': 'soc6',
            # Revisit: cxl1 (sphinx) CUUID is invalid
            '00000000-0070-6f72-5069-6c6c65746e49:0x01161a603c80a385': 'cxl1',
            '00000000-0070-6f72-5069-6c6c65746e49:0x01167bc814210305': 'ali',
            '009b4d92-cb3c-46cf-93e2-adcd9b54063a:0x1167bc73c3045050': 'ACC1',
            '009b4d92-cb3c-46cf-93e2-adcd9b54063a:0x1161a603c80a3c50': 'ACC2',
            'dce432d5-9874-4d4e-af63-5163c4deb354:0x139b2a604b0c1450': 'MB0.0a',
            'dce432d5-9874-4d4e-af63-5163c4deb354:0x139b2a604b0c1451': 'MB0.0b',
            'dce432d5-9874-4d4e-af63-5163c4deb354:0x13b83c12d10c1850': 'MB0.1a',
            'dce432d5-9874-4d4e-af63-5163c4deb354:0x13b83c12d10c1851': 'MB0.1b',
            'dce432d5-9874-4d4e-af63-5163c4deb354:0x13adea04c5043050': 'MB0.2a',
            'dce432d5-9874-4d4e-af63-5163c4deb354:0x13adea04c5043051': 'MB0.2b',
            'dce432d5-9874-4d4e-af63-5163c4deb354:0x15060482c7082050': 'MB1.0a',
            'dce432d5-9874-4d4e-af63-5163c4deb354:0x15060482c7082051': 'MB1.0b',
            'dce432d5-9874-4d4e-af63-5163c4deb354:0x139b2a604b0c3450': 'MB1.1a',
            'dce432d5-9874-4d4e-af63-5163c4deb354:0x139b2a604b0c3451': 'MB1.1b',
            'dce432d5-9874-4d4e-af63-5163c4deb354:0x139b2a604b002850': 'MB1.2a',
            'dce432d5-9874-4d4e-af63-5163c4deb354:0x139b2a604b002851': 'MB1.2b',
            '859be62c-b435-49fe-bf18-c2ac4a50f9c4:0x013a326834e140c5': 'ZMM3',
            '859be62c-b435-49fe-bf18-c2ac4a50f9c5:0x014be7a114304305': 'ZMM4',
            '859be62c-b435-49fe-bf18-c2ac4a50f9c5:0x014be7a115714085': 'ZMM5',
            '859be62c-b435-49fe-bf18-c2ac4a50f9c5:0x014be7a11580e205': 'ZMM6',
            '859be62c-b435-49fe-bf18-c2ac4a50f9c5:0x014be7a11581c0c5': 'ZMM7',
            '859be62c-b435-49fe-bf18-c2ac4a50f9c5:0x014be7a114504085': 'ZMM8',
            '859be62c-b435-49fe-bf18-c2ac4a50f9c5:0x014be7a11431c0c5': 'ZMM9',
            '859be62c-b435-49fe-bf18-c2ac4a50f9c5:0x014be7a11450a385': 'ZMM10',
            '859be62c-b435-49fe-bf18-c2ac4a50f9c5:0x014be7a11431e285': 'ZMM11',
            '859be62c-b435-49fe-bf18-c2ac4a50f9c4:0x013a25e54c61e2c5': 'ZMM12',
            '859be62c-b435-49fe-bf18-c2ac4a50f9c5:0x014be7a115004085': 'ZMM13',
            '859be62c-b435-49fe-bf18-c2ac4a50f9c4:0x013a25e54c61e285': 'ZMM14',
            '859be62c-b435-49fe-bf18-c2ac4a50f9c4:0x0139e762341141c5': 'ZMM15',
            '859be62c-b435-49fe-bf18-c2ac4a50f9c5:0x015de1673c8081c5': 'ZMM16',
            '859be62c-b435-49fe-bf18-c2ac4a50f9c5:0x015dd3693571c185': 'ZMM17',
            '859be62c-b435-49fe-bf18-c2ac4a50f9c5:0x015dd3681c108245': 'ZMM18',
            '859be62c-b435-49fe-bf18-c2ac4a50f9c5:0x015dd3693570c345': 'ZMM19',
            '859be62c-b435-49fe-bf18-c2ac4a50f9c5:0x015dd3693570a305': 'ZMM20',
            '859be62c-b435-49fe-bf18-c2ac4a50f9c4:0x0139f6640c21e105': 'ZMM21',
            '859be62c-b435-49fe-bf18-c2ac4a50f9c5:0x015dd36845308085': 'ZMM22',
            '859be62c-b435-49fe-bf18-c2ac4a50f9c5:0x015dd3693570a2c5': 'ZMM23',
            '859be62c-b435-49fe-bf18-c2ac4a50f9c5:0x015dd3693571a185': 'ZMM24',
            '859be62c-b435-49fe-bf18-c2ac4a50f9c5:0x014be7a114504305': 'ZMM25',
            '859be62c-b435-49fe-bf18-c2ac4a50f9c4:0x013a25e54c612245': 'ZMM26',
        }

    def mapping(self, cuuid_serial: str, pfm: str, sfm: str) -> str:
        # special cases for 'PFM' and 'SFM'
        if cuuid_serial == pfm and pfm is not None:
            return 'PFM'
        if cuuid_serial == sfm and sfm is not None:
            return 'SFM'
        return self._mapping[cuuid_serial]

    def next_name(self, cuuid_serial: str, type:str ) -> str:
        while True:
            try:
                name = type + f'{self.index[type]}'
            except KeyError:
                self.index[type] = 0
                name = type + '0'
            self.index[type] += 1
            if name not in self._mapping.values():
                self._mapping[cuuid_serial] = name
                return name
        
    def name(self, node, pfm: str, sfm: str) -> str:
        cclass = node['cclass']
        type = NodeName.cclass_map[cclass]
        try:
            name = self.mapping(node['cuuid_serial'], pfm, sfm)
        except KeyError:
            name = self.next_name(node['cuuid_serial'], type)
        return name

def get_graph(url=None, file=None, update_pos=False, nn=None,
              update_color_map=False, prev_node_cnt=0, prev_link_cnt=0,
              prev_pfm=None, prev_sfm=None):
    if nn is None:
        nn = NodeName()
    if url is not None:
        if args.verbosity > 0:
            print('getting {}'.format(url))
        r = requests.get(url=url)
        data = r.json()
    elif file is not None:
        with open(file, 'r') as f:
            data = json.load(f)
    pfm = data['graph'].get('pfm', None)
    sfm = data['graph'].get('sfm', None)
    # save current node id as cuuid_serial and replace with friendly node name
    for node in data['nodes']:
        node['cuuid_serial'] = node['id']
        name = nn.name(node, pfm, sfm)
        node['id'] = name
    # fixup links source/target as well
    for e in data['links']:
        e['source'] = nn.mapping(e['source'], pfm, sfm)
        e['target'] = nn.mapping(e['target'], pfm, sfm)
        e['rad'] = 0 if e['key'] == 0 else (e['key'] * 0.1)
    data['directed'] = True # Revisit: arcs only work on MultiDiGraph
    hx = nx.node_link_graph(data)
    node_cnt = hx.number_of_nodes()
    link_cnt = hx.number_of_edges()
    if node_cnt != prev_node_cnt or link_cnt != prev_link_cnt:
        update_pos = True
    if prev_pfm != pfm or prev_sfm != sfm:
        update_color_map = True
        update_pos = True # pos dict uses node name as key
    color_map = []
    if update_pos or update_color_map:
        for node in hx.nodes(data=True):
            node_color(node[0], color_map)
            if args.verbosity > 1:
                print('{} ({}): {}'.format(node[0], node[1]['cuuid_serial'],
                                           node[1]['cclass']))
    if update_pos:
        if args.pos:
            pos = hyperX_pos(24, directed=hx) # Revisit: num_zmms
        else:
            pos = nx.drawing.layout.spring_layout(hx, k=1.0, seed=args.seed)
    else:
        pos = None
    edge_colors = []
    for e in hx.edges(data=True):
        edge_color(e[2], edge_colors)
        if args.verbosity > 1:
            print(e[2], edge_colors[-1])
    return (hx, pos, edge_colors, color_map, node_cnt, link_cnt)

def nx_draw(hx, pos, edge_colors, color_map):
    # draw nodes & edges
    nx.draw(hx, with_labels=True, node_size=args.node_size, node_shape='o',
            pos=pos, edge_color=edge_colors, arrowstyle='-',
            node_color=color_map, font_size=args.font_size, font_weight='bold',
            width=5.0)
    if not args.gcids:
        return
    gcid_delta_y = -0.04
    gcid_pos = {}
    for node, tup in pos.items():
        gcid_pos[node] = (tup[0], tup[1] + gcid_delta_y)
    gcid_labels = {}
    node_attrs = nx.get_node_attributes(hx, 'gcids')
    for node, attr in node_attrs.items():
        gcid_labels[node] = attr[0][5:]  # Revisit: keep SID
    # add gcid labels to nodes
    nx.draw_networkx_labels(hx, gcid_pos, labels=gcid_labels,
                            font_size=args.font_size-2)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--file', default=None,
                        help='fetch topology from this file')
    parser.add_argument('-k', '--keyboard', action='store_true',
                        help='break to interactive keyboard at certain points')
    parser.add_argument('-l', '--loop', action='store_true',
                        help='update graph in loop')
    parser.add_argument('-i', '--interval', type=float, default=1.0,
                        help='update interval')
    parser.add_argument('-n', '--node-size', type=int, default=4150,
                        help='node size (default 4150)')
    parser.add_argument('-s', '--subscribe', action='store_true',
                        help='subscribe to PFM')
    parser.add_argument('-F', '--font-size', type=int, default=16,
                        help='font size (default 16)')
    parser.add_argument('-P', '--post_mortem', action='store_true',
                        help='enter debugger on uncaught exception')
    parser.add_argument('-p', '--pos', action='store_true',
                        help='use predefined node positions')
    parser.add_argument('-S', '--seed', type=int, default=1,
                        help='random seed for layout')
    parser.add_argument('-u', '--url', default=None,
                        help='fetch topology from this url')
    parser.add_argument('-v', '--verbosity', action='count', default=0,
                        help='increase output verbosity')
    parser.add_argument('--gcids', action=argparse.BooleanOptionalAction,
                        default=True,
                        help="include/don't include GCID in node label")
    global args
    args = parser.parse_args()
    if args.keyboard:
        set_trace()
    if args.url:
        upath = Path(args.url)
        win_name = upath.parts[1]
    elif args.file:
        fpath = Path(args.file)
        slen = len(fpath.suffix)
        win_name = fpath.name[:-slen] if slen > 0 else fpath.name
    else:
        win_name = 'hyperX-2x3'
    nn = NodeName()
    if args.url is not None or args.file is not None:
        try:
            hx, pos, edge_colors, color_map, node_cnt, link_cnt = get_graph(
                args.url, args.file, nn=nn, update_pos=True)
        except Exception as e:
            if args.url is not None:
                print('Cannot connect to zephyr at {}, {}'.format(args.url, e))
            else: # args.file
                print('Cannot open {}, {}'.format(args.file, e))
            return
    else:
        hx, pos, edge_colors, color_map = build_hyperX_graph()
    if args.keyboard:
        set_trace()
    nx_draw(hx, pos, edge_colors, color_map)
    for edge, color in zip(hx.edges(data=True), edge_colors):
        nx.draw_networkx_edges(hx, pos, edgelist=[(edge[0],edge[1])], width=5.0,
                               connectionstyle=f'arc3, rad={edge[2]["rad"]}',
                               edge_color=color, node_size=args.node_size,
                               arrows=True, arrowstyle='-')
    #edge_labels = {}
    #for n1, n2, data in hx.edges(data=True):
    #    uu = hx.nodes[n1]['instance_uuid']
    #    edge_labels[(n1, n2)] = data[uu]['num'][9:]
    #nx.draw_networkx_edge_labels(hx, pos, edge_labels=edge_labels,
    #                             label_pos=0.3, font_color='red')
    if args.keyboard:
        set_trace()
    man = plt.get_current_fig_manager()
    # Revisit: this probably only works for the Tk backend
    man.resize(1800, 1350)
    man.set_window_title(win_name)
    if args.subscribe:
        print('args.subscribe')
        plt.ion()
        mainapp = FMServer(None, 'genz-topo')
        mainapp.url = args.url
        mainapp.nn = nn
        mainapp.hx = hx
        mainapp.pos = pos
        mainapp.edge_colors = edge_colors
        mainapp.color_map = color_map
        mainapp.node_cnt = node_cnt
        mainapp.link_cnt = link_cnt
        mainapp.pfm = mainapp.hx.graph.get('pfm', None)
        mainapp.sfm = mainapp.hx.graph.get('sfm', None)
        plt.show()
        mainapp.zeroconf_setup()
        thread = Thread(target=mainapp.run, daemon=True)
        thread.start()
        while True:
            try:
                plt.pause(args.interval)
            except Empty:
                pass
            except KeyboardInterrupt:
                break
            try:
                item = mainapp.q.get_nowait()
                print(f'got q item: {item}')
                if 'graph' in item:
                    graph = item['graph']
                    if 'pfm' in graph and graph['pfm'] is None:
                        continue
                updated = mainapp.update_topo()
                if updated:
                    plt.draw()
                mainapp.q.task_done()
            except Empty:
                pass
            except KeyboardInterrupt:
                break
        mainapp.subscribe_mgr(mainapp.pfm_fm, unsubscribe=True)
        mainapp.zeroconf.close()
    elif args.loop:
        n = hx.number_of_nodes()
        l = hx.number_of_edges()
        plt.ion()
        while True:
            try:
                new_state, n, l = update_links(hx, pos, edge_colors, url=args.url,
                                           nn=nn, node_cnt=n, link_cnt=l)
            except Exception as e:
                print('Lost connection to zephyr at {}, {}'.format(args.url, e))
                return
            if new_state:
                if args.verbosity > 0:
                    print('redrawing')
                plt.draw()
            try:
                plt.pause(args.interval)
            except Exception as e:
                return
        # end while
    else:
        if args.keyboard:
            set_trace()
        try:
            plt.show()
        except KeyboardInterrupt:
            print('exit on keyboard interrupt')
    # end if

if __name__ == '__main__':
    try:
        main()
    except Exception as post_err:
        if args.post_mortem:
            traceback.print_exc()
            post_mortem()
        else:
            raise
