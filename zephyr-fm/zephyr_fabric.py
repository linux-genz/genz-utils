#!/usr/bin/env python3

# Copyright  ©  2020-2021 IntelliProp Inc.
# Copyright (c) 2020 Hewlett Packard Enterprise Development LP
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

import ctypes
import json
from typing import List, Tuple
from genz.genz_common import GCID, CState, IState, RKey, PHYOpStatus, ErrSeverity
import random
from pathlib import Path
from pdb import set_trace
import networkx as nx
from uuid import UUID, uuid4
import zephyr_conf
from zephyr_conf import log, INVALID_GCID
from zephyr_iface import Interface
from zephyr_comp import (Component, LocalBridge, component_num, get_cuuid,
                         get_cclass, get_gcid, get_serial)
from zephyr_route import RouteElement, Routes, Route
from zephyr_res import Resources

TEMP_SUBNET = 0xffff  # where we put uninitialized local bridges
randgen = random.SystemRandom() # crypto secure random numbers from os.urandom
fabs = Path('/sys/bus/genz/fabrics')

# Decorator func to register with dispatcher
# from https://stackoverflow.com/questions/4273998/dynamically-calling-nested-functions-based-on-arguments
def register(dispatcher, *names):
    def dec(f):
        m_name = f.__name__
        for name in names:
            dispatcher[name] = m_name
        return f
    return dec

class Fabric(nx.MultiGraph):
    events = {} # UEP events dispatch dict

    def link_weight(fr, to, edge_dict):
        fr_iface = edge_dict[str(fr.uuid)]
        to_iface = edge_dict[str(to.uuid)]
        # return None for unusable links - DR interfaces are always usable
        usable = ((fr.dr is not None or fr_iface.usable) and
                  (to.dr is not None or to_iface.usable))
        # Revisit: consider bandwidth, latency, LWR
        return 1 if usable else None

    def __init__(self, nl, map, path, fab_uuid=None, grand_plan=None,
                 random_cids=False, accept_cids=False, conf=None,
                 mgr_uuid=None, verbosity=0):
        self.nl = nl
        self.map = map
        self.path = path
        self.fabnum = component_num(path)
        self.fab_uuid = fab_uuid
        self.mgr_uuid = uuid4() if mgr_uuid is None else mgr_uuid
        self.random_cids = random_cids
        self.accept_cids = accept_cids
        self.conf = conf
        self.verbosity = verbosity
        self.bridges = []      # indexed by bridge number
        self.components = {}   # key: comp.uuid
        self.cuuid_serial = {} # key: cuuid:serial
        self.comp_gcids = {}   # key: comp.gcid
        self.assigned_gcids = []
        self.refill_gcids = True
        self.nonce_list = [ 0 ]
        self.routes = Routes(fab_uuid=fab_uuid)
        self.resources = Resources(self)
        super().__init__(fab_uuid=self.fab_uuid, mgr_uuids=[self.mgr_uuid])
        log.info('fabric: {}, num={}, fab_uuid={}, mgr_uuid={}'.format(
            path, self.fabnum, self.fab_uuid, self.mgr_uuid))

    def assign_gcid(self, comp, ssdt_sz=4096, proposed_gcid=None):
        # Revisit: subnets
        # Revisit: CID conficts between accepted & assigned are possible
        random_cids = self.random_cids
        if self.refill_gcids:
            self.avail_gcids = (random.sample(range(1, ssdt_sz), ssdt_sz-1)
                                if random_cids else list(range(1, ssdt_sz)))
            self.refill_gcids = False
        if proposed_gcid is not None:
            try:
                self.avail_gcids.remove(proposed_gcid.cid)
                comp.gcid = proposed_gcid
            except ValueError:
                comp.gcid = None
        else:
            try:
                cid = self.avail_gcids.pop(0)
                comp.gcid = GCID(cid=cid)
            except IndexError:
                comp.gcid = None
        if comp.gcid is not None:
            self.assigned_gcids.append(comp.gcid)
            self.nodes[comp]['gcids'] = [ comp.gcid ]
        return comp.gcid

    def add_comp(self, comp):
        self.cuuid_serial[comp.cuuid_serial] = comp
        self.comp_gcids[comp.gcid] = comp
        self.update_comp(comp)

    def update_comp(self, comp):
        self.nodes[comp]['fru_uuid'] = comp.fru_uuid
        self.nodes[comp]['max_data'] = comp.max_data
        self.nodes[comp]['max_iface'] = comp.max_iface
        self.nodes[comp]['rsp_page_grid_ps'] = comp.rsp_page_grid_ps
        comp.update_cstate()
        self.nodes[comp]['cstate'] = str(comp.cstate) # Revisit: to_json() doesn't work

    def generate_nonce(self):
        while True:
            r = randgen.getrandbits(64)
            if not r in self.nonce_list:
                self.nonce_list.append(r)
                return r

    def fab_init(self):
        br_paths = self.path.glob('bridge*')
        # Revisit: deal with multiple bridges that may or may not be on same fabric
        for br_path in br_paths:
            cuuid = get_cuuid(br_path)
            serial = get_serial(br_path)
            cuuid_serial = str(cuuid) + ':' + serial
            cur_gcid = get_gcid(br_path)
            brnum = component_num(br_path)
            cclass = int(get_cclass(br_path))
            tmp_gcid = cur_gcid if cur_gcid.sid == TEMP_SUBNET else INVALID_GCID
            br = LocalBridge(cclass, self, self.map, br_path, self.mgr_uuid,
                             local_br=True, brnum=brnum, dr=None,
                             tmp_gcid=tmp_gcid, netlink=self.nl,
                             verbosity=self.verbosity)
            gcid = self.assign_gcid(br, ssdt_sz=br.ssdt_size(haveCore=False)[0])
            self.set_pfm(br)
            log.info('{}:{} bridge{} {}'.format(self.fabnum, gcid, brnum, cuuid_serial))
            br.comp_init(self.pfm)
            self.bridges.append(br)
            br.explore_interfaces(self.pfm)
        # end for br_path

    def set_pfm(self, pfm):
        self.pfm = pfm
        self.graph['pfm'] = pfm

    def all_shortest_paths(self, fr: Component, to: Component,
                           cutoff_factor: float = 3.0,
                           min_paths: int = 2,
                           max_paths: int = None) -> List[List[Component]]:
        g = nx.Graph(self)  # Revisit: don't re-create g on every call
        all = nx.shortest_simple_paths(g, fr, to, weight=Fabric.link_weight)
        path_cnt = 1
        for path in all:
            if path_cnt == 1:
                min_len = len(path) - 1
                max_len = int(min_len * cutoff_factor)
            if (((len(path) - 1) <= max_len or path_cnt < min_paths) and
                (max_paths is None or path_cnt <= max_paths)):
                yield path
                path_cnt += 1
            else:
                break
        # end for

    def route_entries_avail(self, rt: Route) -> bool:
        avail = True
        fr = rt.fr
        to = rt.to
        cid = to.gcid.cid
        for elem in rt:
            if elem.rit_only:
                pass
            elif elem.ingress_iface is None: # SSDT
                found = None
                free = None
                infos = elem.comp.route_info[cid]
                row = fr.ssdt[cid]
                for i in range(len(row)):
                    if row[i].V == 1 and row[i].EI == elem.egress_iface.num:
                        found = i
                        break
                    elif row[i].V == 0 and free is None:
                        free = i
                # end for
                if found is None and free is None:
                    return False
                elif found is not None: # use existing matching entry
                    elem.rt_num = found
                else: # new entry
                    elem.rt_num = free
            else: # LPRT
                found = None
                free = None
                elem.ingress_iface.lprt_read()
                infos = elem.ingress_iface.route_info[cid]
                row = elem.ingress_iface.lprt[cid]
                for i in range(len(row)):
                    if row[i].V == 1 and row[i].EI == elem.egress_iface.num:
                        found = i
                        break
                    elif row[i].V == 0 and free is None:
                        free = i
                # end for
                if found is None and free is None:
                    return False
                elif found is not None: # use existing matching entry
                    elem.rt_num = found
                else: # new entry
                    elem.rt_num = free
            # end if
        # end for
        return avail

    def route_info_update(self, rt: Route, add: bool):
        fr = rt.fr
        to = rt.to
        cid = to.gcid.cid
        for elem in rt:
            if elem.rit_only:
                continue # No route info to update
            elif elem.ingress_iface is None: # SSDT
                info = elem.comp.route_info[cid][elem.rt_num]
            else: # LPRT
                info = elem.ingress_iface.route_info[cid][elem.rt_num]
            if add:
                info.add_route(rt)
            else:
                info.remove_route(rt)
        # end for

    def find_routes(self, fr: Component, to: Component,
                    cutoff_factor: float = 3.0,
                    min_paths: int = 2,
                    max_routes: int = None) -> List[Route]:
        def nested_loop(paths, max_routes):
            # inner function to avoid the need for a multi-loop break
            # which python doesn't have
            rts = []
            for path in paths: # in order, shortest to longest
                if max_routes is not None and len(rts) >= max_routes:
                    return rts
                rt = Route(path)
                if self.route_entries_avail(rt):
                    self.route_info_update(rt, True)
                    rts.append(rt)
                # MultiGraph routes
                for mg_rt in rt.multigraph_routes():
                    if max_routes is not None and len(rts) >= max_routes:
                        return rts
                    if self.route_entries_avail(mg_rt):
                        self.route_info_update(mg_rt, True)
                        rts.append(mg_rt)
                # end for mg_rt
            # end for rt
            return rts

        paths = self.all_shortest_paths(fr, to, cutoff_factor=cutoff_factor,
                                        min_paths=min_paths,
                                        max_paths=max_routes)
        return nested_loop(paths, max_routes)

    def write_route(self, route: Route, write_ssdt=True, enable=True):
        # When enabling a route, write entries in reverse order so
        # that live updates to routing never enable a route entry
        # before its "downstream" entries. When disabling a route,
        # start at the front, for the same reason.
        rt_iter = reversed(route) if enable else iter(route)
        for rt in rt_iter:
            if rt.ingress_iface is not None:
                # switch: add to's GCID to rt's LPRT
                rt.set_lprt(route.to, valid=enable)
            elif write_ssdt:
                # add to's GCID to rt's SSDT
                rt.set_ssdt(route.to, valid=enable)

    def setup_routing(self, fr: Component, to: Component,
                      write_ssdt=True, routes=None) -> List[Route]:
        if routes is None:
            routes = self.find_routes(fr, to,
                                      max_routes=zephyr_conf.args.max_routes)
        try:
            cur_rts = self.routes.get_routes(fr, to)
        except KeyError:
            cur_rts = []
        new_rts = []
        for route in routes:
            if route in cur_rts:
                log.debug('skipping existing route {}'.format(route))
            else:
                log.info('adding route from {} to {} via {}'.format(
                    fr, to, route))
                self.write_route(route, write_ssdt)
                self.routes.add(fr, to, route)
                new_rts.append(route)
        return new_rts

    def setup_bidirectional_routing(self, fr: Component, to: Component,
                                    write_to_ssdt=True, routes=None) -> Tuple[List[Route], List[Route]]:
        if fr is to: # Revisit: loopback
            return None
        to_routes = self.setup_routing(fr, to, routes=routes) # always write fr ssdt
        to_inverted = [rt.invert(self) for rt in to_routes]
        to_filtered = filter(lambda rt: rt is not None, to_inverted)
        fr_routes = (self.setup_routing(to, fr, write_ssdt=write_to_ssdt,
                                        routes=to_filtered)
                     if len(to_routes) > 0 else [])
        return (to_routes, fr_routes)

    def teardown_routing(self, fr: Component, to: Component,
                         route: Route) -> None:
        # Revisit: tear down HW route from "fr" to "to",
        # Revisit: but some of the components may not be reachable from PFM
        # remove route from routes list
        self.routes.remove(fr, to, route)

    def recompute_routes(self, iface1, iface2):
        # Revisit: this is O(n**2) during crawl-out, worse later
        # Revisit: can we make use of iface1/2 to do better?
        for fr, to in self.routes.fr_to.keys():
            self.setup_routing(fr, to)

    def has_link(self, fr_iface: Interface, to_iface: Interface) -> bool:
        fr = fr_iface.comp
        to = to_iface.comp
        num_edges = self.number_of_edges(fr, to)
        if num_edges == 0:
            return False
        edge_data = self.get_edge_data(fr, to)
        for key in range(num_edges):
            if (edge_data[key][str(fr.uuid)] == fr_iface and
                edge_data[key][str(to.uuid)] == to_iface):
                return True
        return False

    def add_link(self, fr_iface: Interface, to_iface: Interface) -> None:
        fr = fr_iface.comp
        to = to_iface.comp
        # prevent adding same link multiple times
        if not self.has_link(fr_iface, to_iface):
            self.add_edges_from([(fr, to, {str(fr.uuid): fr_iface,
                                           str(to.uuid): to_iface})])

    def make_path(self, gcid):
        return fabs / 'fabric{f}/{f}:{s:04x}/{f}:{s:04x}:{c:03x}'.format(
            f=self.fabnum, s=gcid.sid, c=gcid.cid)

    def update_path(self, path):
        self.path = path
        self.fabnum = component_num(path)

    def iface_unusable(self, iface):
        # lookup impacted routes
        impacted = self.routes.impacted(iface)
        for rt in impacted:
            log.debug('route {} impacted by unusable {}'.format(rt, iface))
            # Revisit: route around failed link (if possible)
            try:
                new_rt = self.route(rt.fr, rt.to)
                # Revisit: finish this
            except nx.exception.NetworkXNoPath:
                # no valid route anymore, remove unreachable comp
                rt.fr.unreachable_comp(rt.to, iface, rt)
        # end for

    @register(events, 'IfaceErr')
    def iface_error(self, key, br, sender, iface, pkt):
        es = genz.IErrorES(pkt['ES'])
        log.info('{}: {}:{}({}) from {} on {}'.format(br, key, es.errName,
                                                es.errSeverity, sender, iface))
        status = iface.phy_init() # get PHY status (no actual init)
        state = iface.iface_state()
        # Revisit: Containment and RootCause
        if not iface.usable:
            self.iface_unusable(iface)
        return { key: 'ok' }

    @register(events, 'WarmIfaceReset', 'FullIfaceReset')
    def iface_reset(self, key, br, sender, iface, pkt):
        log.info('{}: {} from {} on {}'.format(br, key, sender, iface))
        status = iface.phy_init() # get PHY status (no actual init)
        state = iface.iface_state()
        if not iface.usable:
            self.iface_unusable(iface)
        return { key: 'ok' }

    @register(events, 'NewPeerComp')
    def new_peer_comp(self, key, br, sender, iface, pkt):
        log.info('{}: {} from {} on {}'.format(br, key, sender, iface))
        iup = iface.iface_init()
        # Revisit: check iup
        # find previous Component (if there is one)
        prev_comp = iface.peer_comp
        sender.explore_interfaces(self.pfm, ingress_iface=None, # Revisit
                                  explore_ifaces=[iface], prev_comp=prev_comp)
        return { key: 'ok' }

    def dispatch(self, key, *args, **kwargs):
        try:
            ret = getattr(self, self.events[key])(key, *args, **kwargs)
        except KeyError:
            log.warning('no handler for UEP {}'.format(key))
            ret = { key: 'no handler' }
        return ret

    def handle_uep(self, body):
        mgr_uuid = UUID(body.get('GENZ_A_UEP_MGR_UUID'))
        # Revisit: check mgr_uuid against self.mgr_uuid
        br_gcid = GCID(val=body.get('GENZ_A_UEP_BRIDGE_GCID'))
        br = self.comp_gcids[br_gcid]
        flags = body.get('GENZ_A_UEP_FLAGS')
        local = flags & 0x10 # Revisit: enum?
        ts_sec = body.get('GENZ_A_UEP_TS_SEC')
        ts_nsec = body.get('GENZ_A_UEP_TS_NSEC')
        # Revisit: do something with ts_sec/ts_nsec
        pkt = body.get('GENZ_A_UEP_PKT')  # dict, not genz.Packet
        if local:
            sender = br
        else:
            gc = pkt['GC']
            scid = pkt['SCID']
            sender_gcid = GCID(cid=scid, sid=(pkt['SSID'] if gc else
                                              br.gcid.sid))
            sender = self.comp_gcids[sender_gcid]
        if pkt['IV']:
            iface = sender.interfaces[pkt['IfaceID']]
        else:
            iface = None
        if zephyr_conf.args.keyboard > 2:
            set_trace()
        # dispatch to event handler based on EventName
        return self.dispatch(pkt['EventName'], br, sender, iface, pkt)

    def to_json(self):
        nl = nx.node_link_data(self)
        js = json.dumps(nl, indent=2) # Revisit: indent
        return js
