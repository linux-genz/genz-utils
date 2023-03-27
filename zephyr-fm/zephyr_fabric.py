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
from typing import List, Tuple, Iterator, Optional
from genz.genz_common import GCID, CState, IState, RKey, PHYOpStatus, ErrSeverity, RefCount, AllOnesData
import itertools
import random
import posixpath
import requests
import sched
import socket
import time
from pathlib import Path
from pdb import set_trace
import networkx as nx
from uuid import UUID, uuid4
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from base64 import b64encode, b64decode
from heapq import nlargest
from zeroconf import Zeroconf, ServiceInfo, ServiceBrowser
from threading import Thread
from collections import defaultdict
import zephyr_conf
from zephyr_conf import log, INVALID_GCID
from zephyr_iface import Interface
from zephyr_comp import (Component, LocalBridge, component_num, get_cuuid,
                         get_cclass, get_gcid, get_serial, get_mgr_uuid)
from zephyr_route import RouteElement, Routes, Route
from zephyr_res import Resources

# Revisit: copied from zephyr_subsys.py
# Magic to get JSONEncoder to call to_json method, if it exists
def _default(self, obj):
    return getattr(obj.__class__, 'to_json', _default.default)(obj)

_default.default = json.JSONEncoder().default
json.JSONEncoder.default = _default

def uuid_to_json(self):
    return str(self)
UUID.to_json = uuid_to_json

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

# Categorize a sequence
# from https://stackoverflow.com/questions/949098/how-can-i-partition-split-up-divide-a-list-based-on-a-condition
def categorize(func, seq):
    """Return mapping from categories to lists
    of categorized items.
    """
    d = defaultdict(list)
    for item in seq:
        d[func(item)].append(item)
    return d

class Fabric(nx.MultiGraph):
    events = {} # UEP events dispatch dict

    @staticmethod
    def link_weight(fr, to, edge_dict):
        fr_iface = edge_dict[str(fr.uuid)]
        to_iface = edge_dict[str(to.uuid)]
        # return None for unusable links - DR interfaces are always usable
        usable = ((fr.dr is not None or fr_iface.usable) and
                  (to.dr is not None or to_iface.usable))
        # Revisit: consider bandwidth, latency, LWR
        return 1 if usable else None

    def __init__(self, nl, mainapp, map, path, fab_uuid=None, grand_plan=None,
                 random_cids=False, conf=None, mgr_uuid=None, verbosity=0):
        self.nl = nl
        self.mainapp = mainapp
        self.map = map
        self.path = path
        self.fabnum = component_num(path)
        self.fab_uuid = fab_uuid
        new_mgr_uuid = mgr_uuid is None and not zephyr_conf.args.sfm
        self.mgr_uuid = uuid4() if new_mgr_uuid else mgr_uuid
        self.instance_uuid = self.mgr_uuid if new_mgr_uuid else uuid4()
        self.random_cids = random_cids
        self.conf = conf
        self.verbosity = verbosity
        self.bridges = []      # indexed by bridge number
        self.components = {}   # key: comp.uuid
        self.cuuid_serial = {} # key: cuuid:serial
        self.comp_gcids = {}   # key: comp.gcid
        self.assigned_gcids = self.conf.get_assigned_cids()
        self.refill_gcids = True
        self.nonce_list = [ 0 ]
        self.routes = Routes(fab_uuid=fab_uuid)
        self.resources = Resources(self)
        self.aesgcm = AESGCM(b64decode(conf.data['aesgcm_key']))
        self.pfm = None
        self.sfm = None
        self.pfm_fm = None
        self.fms = {}
        self.promote_sfm_refcount = RefCount()
        self._g = None  # Graph() for routing
        mgr_uuids = [] if self.mgr_uuid is None else [self.mgr_uuid]
        ns = time.time_ns()
        super().__init__(fab_uuid=self.fab_uuid, mgr_uuids=mgr_uuids,
                         cur_timestamp=ns, mod_timestamp=ns)
        log.info(f'fabric: {path}, num={self.fabnum}, fab_uuid={self.fab_uuid}, mgr_uuid={self.mgr_uuid}, cur_timestamp={ns}')

    def assign_gcid(self, comp, ssdt_sz=4096, proposed_gcid=None, reclaim=False,
                    cstate=CState.CUp) -> Optional[GCID]:
        # Revisit: subnets
        # Revisit: CID conficts between accepted & assigned are possible
        random_cids = self.random_cids
        if self.refill_gcids:
            default_range = (1, ssdt_sz-1)
            cid_range = self.conf.data.get('cid_range', default_range)
            min_cid, max_cid = cid_range if len(cid_range) == 2 else default_range
            self.avail_cids = (
                random.sample(range(min_cid, max_cid+1), max_cid-min_cid+1)
                if random_cids else list(range(min_cid, max_cid+1)))
            self.refill_gcids = False
        if proposed_gcid is not None:
            try:
                self.avail_cids.remove(proposed_gcid)
                comp.gcid = proposed_gcid
            except ValueError:
                comp.gcid = None
        else:
            try:
                availLen = len(self.avail_cids)
                cid = self.avail_cids.pop(0)
                if reclaim and cstate == CState.CCFG:
                    done = False
                    while not done:
                        if cid not in self.assigned_gcids.values():
                            done = True
                        else:
                            self.avail_cids.append(cid)
                            availLen -= 1
                            if availLen <= 0:
                                raise IndexError
                            cid = self.avail_cids.pop(0)
                    # end while
                # end if reclaim
                comp.gcid = GCID(cid=cid)
            except IndexError:
                comp.gcid = None
        if comp.gcid is not None:
            # Cannot update assigned_gcids here because cuuid_serial is
            # not available yet - must defer to update_assigned_gcids()
            # called later in comp_init()
            self.nodes[comp]['gcids'] = [ str(comp.gcid) ]
        return comp.gcid

    def update_assigned_gcids(self, comp: Component) -> None:
        self.assigned_gcids[comp.cuuid_serial] = comp.gcid

    def free_gcid(self, comp: Component) -> None:
        gcid = comp.gcid
        comp.gcid = None
        if gcid is None or gcid not in self.assigned_gcids.values():
            return
        del self.assigned_gcids[comp.cuuid_serial]
        self.avail_cids.append(gcid.cid) # Revisit: random_cids
        self.nodes[comp]['gcids'].remove(str(gcid))

    def reassign_gcid(self, comp: Component) -> bool:
        cur_gcid = comp.gcid
        try:
            prev_gcid = self.assigned_gcids[comp.cuuid_serial]
        except KeyError:
            prev_gcid = cur_gcid
        if cur_gcid == prev_gcid: # no change - done
            return False
        gcid = self.assign_gcid(comp, proposed_gcid=prev_gcid)
        if gcid is None:
            log.debug(f'{comp}: unable to reassign GCID to {prev_gcid}')
            return False
        comp.tmp_gcid = cur_gcid # for teardown_routing & add_fab_comp scenario3
        # fix up routes - teardown old routes to comp & setup new
        # routes back to PFM are unaffected
        self.teardown_routing(self.pfm, comp)
        route = self.setup_routing(self.pfm, comp)
        # remove any leftover /sys tree for the new GCID
        path = self.make_path(gcid)
        if path.exists():
            comp.remove_fab_comp(force=True, useDR=False, useTMP=False,
                                 rm_paths=False)
        log.info(f'{comp}: reassignd GCID from {cur_gcid} to {gcid}')
        return True

    def add_comp(self, comp):
        self.cuuid_serial[comp.cuuid_serial] = comp
        self.comp_gcids[comp.gcid] = comp
        self.update_comp(comp)
        self._g = None  # will be recreated in all_shortest_paths()

    def get_mod_timestamp(self, comp=None) -> Tuple:
        return (self.graph['mod_timestamp'],
                None if comp is None else self.nodes[comp]['mod_timestamp'])

    def update_mod_timestamp(self, comp=None, ts=None, forceUpdate=False):
        if ts is None:
            ts = time.time_ns()
        if comp is not None:
            self.nodes[comp]['mod_timestamp'] = ts
        self.graph['mod_timestamp'] = max(ts if forceUpdate else
                                          self.graph['mod_timestamp'], ts)

    def update_comp(self, comp, forceTimestamp=False):
        self.nodes[comp]['fru_uuid'] = comp.fru_uuid
        self.nodes[comp]['max_data'] = comp.max_data
        self.nodes[comp]['max_iface'] = comp.max_iface
        self.nodes[comp]['nonce'] = self.encrypt_nonce(comp.nonce)
        self.nodes[comp]['rsp_page_grid_ps'] = comp.rsp_page_grid_ps
        comp.update_cstate(forceTimestamp=forceTimestamp)
        self.nodes[comp]['cstate'] = str(comp.cstate) # Revisit: to_json() doesn't work

    def get_comp_name(self, comp):
        try:
            return self.nodes[comp]['name']
        except KeyError:
            return None

    def set_comp_name(self, comp, name: str):
        self.nodes[comp]['name'] = name

    def generate_nonce(self):
        while True:
            r = randgen.getrandbits(64)
            if not r in self.nonce_list:
                self.nonce_list.append(r)
                return r

    def encrypt_nonce(self, comp_nonce: int) -> str:
        data = comp_nonce.to_bytes(8, 'little')
        ct_nonce = randgen.randbytes(12)
        ct = self.aesgcm.encrypt(ct_nonce, data, None)
        return b64encode(ct_nonce + ct).decode('ascii')

    def decrypt_nonce(self, nonce_str: str) -> int:
        nonce_plus_ct = b64decode(nonce_str)
        ct_nonce = nonce_plus_ct[0:12]
        ct = nonce_plus_ct[12:]
        return int.from_bytes(self.aesgcm.decrypt(ct_nonce, ct, None), 'little')

    def br_paths(self):
        def br_paths_generator(br_paths, local_bridges):
            # order of local_bridges controls order returned and thus PFM
            mapping = { self.get_cuuid_serial(bp) : bp for bp in br_paths }
            for br in local_bridges:
                try:
                    br_path = mapping[br]
                except KeyError:
                    log.warning(f'local bridge {br} not found')
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

    def fab_init(self, reclaim=False):
        zephyr_conf.is_sfm = False
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
                gcid = self.assign_gcid(br, reclaim=reclaim,
                                        ssdt_sz=br.ssdt_size(haveCore=False)[0])
                self.set_pfm(br)
                log.info(f'{self.fabnum}:{gcid} bridge{brnum} {cuuid_serial}')
                usable = br.comp_init(self.pfm)
                if usable:
                    self.bridges.append(br)
                    br.explore_interfaces(self.pfm, reclaim=reclaim)
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
        # While doing crawl-out, we were not prepared for NewPeerComp UEPs;
        # now we are, so enable them.
        log.debug('enabling NewPeerComp UEPs')
        for comp in self.components.values():
            comp.ievent_update(newPeerComp=True)

    def sfm_init(self):
        zephyr_conf.is_sfm = True
        for br_path in self.br_paths():
            cuuid_serial = self.get_cuuid_serial(br_path)
            cur_gcid = get_gcid(br_path)
            brnum = component_num(br_path)
            cclass = int(get_cclass(br_path))
            if self.sfm is None: # this bridge will be our SFM component
                self.mgr_uuid = get_mgr_uuid(br_path)
                gcid = cur_gcid
                tmp_gcid = cur_gcid if cur_gcid.sid == TEMP_SUBNET else INVALID_GCID
                # temporary component until we get the PFM-assigned uuid
                br = LocalBridge(cclass, self, self.map, br_path, self.mgr_uuid,
                                 local_br=True, brnum=brnum, dr=None,
                                 tmp_gcid=tmp_gcid, netlink=self.nl,
                                 gcid=gcid, verbosity=self.verbosity)
                gcid = self.assign_gcid(br, ssdt_sz=br.ssdt_size(haveCore=False)[0],
                                        proposed_gcid=cur_gcid)
                self.set_sfm(br)
                log.info(f'{self.fabnum}:{gcid} bridge{brnum} {cuuid_serial}')
                usable = br.comp_init(None) # None: not PFM
                if usable:
                    self.bridges.append(br)
                    log.debug(f'bridges: {self.bridges}')
                else:
                    self.set_sfm(None)
                    log.warning(f'{self.fabnum}:{gcid} bridge{brnum} is not usable')
            else: # not first bridge (self.sfm is not None)
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

    def zeroconf_browser(self, zeroconf):
        services = ['_genz-fm._tcp.local.']
        return ServiceBrowser(zeroconf, services, self)

    def set_pfm(self, pfm):
        self.pfm = pfm
        self.graph['pfm'] = pfm
        self.send_mgrs(['llamas', 'sfm'], 'mgr_topo', 'graph', self.graph,
                       op='change', invertTypes=True)

    def set_sfm(self, sfm: Component):
        self.sfm = sfm
        self.graph['sfm'] = sfm
        self.send_mgrs(['llamas', 'sfm'], 'mgr_topo', 'graph', self.graph,
                       op='change', invertTypes=True)

    def all_shortest_paths(self, fr: Component, to: Component,
                           cutoff_factor: float = 3.0,
                           min_paths: int = 2,
                           max_paths: int = None) -> List[List[Component]]:
        # Revisit: need to control how multi-edge attributes are merged so that
        # link_weight returns the right answer (especially for returning "None")
        if self._g is None:
            # shortest_simple_paths does not work on a MultiGraph
            self._g = nx.Graph(self)
        try:
            all = nx.shortest_simple_paths(self._g, fr, to,
                                           weight=Fabric.link_weight)
        except Exception as e:
            log.error(f'all_shortest_paths: fr={fr}, to={to}: "{e}"')
            return
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

    def find_dr_routes(self, fr: Component, to: Component,
                       cur_routes: List[Route] = None):
        # the assumption is that we already have routes to the dr_comp and just
        # need to add on the DR hop to each
        dr = to.dr
        dr_comp = dr.comp
        if dr_comp == fr:  # special case for direct attach
            rt = Route([fr, to], [dr])
            if rt.route_entries_avail():
                rt.route_info_update(True)
                yield rt
            return
        for dr_rt in self.get_routes(fr, dr_comp):
            rt = Route(dr_rt.path + [to], itertools.chain(dr_rt.elems, [dr]))
            if rt not in cur_routes and rt.route_entries_avail():
                rt.route_info_update(True)
                yield rt

    def find_routes(self, fr: Component, to: Component,
                    cutoff_factor: float = 3.0,
                    min_paths: int = 2, routes: List[Route] = None,
                    cur_routes: List[Route] = None,
                    max_routes: int = None) -> Iterator[Route]:
        if routes is not None: # explicit routes param ignores max_routes
            for rt in routes:
                if rt not in cur_routes:
                    yield rt
            return
        if to.dr is not None: # must route through to's DR interface
            for rt in self.find_dr_routes(fr, to, cur_routes):
                yield rt
            return
        min_paths = min_paths if max_routes is None else min(min_paths, max_routes)
        paths = self.all_shortest_paths(fr, to, cutoff_factor=cutoff_factor,
                                        min_paths=min_paths,
                                        max_paths=max_routes)
        cnt = 0
        for path in paths: # in order, shortest to longest
            if max_routes is not None and cnt >= max_routes:
                return
            rt = Route(path)
            if rt not in cur_routes and rt.route_entries_avail():
                rt.route_info_update(True)
                cnt += 1
                yield rt
            # MultiGraph routes - by definition, same len as original rt
            for mg_rt in rt.multigraph_routes():
                if max_routes is not None and cnt >= max_routes:
                    return
                if mg_rt not in cur_routes and mg_rt.route_entries_avail():
                    mg_rt.route_info_update(True)
                    cnt += 1
                    yield mg_rt
            # end for mg_rt
        # end for path

    def write_route(self, route: Route, write_ssdt=True, enable=True, refcountOnly=False):
        # When enabling a route, write entries in reverse order so
        # that live updates to routing never enable a route entry
        # before its "downstream" entries. When disabling a route,
        # start at the front, for the same reason.
        rt_iter = reversed(route) if (enable and not refcountOnly) else iter(route)
        for rt in rt_iter:
            if rt.ingress_iface is not None:
                # switch: add to's GCID to rt's LPRT
                rt.set_lprt(route.to, valid=enable, refcountOnly=refcountOnly,
                            updateRtNum=refcountOnly)
            elif write_ssdt:
                # add to's GCID to rt's SSDT
                rt.set_ssdt(route.to, valid=enable, refcountOnly=refcountOnly,
                            updateRtNum=refcountOnly)

    def write_routes(self, rts: Routes, write_ssdt=True, enable=True, refcountOnly=False):
        for rt in rts:
            log.info(f'writing PFM route from {rt.fr} to {rt.to} via {rt}')
            self.write_route(rt, write_ssdt, enable, refcountOnly=refcountOnly)
        # end for

    def setup_routing(self, fr: Component, to: Component, write_ssdt=True,
                      routes=None, send=True, overrideMaxRoutes=False) -> List[Route]:
        cur_rts = self.get_routes(fr, to)
        new_rts = []
        excess_rts = []
        max_routes = None if overrideMaxRoutes else zephyr_conf.args.max_routes
        for route in self.find_routes(fr, to, routes=routes, max_routes=max_routes,
                                      cur_routes=cur_rts):
            route.refcount.inc()
            log.debug(f'adding route(hc={route.hc}) from {fr} to {to} via {route}, refcount={route.refcount.value()}')
            self.write_route(route, write_ssdt, refcountOnly=(not send))
            self.routes.add(fr, to, route)
            new_rts.append(route)
        # end for
        merged = sorted(set(itertools.chain.from_iterable((cur_rts, new_rts))))
        n = len(merged)
        if max_routes is not None and n > max_routes:
            log.debug(f'too many routes ({n}) from {fr} to {to}')
            excess_rts = nlargest(n - max_routes, merged)
            self.teardown_routing(fr, to, excess_rts, send=send)
        log.info(f'added {len(new_rts)} routes, removed {len(excess_rts)} routes from {fr} to {to}')
        if write_ssdt and to is self.pfm:
            fr.pfm_uep_update(self.pfm)
        elif write_ssdt and to is self.sfm:
            fr.sfm_uep_update(self.sfm)
        if send and len(new_rts) > 0:
            js = Routes(fab_uuid=self.fab_uuid, routes=new_rts).to_json()
            self.send_sfm('sfm_routes', 'routes', js, op='add')
            self.send_mgrs(['sfm', 'llamas'], 'mgr_routes', 'routes', js,
                           op='add', invertTypes=True)
        return new_rts

    def setup_bidirectional_routing(self, fr: Component, to: Component,
                                    write_to_ssdt=True) -> Tuple[List[Route], List[Route]]:
        if fr is to: # Revisit: loopback
            return None
        to_routes = self.setup_routing(fr, to) # always write fr ssdt
        to_inverted = [rt.invert(self) for rt in to_routes]
        # rt.invert may return None for routes that cannot be inverted
        # (because a route table row is full) - filter those routes out
        to_filtered = filter(lambda rt: rt is not None, to_inverted)
        fr_routes = (self.setup_routing(to, fr, write_ssdt=write_to_ssdt,
                                        routes=to_filtered)
                     if len(to_routes) > 0 else [])
        return (to_routes, fr_routes)

    def teardown_routing(self, fr: Component, to: Component,
                         routes: List[Route] = None, send=True) -> None:
        # Revisit: when tearing down HW routes from "fr" to "to",
        # Revisit: some of the components may not be reachable from PFM
        cur_rts = self.get_routes(fr, to)
        if routes is None:
            routes = cur_rts
        for route in routes:
            if route not in cur_rts:
                log.debug(f'skipping missing route {route}')
            else:
                last = route.refcount.dec()
                if not last:
                    log.debug(f'decremented route {route} refcount, refcount={route.refcount.value()}')
                    continue
                log.debug(f'removing route(hc={route.hc}) from {fr} to {to} via {route}')
                route.route_info_update(False) # remove route_info
                self.write_route(route, enable=False, refcountOnly=(not send))
                self.routes.remove(fr, to, route)
        # end for
        if send and len(routes) > 0:
            js = Routes(fab_uuid=self.fab_uuid, routes=routes).to_json()
            self.send_sfm('sfm_routes', 'routes', js, op='remove')
            self.send_mgrs(['sfm', 'llamas'], 'mgr_routes', 'routes', js,
                           op='remove', invertTypes=True)

    def recompute_routes(self, iface1, iface2):
        # Revisit: this is O(n**2) during crawl-out, worse later
        # Revisit: can we make use of iface1/2 to do better?
        for fr, to in self.routes.fr_to.keys():
            if not fr.usable or not to.usable:
                log.debug(f'skipping recompute routes for unusable {fr}, {to}')
                continue
            log.debug(f'recompute routes: {fr}, {to}')
            self.setup_routing(fr, to)

    def replace_dr_routes(self, fr: Component, to: Component):
        for dr_rt in filter(lambda x: x.is_dr, self.get_routes(fr, to)):
            rt = Route(dr_rt.path, dr_rt.elems, noDR=True)
            # do replacement
            if rt.route_entries_avail():
                self.routes.remove(fr, to, dr_rt) # remove old DR
                dr_rt.route_info_update(False)
                self.routes.add(fr, to, rt)       # add new
                rt.route_info_update(True)
            else:
                log.warning(f'cannot replace DR route {dr_rt}')
        # end for

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

    def add_link(self, fr_iface: Interface, to_iface: Interface) -> bool:
        '''Returns True if link added; False if link was already there'''
        fr = fr_iface.comp
        to = to_iface.comp
        # prevent adding same link multiple times
        if not self.has_link(fr_iface, to_iface):
            self.add_edges_from([(fr, to, {str(fr.uuid): fr_iface,
                                           str(to.uuid): to_iface})])
            self._g = None  # will be recreated in all_shortest_paths()
            return True
        return False

    def make_path(self, gcid):
        return fabs / 'fabric{f}/{f}:{s:04x}/{f}:{s:04x}:{c:03x}'.format(
            f=self.fabnum, s=gcid.sid, c=gcid.cid)

    def update_path(self, path):
        self.path = path
        self.fabnum = component_num(path)

    def iface_unusable(self, iface):
        iface.usable = False
        # lookup impacted routes
        impacted = self.routes.impacted(iface)
        # split the impacted list by (rt.fr, rt.to)
        fr_to = categorize(lambda x: (x.fr, x.to), impacted)
        # Revisit: do 1 send_mgrs for impacted, not 1 per (rt.fr, rt.to)
        log.info(f'{len(impacted)} routes impacted by unusable {iface}: {impacted}')
        for (fr, to), rts in fr_to.items():
            self.teardown_routing(fr, to, rts)
        for fr, to in fr_to.keys():
            # route around failed link (if possible)
            try:
                self.setup_routing(fr, to)
            except nx.exception.NetworkXNoPath:
                # no valid route anymore, remove unreachable comp
                fr.unreachable_comp(to, iface)
        # end for

    def uep_reason_name(self, esVal):
        genz = zephyr_conf.genz
        es = genz.ProtocolErrorES(esVal)
        rsn = es.ReasonCode
        return genz.reasonData[rsn][0]

    # UEP dispatch handlers
    # I-Error UEPs
    @register(events, 'IfaceErr')
    def iface_error(self, key, br, sender, iface, rc, rec):
        genz = zephyr_conf.genz
        es = genz.IErrorES(rec['ES'])
        bitK = es.BitK
        errName = es.errName
        log.info(f'{br}: {key}:{errName}[{bitK}]({es.errSeverity}) UEP from {sender} on {iface}')
        # with AutoStop enabled, IfaceFCFwdProgressViolation requires peer_c_reset
        if errName == 'IfaceFCFwdProgressViolation':
            log.debug(f'attempting peer_c_reset on {iface}')
            try:
                iface.peer_c_reset()
                iface.update_peer_info()
                iface.peer_comp.was_reset(iface)
            except AllOnesData:
                log.warning(f'{iface}: IfaceFCFwdProgressViolation returned all-ones data')
                iface.usable = False
                return { key: 'iface_error all-ones' }
        elif errName == 'SwitchPktRelayFailure':
            # log LPRT for debug
            iface.lprt_read(force=True, verbosity=4)
            log.debug(iface.lprt)
        try:
            # clear IErrorStatus bitK
            iface.clear_ierror_status(bitK)
            phyOk, phyChanged = iface.phy_init() # check PHY status (no actual init)
            istate, iChanged = iface.iface_state()
        except AllOnesData:  # got all-ones
            log.warning(f'{iface}: iface_error interface{iface.num} returned all-ones data')
            iface.usable = False
            return { key: 'iface all-ones' }
        # Revisit: Containment and RootCause
        if phyChanged or iChanged:
            js = { iface.comp.uuid: iface.to_json() }
            self.send_mgrs(['llamas'], 'mgr_topo', 'interface', js,
                           op='change', invertTypes=True)
        if not iface.usable:
            self.iface_unusable(iface)
        return { key: 'ok' }

    # I-Event UEPs
    @register(events, 'WarmIfaceReset', 'FullIfaceReset')
    def iface_reset(self, key, br, sender, iface, rc, rec):
        genz = zephyr_conf.genz
        bit = genz.IEvent.uep_map(rec['Event'])
        log.info(f'{br}: {key}[{bit}] UEP from {sender} on {iface}')
        try:
            # clear IEventStatus bit
            sender.clear_ievent_status(bit)
            phyOk, phyChanged = iface.phy_init() # check PHY status (no actual init)
            istate, iChanged = iface.iface_state()
        except AllOnesData:  # got all-ones
            log.warning(f'{iface}: iface_reset interface{iface.num} returned all-ones data')
            iface.usable = False
            return { key: 'iface all-ones' }
        if phyChanged or iChanged:
            js = { iface.comp.uuid: iface.to_json() }
            self.send_mgrs(['llamas'], 'mgr_topo', 'interface', js,
                           op='change', invertTypes=True)
        if not iface.usable:
            self.iface_unusable(iface)
        return { key: 'ok' }

    @register(events, 'NewPeerComp')
    def new_peer_comp(self, key, br, sender, iface, rc, rec):
        genz = zephyr_conf.genz
        bit = genz.IEvent.uep_map(rec['Event'])
        log.info(f'{br}: {key}[{bit}] UEP from {sender} on {iface}')
        iup = iface.iface_init()
        if not iup:
            log.warning(f'{br}: new_peer_comp: unable to bring up interface {iface}')
            return { key: f'{iface} not I-Up' }
        sender.explore_interfaces(self.pfm, ingress_iface=None, explore_ifaces=[iface],
                                  reclaim=True, send=True)
        try:
            # clear IEventStatus bit
            sender.clear_ievent_status(bit)
        except AllOnesData:  # got all-ones
            log.warning(f'{iface}: new_peer_comp interface{iface.num} returned all-ones data')
            iface.usable = False
            return { key: 'ievent_status all-ones' }
        return { key: 'ok' }

    @register(events, 'ExceededTransientErrThresh')
    def trans_err_thresh(self, key, br, sender, iface, rc, rec):
        genz = zephyr_conf.genz
        bit = genz.IEvent.uep_map(rec['Event'])
        log.info(f'{br}: {key}[{bit}] UEP from {sender} on {iface}')
        # Revisit: do something useful
        try:
            # clear IEventStatus bit
            sender.clear_ievent_status(bit)
        except AllOnesData:  # got all-ones
            log.warning(f'{iface}: trans_err_thresh interface{iface.num} returned all-ones data')
            iface.usable = False
            return { key: 'ievent_status all-ones' }
        return { key: 'ok' }

    @register(events, 'IfacePerfDegradation')
    def iface_perf_degradation(self, key, br, sender, iface, rc, rec):
        genz = zephyr_conf.genz
        bit = genz.IEvent.uep_map(rec['Event'])
        log.info(f'{br}: {key}[{bit}] UEP from {sender} on {iface}')
        # Revisit: do something useful
        try:
            # clear IEventStatus bit
            sender.clear_ievent_status(bit)
        except AllOnesData:  # got all-ones
            log.warning(f'{iface}: iface_perf_degradation interface{iface.num} returned all-ones data')
            iface.usable = False
            return { key: 'ievent_status all-ones' }
        return { key: 'ok' }

    # C-Error UEPs
    @register(events, 'RecovProtocolErr')
    def recov_protocol_err(self, key, br, sender, iface, rc, rec):
        genz = zephyr_conf.genz
        esVal = rec['ES']
        rsnName = self.uep_reason_name(esVal)
        bit = genz.CError.uep_map(rec['Event'], esVal)
        log.info(f'{br}: {key}:{rsnName}[{bit}] UEP from {sender}, rc {rc}') # no iface
        # Revisit: do something useful
        try:
            # clear CErrorStatus bit
            sender.clear_cerror_status(bit)
        except AllOnesData:  # got all-ones
            log.warning(f'{sender}: recov_protocol_err returned all-ones data')
            return { key: 'cerror_status all-ones' }
        return { key: 'ok' }

    @register(events, 'UnrecovProtocolErr')
    def unrecov_protocol_err(self, key, br, sender, iface, rc, rec):
        genz = zephyr_conf.genz
        esVal = rec['ES']
        rsnName = self.uep_reason_name(esVal)
        bit = genz.CError.uep_map(rec['Event'], esVal)
        log.info(f'{br}: {key}:{rsnName}[{bit}] UEP from {sender}, rc {rc}') # no iface
        # Revisit: do something useful
        try:
            # clear CErrorStatus bit
            sender.clear_cerror_status(bit)
        except AllOnesData:  # got all-ones
            log.warning(f'{sender}: unrecov_protocol_err returned all-ones data')
            return { key: 'cerror_status all-ones' }
        return { key: 'ok' }

    # C-Event UEPs
    @register(events, 'ExcessiveRNRNAK')
    def excessive_rnr_nak(self, key, br, sender, iface, rc, rec):
        genz = zephyr_conf.genz
        esVal = rec['ES']
        es = genz.OpcodeEventES(esVal)
        pktName = genz.Packet.className(es.OpClass, es.OpCode)
        bit = genz.CEvent.uep_map(rec['Event'], esVal)
        log.info(f'{br}: {key}[{bit}] UEP from {sender}, rc {rc}, pkt {pktName}') # no iface
        # Revisit: do something useful
        try:
            # clear CEventStatus bit
            sender.clear_cevent_status(bit)
        except AllOnesData:  # got all-ones
            log.warning(f'{sender}: excessive_rnr_nak_err returned all-ones data')
            return { key: 'cevent_status all-ones' }
        return { key: 'ok' }

    def dispatch(self, key, *args, **kwargs):
        try:
            ret = getattr(self, self.events[key])(key, *args, **kwargs)
        except KeyError:
            log.warning(f'no handler for UEP {key}')
            ret = { key: 'no handler' }
        return ret

    def handle_uep(self, body):
        if zephyr_conf.is_sfm: # a UEP delivered to SFM means PFM delivery failed
            self.promote_sfm_to_pfm()

        mgr_uuid = UUID(body.get('GENZ_A_UEP_MGR_UUID'))
        if mgr_uuid != self.mgr_uuid:
            log.warning(f'incorrect mgr_uuid: {mgr_uuid}')
            return None
        br_gcid = GCID(val=body.get('GENZ_A_UEP_BRIDGE_GCID'))
        try:
            br = self.comp_gcids[br_gcid]
        except KeyError:
            log.warning(f'unknown bridge GCID: {br_gcid}')
            return None
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
            try:
                sender = self.comp_gcids[sender_gcid]
            except KeyError:
                log.warning(f'unknown UEP sender GCID: {sender_gcid}')
                return None
        if rec['IV']:
            ifnum = rec['IfaceID']
            try:
                iface = sender.interfaces[ifnum]
            except IndexError:
                log.warning(f'unknown UEP sender interface: {sender_gcid}.{ifnum}')
                return None
        else:
            iface = None
        if rec['CV']:
            rc_cid = rec['RCCID']
            sv = rec['SV']
            rc_gcid = GCID(cid=rc_cid, sid=(rec['RCSID'] if sv else br.gcid.sid))
            try:
                rc = self.comp_gcids[rc_gcid]
            except KeyError:
                log.warning(f'unknown UEP rc GCID: {rc_gcid}')
                return None
        else:
            rc = None
        if zephyr_conf.args.keyboard > 2:
            set_trace()
        # dispatch to event handler based on EventName
        return self.dispatch(rec['EventName'], br, sender, iface, rc, rec)

    def unreachable_comps(self, fr: Component):
        '''Return list of unreachable components from @fr'''
        return filter(lambda x: x.is_unreachable(fr), self.components)

    def to_json(self):
        self.graph['cur_timestamp'] = time.time_ns()
        nl = nx.node_link_data(self)
        return nl

    def get_routes(self, fr: Component, to: Component):
        try:
            return self.routes.get_routes(fr, to)
        except KeyError:
            return []

    def add_routes(self, body, send=True):
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
                existing = self.get_routes(fr, to)
                if rt in existing:
                    index = existing.index(rt)
                    existing[index].refcount.inc()
                    log.info(f'incremented refcount on existing route {existing[index]}, refcount={existing[index].refcount.value()}')
                elif rt.route_entries_avail():
                    rt.route_info_update(True)
                    self.setup_routing(fr, to, routes=[rt], send=send, overrideMaxRoutes=True)
                else:
                    log.warning(f'insufficient route entries to add {rt}')
            # end for rt
        # end for key
        # Revisit: return correct success/failed dict
        return { 'success': [] }

    def remove_routes(self, body, send=True):
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
                    log.info(f'cannot remove non-existent route {rt}')
                elif rt.route_entries_avail():
                    self.teardown_routing(fr, to, [rt], send=send)
                else:
                    log.warning(f'missing route entries removing {rt}')
            # end for rt
        # end for key
        # Revisit: return correct success/failed dict
        return { 'success': [] }

    def enable_sfm(self, sfm: Component):
        # Revisit: what to do if there's already a registered SFM?
        for comp in self.components.values():
            comp.enable_sfm(sfm)
        self.set_sfm(sfm)
        return 'ok'

    def disable_sfm(self, sfm: Component):
        # Revisit: what to do if there isn't a registered SFM?
        for comp in self.components.values():
            comp.disable_sfm(sfm)
        self.set_sfm(None)
        return 'ok'

    # zeroconf ServiceBrowser service handlers
    def add_service(self, zeroconf: Zeroconf, type: str, name: str) -> None:
        log.debug(f'Service {name} of type {type} Added')
        info = zeroconf.get_service_info(type, name)
        log.debug(f'Info from zeroconf.get_service_info: {info}')
        if name in self.fms:
            log.error(f'duplicate FM name {name}')
            return
        fm = FM(info)
        self.fms[name] = fm
        if fm.fab_uuid != self.fab_uuid:
            log.info(f'ignoring FM {name} due to fab_uuid mismatch {fm.fab_uuid} != {self.fab_uuid}')
            return
        if fm.mgr_uuid != self.mgr_uuid:
            log.info(f'ignoring FM {name} due to mgr_uuid mismatch {fm.mgr_uuid} != {self.mgr_uuid}')
            return
        if not fm.pfm:
            log.info(f'ignoring non-PFM {name}')
            return
        self.subscribe_sfm(fm)
        topo, pfm, sfm, mgr_uuids = self.get_fm_topo(fm)
        self.add_mgr_uuids(mgr_uuids)
        self.add_comps_from_topo(topo, pfm, sfm)
        self.add_links_from_topo(topo)
        self.update_mod_timestamp(ts=topo.graph['mod_timestamp'], forceUpdate=True)
        self.get_fm_endpoints(fm)
        routes = self.get_fm_routes(fm)
        self.write_routes(routes, refcountOnly=True)
        self.get_fm_resources(fm)
        self.pfm_fm = fm
        # start heartbeat thread
        self.heartbeat = RepeatedTimer(zephyr_conf.args.sfm_heartbeat, self.check_pfm, fm)
        self.heartbeat.start()

    def remove_service(self, zeroconf: Zeroconf, type: str, name: str) -> None:
        log.debug(f'Service {name} of type {type} Removed')
        try:
            fm = self.fms[name]
        except KeyError:
            log.error(f'attempt to remove unknown FM {name}')
            return
        del self.fms[name]
        if fm == self.pfm_fm:
            self.promote_sfm_to_pfm()
        # Revisit: finish this

    def update_service(self, zeroconf: Zeroconf, type: str, name: str) -> None:
        log.debug(f'Service {name} of type {type} Updated')
        info = zeroconf.get_service_info(type, name)
        log.debug(f'Info from zeroconf.get_service_info: {info}')
        unknown = False
        try:
            fm = self.fms[name]
        except KeyError:
            log.warning(f'attempt to update unknown FM {name}')
            unknown = True
            fm = FM(info) # treat as if this was an 'add'
        # Revisit: finish this

    def endpoints_url(self, fm: 'FM', fm_endpoint=None):
        cfg = self.mainapp.config
        port = self.mainapp.port
        eps = cfg['ENDPOINTS']
        mainapp_eps = self.mainapp.kwargs.get('endpoints', None)
        if mainapp_eps is not None:
            eps = mainapp_eps
        if fm_endpoint is None:
            fm_endpoint = self.mainapp.config.get('SFM_SUBSCRIBE', 'subscribe/sfm')
        # Revisit: multiple FM addresses
        url = (f'http://{fm.addresses[0]}:{fm.port}/{fm_endpoint}' if fm is not None
               else None)

        this_hostname = self.mainapp.config.get('THIS_HOSTNAME', None)
        if this_hostname is None:
            this_hostname = f'http://{self.mainapp.hostname}:{port}'

        # Revisit: llamas has these - needed?
        #if not utils.is_port_in_url(this_hostname):
        #    this_hostname = f'{this_hostname}:{port}'
        #if utils.is_valid_url(this_hostname) is False:
        #    raise RuntimeError('Invalid THIS_HOSTNAME url in config: %s ' % this_hostname)

        endpoints = {}
        for k, v in eps.items():
            endpoints[k] = posixpath.join(this_hostname, v)

        return (url, endpoints)

    def subscribe_sfm(self, pfm: 'FM'):
        if pfm.is_subscribed: # already subscribed
            return

        bridges = [br.cuuid_serial for br in self.bridges]

        url, callback_endpoints = self.endpoints_url(pfm)
        data = {
            'callbacks' : callback_endpoints,
            'alias'     : None,
            'bridges'   : bridges,
            'mgr_type'  : 'sfm'
        }

        log.debug(f'subscribe_sfm: url={url}, data={data}') # Revisit: temp debug
        try:
            resp = requests.post(url, json=data)
        except Exception as err:
            resp = None
            log.debug(f'subscribe_sfm(): {err}')

        is_success = resp is not None and resp.status_code < 300

        if is_success:
            pfm.is_subscribed = True
            log.info(f'--- Subscribed to {url}, callbacks at {callback_endpoints}')
        else:
            log.error(f'---- Failed to subscribe to FM event! {url} {callback_endpoints} ---- ')
            if resp is not None:
                # Revisit: log the actual status message from the response
                log.error(f'subscription error reason [{resp.status_code}]: {resp.reason}')

    def unsubscribe_sfm(self, pfm: 'FM'):
        if not pfm.is_subscribed: # not subscribed
            return

        bridges = [br.cuuid_serial for br in self.bridges]

        url, callback_endpoints = self.endpoints_url(
            pfm, fm_endpoint='subscribe/unsubscribe')
        data = {
            'callbacks' : callback_endpoints,
            'alias'     : None,
            'bridges'   : bridges,
            'mgr_type'  : 'sfm'
        }

        log.debug(f'unsubscribe_sfm: url={url}, data={data}') # Revisit: temp debug
        try:
            resp = requests.post(url, json=data)
        except Exception as err:
            resp = None
            log.debug(f'unsubscribe_sfm(): {err}')

        is_success = resp is not None and resp.status_code < 300

        if is_success:
            pfm.is_subscribed = False
            log.info(f'--- Unsubscribed to {url}, callbacks at {callback_endpoints}')
        else:
            log.error(f'---- Failed to unsubscribe to FM event! {url} {callback_endpoints} ---- ')
            if resp is not None:
                # Revisit: log the actual status message from the response
                log.error(f'unsubscription error reason [{resp.status_code}]: {resp.reason}')

    def get_fm_topo(self, fm: 'FM'):
        url, _ = self.endpoints_url(fm, fm_endpoint='fabric/topology')
        r = requests.get(url=url) # Revisit: timeout
        data = r.json()
        pfm = data['graph'].get('pfm', None)
        sfm = data['graph'].get('sfm', None)
        mgr_uuids = data['graph'].get('mgr_uuids', [])
        # Revisit: check that pfm matches fm and sfm matches self.sfm
        topo = nx.node_link_graph(data)
        return (topo, pfm, sfm, mgr_uuids)

    def add_comps_from_topo(self, topo, pfm, sfm):
        for node in topo.nodes(data=True):
            cuuid_serial = node[0]
            attrs = node[1]
            nonce = self.decrypt_nonce(attrs['nonce'])
            update_sfm = False
            if cuuid_serial == self.sfm.cuuid_serial:
                log.debug(f'updating component for SFM local bridge {cuuid_serial}')
                del self.components[self.sfm.uuid]
                del self.cuuid_serial[cuuid_serial]
                del self.comp_gcids[self.sfm.gcid]
                brnum = self.sfm.brnum
                self.remove_node(self.sfm)
                update_sfm = True
            if cuuid_serial in self.cuuid_serial:
                log.debug(f'skipping known component {cuuid_serial}')
                continue
            cclass = attrs['cclass']
            gcid = GCID(str=attrs['gcids'][0])
            path = self.make_path(gcid)
            uuid = UUID(attrs['instance_uuid'])
            name = attrs.get('name', None)
            ps = int(attrs['rsp_page_grid_ps'])
            ts = attrs.get('mod_timestamp', None)
            if update_sfm:
                # Replace temp LocalBridge from sfm_init() with one having
                # the correct instance_uuid from PFM
                comp = LocalBridge(cclass, self, self.map, path,
                                   self.mgr_uuid, netlink=self.nl, nonce=nonce,
                                   local_br=True, brnum=brnum,
                                   gcid=gcid, uuid=uuid,
                                   verbosity=self.verbosity)
                self.nodes[comp]['gcids'] = [ str(comp.gcid) ]
                self.bridges[brnum] = comp
                self.set_sfm(comp)
            else:
                comp = Component(cclass, self, self.map, path,
                                 self.mgr_uuid, netlink=self.nl, nonce=nonce,
                                 gcid=gcid, uuid=uuid, br_gcid=self.sfm.gcid,
                                 verbosity=self.verbosity)
                gcid = self.assign_gcid(comp, proposed_gcid=gcid)
                if path.exists():
                    comp.remove_fab_comp(force=True)
                comp.add_fab_comp(setup=True)
            # Revisit: instead, call rsp_page_grid_init(readOnly=True)
            comp.rsp_page_grid_ps = ps
            self.update_mod_timestamp(comp, ts)
            comp.comp_init(None) # None: not PFM
            if cuuid_serial == pfm:
                self.set_pfm(comp)
            if name is not None:
                self.set_comp_name(comp, name)
        # end for node
        log.debug('finished adding components from PFM topology')

    def add_links_from_topo(self, topo):
        for edge in topo.edges(data=True):
            fr = self.cuuid_serial[edge[0]] # Revisit: unused
            to = self.cuuid_serial[edge[1]] # Revisit: unused
            attrs = edge[2]
            items = [x for x in attrs.items()]
            fr_uuid = UUID(items[0][0])
            to_uuid = UUID(items[1][0])
            fr_iface = self.components[fr_uuid].lookup_iface(items[0][1]['num'])
            to_iface = self.components[to_uuid].lookup_iface(items[1][1]['num'])
            fr_iface.iface_state(ts=items[0][1]['mod_timestamp'])
            to_iface.iface_state(ts=items[1][1]['mod_timestamp'])
            self.add_link(fr_iface, to_iface)
        # end for

    def add_mgr_uuids(self, mgr_uuids):
        for idx, m in enumerate(mgr_uuids):
            mgr_uuid = UUID(m)
            self.graph['mgr_uuids'].append(mgr_uuid)
            if idx == 0:
                self.mgr_uuid = mgr_uuid
                self.conf.set_fab(self)

    def get_fm_routes(self, fm: 'FM'):
        url, _ = self.endpoints_url(fm, fm_endpoint='fabric/routes')
        r = requests.get(url=url) # Revisit: timeout
        data = r.json()
        fab_uuid = data.get('fab_uuid', None)
        if fab_uuid is not None:
            fab_uuid = UUID(fab_uuid)
        if fab_uuid is None or fab_uuid != self.fab_uuid:
            log.warning(f'get_fm_routes: wrong FM fab_uuid {fab_uuid}')
            return None
        route_data = data.get('routes', None)
        self.routes.parse(route_data, self, fab_rts=self.routes)
        return self.routes

    def get_fm_resources(self, fm: 'FM') -> None:
        url, _ = self.endpoints_url(fm, fm_endpoint='fabric/resources')
        r = requests.get(url=url) # Revisit: timeout
        data = r.json()
        fab_uuid = data.get('fab_uuid', None)
        if fab_uuid is not None:
            fab_uuid = UUID(fab_uuid)
        if fab_uuid is None or fab_uuid != self.fab_uuid:
            log.warning(f'get_fm_resources: wrong FM fab_uuid {fab_uuid}')
            return None
        res_data = data.get('fab_resources', None)
        ts = data.get('mod_timestamp', None)
        self.conf.fab_resources(res_data, ts=ts)

    def get_fm_endpoints(self, fm: 'FM') -> None:
        url, _ = self.endpoints_url(fm, fm_endpoint='fabric/endpoints')
        r = requests.get(url=url) # Revisit: timeout
        data = r.json()
        fab_uuid = data.get('fab_uuid', None)
        if fab_uuid is not None:
            fab_uuid = UUID(fab_uuid)
        if fab_uuid is None or fab_uuid != self.fab_uuid:
            log.warning(f'get_fm_endpoints: wrong FM fab_uuid {fab_uuid}')
            return None
        now = time.time_ns()
        cur_ts = data.get('cur_timestamp', now)
        mod_ts = data.get('mod_timestamp', now)
        ep_data = data.get('endpoints', {})
        self.mainapp.callbacks.set_fm_endpoints(ep_data, cur_ts, mod_ts)

    def send_mgrs(self, mgr_types: List[str], callback: str, item: str, js,
                  op=None, invertTypes=False):
        callbacks = self.mainapp.callbacks.get_callbacks(mgr_types, callback,
                                                         invertTypes=invertTypes)
        hdrs = {'Content-type': 'application/json', 'Accept': 'text/plain'}
        data = {
            'fabric_uuid'   : str(self.fab_uuid),
            'mgr_uuid'      : str(self.mgr_uuid),
            'cur_timestamp' : time.time_ns(),
            f'{item}'       : js,
        }
        if op is not None:
            data['operation'] = op
        log.debug(f'send_mgrs: data={data}') # Revisit: temp debug
        for url in callbacks:
            try:
                # We have to convert to json ourselves because if we try to let
                # requests do it, it doesn't get our magic to_json() stuff
                resp = requests.post(url, data=json.dumps(data), headers=hdrs)
            except Exception as err:
                resp = None
                log.debug(f'send_mgrs(): {err}')
        # end for url
        # Revisit: error handling

    def send_sfm(self, callback: str, item: str, js, op=None):
        if self.sfm is None: # no SFM
            return
        url = self.mainapp.callbacks.get_endpoints(self.sfm.cuuid_serial,
                                                   'sfm')['callbacks'][callback]
        data = {
            'fabric_uuid'   : str(self.fab_uuid),
            'mgr_uuid'      : str(self.mgr_uuid),
            'cur_timestamp' : time.time_ns(),
            f'{item}'       : js,
        }
        if op is not None:
            data['operation'] = op
        log.debug(f'send_sfm: url={url}, data={data}') # Revisit: temp debug
        try:
            resp = requests.post(url, json=data)
        except Exception as err:
            resp = None
            log.debug(f'send_sfm(): {err}')

        is_success = resp is not None and resp.status_code < 300
        # Revisit: finish this

    def zeroconf_update(self):
        mainapp = self.mainapp
        prev_info = mainapp.zeroconfInfo
        props = prev_info.properties
        props['pfm'] = 1
        # Revisit: refactor - duplicates zeroconf_register
        new_info = ServiceInfo(
            '_genz-fm._tcp.local.',
            f'zephyr{self.fabnum}.{mainapp.hostname}._genz-fm._tcp.local.',
            addresses=[socket.inet_aton(mainapp.ip)],
            port=mainapp.port,
            properties=props,
            server=f'{mainapp.hostname}.local.'
        )
        mainapp.zeroconf.update_service(new_info)
        mainapp.zeroconfInfo = new_info

    def promote_sfm_to_pfm(self):
        first = self.promote_sfm_refcount.inc()
        log.debug(f'promote_sfm_to_pfm: first={first}')
        if not first:
            return
        log.warning(f'promoting SFM {self.sfm} to PFM')
        zephyr_conf.is_sfm = False
        # cancel heartbeat
        self.heartbeat.stop()
        # install SFM as PFM in every component, remove SFM
        # from every component, remove PFM routes
        for comp in self.components.values():
            comp.promote_sfm_to_pfm(self.sfm, self.pfm)
        # update zeroconf
        self.zeroconf_update()
        # save assigned CIDs
        self.conf.save_assigned_cids()
        # Revisit: ask llamas on former-PFM to remove all fabric components?
        self.pfm, self.sfm = self.sfm, None
        self.graph['pfm'], self.graph['sfm'] = self.pfm, self.sfm
        self.pfm_fm = None
        self.send_mgrs(['llamas', 'sfm'], 'mgr_topo', 'graph', self.graph,
                       op='change', invertTypes=True)

    def check_pfm(self, fm: 'FM'):
        url, _ = self.endpoints_url(fm, fm_endpoint='fabric/topology')
        # just get the HEAD - no data needed
        try:
            # Revisit: use requests.Session & HTTPAdapter to retry before giving up
            r = requests.head(url=url, timeout=1) # Revisit: timeout hardcoded
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            self.promote_sfm_to_pfm()

    def check_connectivity(self, br_gcid_val, sgcid_val, dgcid_val):
        '''Check the ~20 things that could prevent successful communication
        between sgcid & dgcid.
        '''
        code = 200
        br_gcid = GCID(val=br_gcid_val)
        sgcid = GCID(val=sgcid_val)
        dgcid = GCID(val=dgcid_val)
        # Revisit: until HW supports ControlNOP generation on requesters,
        # the sgcid must equal br_gcid
        if br_gcid != sgcid:
            resp = { 'error' : 'sgcid must match br_gcid.' }
            return (resp, 404)
        resp = { 'status': 'not implemented' }
        return (resp, code)


class RepeatedTimer(sched.scheduler):
    def __init__(self, interval, function, *args, **kwargs):
        super().__init__() # defaults to time.monotonic/time.sleep
        self._event     = None
        self._thread    = None
        self.interval   = interval
        self.function   = function
        self.args       = args
        self.kwargs     = kwargs
        self.is_running = False

    def _thread_run(self):
        log.debug(f'RepeatedTimer started @ {time.monotonic()}')
        while self.is_running:
            if self._event is None:
                # self.function will be called after delay of self.interval
                self._event = self.enter(self.interval, 1, self.function,
                                         argument=self.args, kwargs=self.kwargs)
            else:
                # guarantee no drift by using enterabs with previous event time + interval
                self._event = self.enterabs(self._event.time + self.interval, 1,
                                            self.function,
                                            argument=self.args, kwargs=self.kwargs)
            self.run()  # wait for _event
        # end while

    def start(self, interval=None):
        if interval is not None: # override the interval from __init__ if desired
            self.interval = interval
        if self._thread is None:
            self._thread = Thread(target=self._thread_run, daemon=True)
        if not self.is_running: # if already started, do nothing
            self.is_running = True
            self._thread.start()

    def stop(self):
        self.is_running = False # current thread will exit while loop
        self._thread = None     # next start() will create new thread
        try:
            self.cancel(self._event)
        except ValueError:      # if _event is not valid
            pass


class FM():
    def __init__(self, info: ServiceInfo):
        self.is_subscribed = False
        self.info = info
        self.addresses = info.parsed_scoped_addresses()
        if info.properties:
            self.fab_uuid = UUID(bytes=info.properties[b'fab_uuid'])
            self.mgr_uuid = UUID(bytes=info.properties[b'mgr_uuid'])
            self.instance_uuid = UUID(bytes=info.properties[b'instance_uuid'])
            self.pfm = bool(int(info.properties[b'pfm']))
        self.bridges = []

    @property
    def port(self):
        return self.info.port

    @property
    def name(self):
        return self.info.name

    def __hash__(self): # Revisit: do we need this?
        return hash(self.name)
