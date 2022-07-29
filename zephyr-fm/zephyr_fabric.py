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
from typing import List, Tuple, Iterator
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
        self.pfm = None
        super().__init__(fab_uuid=self.fab_uuid, mgr_uuids=[self.mgr_uuid])
        log.info('fabric: {}, num={}, fab_uuid={}, mgr_uuid={}'.format(
            path, self.fabnum, self.fab_uuid, self.mgr_uuid))

    def assign_gcid(self, comp, ssdt_sz=4096, proposed_gcid=None):
        # Revisit: subnets
        # Revisit: CID conficts between accepted & assigned are possible
        random_cids = self.random_cids
        if self.refill_gcids:
            default_range = (1, ssdt_sz-1)
            cid_range = self.conf.data.get('cid_range', default_range)
            min_cid, max_cid = cid_range if len(cid_range) == 2 else default_range
            self.avail_gcids = (
                random.sample(range(min_cid, max_cid+1), max_cid-min_cid+1)
                if random_cids else list(range(min_cid, max_cid+1)))
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

    def set_comp_name(self, comp, name: str):
        self.nodes[comp]['name'] = name

    def generate_nonce(self):
        while True:
            r = randgen.getrandbits(64)
            if not r in self.nonce_list:
                self.nonce_list.append(r)
                return r

    def br_paths(self):
        def br_paths_generator(br_paths, local_bridges):
            # order of local_bridges controls order returned and thus PFM
            mapping = { self.get_cuuid_serial(bp) : bp for bp in br_paths }
            for br in local_bridges:
                try:
                    br_path = mapping[br]
                except KeyError:
                    log.warning('local bridge {} not found'.format(br))
                    continue
                yield br_path
            # end for

        br_paths = self.path.glob('bridge*')
        local_bridges = self.conf.data.get('local_bridges', [])
        if len(local_bridges) == 0:
            return br_paths
        else:
            return br_paths_generator(br_paths, local_bridges)

    def get_cuuid_serial(self, br_path):
        cuuid = get_cuuid(br_path)
        serial = get_serial(br_path)
        return str(cuuid) + ':' + serial

    def fab_init(self):
        for br_path in self.br_paths():
            cuuid_serial = self.get_cuuid_serial(br_path)
            cur_gcid = get_gcid(br_path)
            brnum = component_num(br_path)
            cclass = int(get_cclass(br_path))
            if self.pfm is None: # this bridge will be our PFM component
                tmp_gcid = cur_gcid if cur_gcid.sid == TEMP_SUBNET else INVALID_GCID
                br = LocalBridge(cclass, self, self.map, br_path, self.mgr_uuid,
                                 local_br=True, brnum=brnum, dr=None,
                                 tmp_gcid=tmp_gcid, netlink=self.nl,
                                 verbosity=self.verbosity)
                gcid = self.assign_gcid(br, ssdt_sz=br.ssdt_size(haveCore=False)[0])
                self.set_pfm(br)
                log.info('{}:{} bridge{} {}'.format(self.fabnum, gcid, brnum, cuuid_serial))
                usable = br.comp_init(self.pfm)
                if usable:
                    self.bridges.append(br)
                    br.explore_interfaces(self.pfm)
                else:
                    self.set_pfm(None)
                    log.warning(f'{self.fabnum}:{gcid} bridge{brnum} is not usable')
            else: # not first bridge (self.pfm is not None)
                gcid = cur_gcid
                try:
                    br = self.cuuid_serial[cuuid_serial]
                except KeyError:
                    log.warning('{}:{} bridge{} {} not connected to fabric'.
                                format(self.fabnum, gcid, brnum, cuuid_serial))
                    continue
                # Revisit: check C-Up and mgr_uuid?
                log.info('{}:{} bridge{} {} alternate bridge to fabric{0}'.format(self.fabnum, gcid, brnum, cuuid_serial))
                self.bridges.append(br)
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

    # Revisit: this doesn't use 'self' and so should be in class Route
    def route_entries_avail(self, rt: Route) -> bool:
        fr = rt.fr
        to = rt.to
        for elem in rt:
            if not elem.route_entries_avail(fr, to):
                return False
        return True

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
                    min_paths: int = 2, routes: List[Route] = None,
                    max_routes: int = None) -> Iterator[Route]:
        if routes is not None:
            for rt in routes:
                yield rt
            return

        paths = self.all_shortest_paths(fr, to, cutoff_factor=cutoff_factor,
                                        min_paths=min_paths,
                                        max_paths=max_routes)
        cnt = 0
        for path in paths: # in order, shortest to longest
            if max_routes is not None and cnt >= max_routes:
                return
            rt = Route(path)
            if self.route_entries_avail(rt):
                self.route_info_update(rt, True)
                cnt += 1
                yield rt
            # MultiGraph routes - by definition, same len as original rt
            for mg_rt in rt.multigraph_routes():
                if max_routes is not None and cnt >= max_routes:
                    return
                if self.route_entries_avail(mg_rt):
                    self.route_info_update(mg_rt, True)
                    cnt += 1
                    yield mg_rt
            # end for mg_rt
        # end for path

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
        cur_rts = self.get_routes(fr, to)
        new_rts = []
        for route in self.find_routes(fr, to, routes=routes,
                                      max_routes=zephyr_conf.args.max_routes):
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
                         routes: List[Route]) -> None:
        # Revisit: when tearing down HW routes from "fr" to "to",
        # Revisit: some of the components may not be reachable from PFM
        cur_rts = self.get_routes(fr, to)
        for route in routes:
            if route not in cur_rts:
                log.debug('skipping missing route {}'.format(route))
            else:
                log.info('removing route from {} to {} via {}'.format(
                    fr, to, route))
                self.write_route(route, enable=False)
                self.routes.remove(fr, to, route)
        # end for

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
            # route around failed link (if possible)
            try:
                self.teardown_routing(rt.fr, rt.to, [rt])
                self.setup_routing(rt.fr, rt.to)
            except nx.exception.NetworkXNoPath:
                # no valid route anymore, remove unreachable comp
                rt.fr.unreachable_comp(rt.to, iface, rt)
        # end for

    @register(events, 'IfaceErr')
    def iface_error(self, key, br, sender, iface, pkt):
        genz = zephyr_conf.genz
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
        rec = body.get('GENZ_A_UEP_REC')  # dict, not genz.UEPEventRecord
        if local:
            sender = br
        else:
            gc = rec['GC']
            scid = rec['SCID']
            sender_gcid = GCID(cid=scid, sid=(rec['SSID'] if gc else
                                              br.gcid.sid))
            sender = self.comp_gcids[sender_gcid]
        if rec['IV']:
            iface = sender.interfaces[rec['IfaceID']]
        else:
            iface = None
        if zephyr_conf.args.keyboard > 2:
            set_trace()
        # dispatch to event handler based on EventName
        return self.dispatch(rec['EventName'], br, sender, iface, rec)

    def to_json(self):
        nl = nx.node_link_data(self)
        js = json.dumps(nl, indent=2) # Revisit: indent
        return js

    def get_routes(self, fr: Component, to: Component):
        try:
            return self.routes.get_routes(fr, to)
        except KeyError:
            return []

    def add_routes(self, body):
        fab_uuid = UUID(body['fab_uuid'])
        if fab_uuid != self.fab_uuid:
            return { 'failed': [ 'fab_uuid mismatch' ] }
        try:
            routes = self.routes.parse(body['routes'], self)
        except:
            return { 'failed': [ 'routes parse error' ] }
        for key, rts in routes.items():
            fr, to = key
            for rt in rts.get_routes(fr, to):
                if rt in self.get_routes(fr, to):
                    log.info('not adding existing route {}'.format(rt))
                elif self.route_entries_avail(rt):
                    self.route_info_update(rt, True)
                    self.setup_routing(fr, to, routes=[rt])
                else:
                    log.warning('insufficient route entries to add {}'.format(rt))
            # end for rt
        # end for key
        # Revisit: return correct success/failed dict
        return { 'success': [] }

    def remove_routes(self, body):
        fab_uuid = UUID(body['fab_uuid'])
        if fab_uuid != self.fab_uuid:
            return { 'failed': [ 'fab_uuid mismatch' ] }
        try:
            routes = self.routes.parse(body['routes'], self)
        except:
            return { 'failed': [ 'routes parse error' ] }
        for key, rts in routes.items():
            fr, to = key
            for rt in rts.get_routes(fr, to):
                if rt not in self.get_routes(fr, to):
                    log.info('cannot remove non-existent route {}'.format(rt))
                elif self.route_entries_avail(rt):
                    self.route_info_update(rt, False)
                    self.teardown_routing(fr, to, [rt])
                else:
                    log.warning('missing route entries removing {}'.format(rt))
            # end for rt
        # end for key
        # Revisit: return correct success/failed dict
        return { 'success': [] }
