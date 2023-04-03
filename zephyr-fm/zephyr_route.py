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
import re
from typing import List, Tuple, NamedTuple
from genz.genz_common import GCID, CState, IState, RKey, PHYOpStatus, ErrSeverity, RefCount
from pdb import set_trace
from collections import Counter
from itertools import product
import bisect
import time
from zephyr_conf import log
from zephyr_iface import Interface
from zephyr_comp import Component

def moving_window(n, iterable):
    # return "n" items from iterable at a time, advancing 1 item per call
    start, stop = 0, n
    while stop <= len(iterable):
        yield iterable[start:stop]
        start += 1
        stop += 1

class RouteElementTuple(NamedTuple):
    comp: Component
    ingress_iface: Interface
    egress_iface: Interface
    to_iface: Interface = None
    hc: int = 0
    dr: bool = False
    vca: int = 0

class RouteElement():
    def __init__(self, comp: Component,
                 ingress_iface: Interface, egress_iface: Interface,
                 to_iface: Interface = None, hc: int = 0, dr: bool = False):
        self._tuple = RouteElementTuple(comp, ingress_iface, egress_iface,
                                        to_iface, hc, dr)
        self.rt_num = None  # the only mutable field; not included in hash

    @property
    def comp(self):
        return self._tuple.comp

    @property
    def ingress_iface(self):
        return self._tuple.ingress_iface

    @property
    def egress_iface(self):
        return self._tuple.egress_iface

    @property
    def to_iface(self):
        return self._tuple.to_iface

    @property
    def hc(self):
        return self._tuple.hc

    @property
    def dr(self):
        return self._tuple.dr

    @property
    def gcid(self):
        return self.comp.gcid

    @property
    def rit_only(self):
        return self.ingress_iface is None and self.comp.rit_only

    @property
    def path(self):
        return self.egress_iface.iface_dir

    def route_entries_avail(self, fr: Component, to: Component) -> bool:
        '''Major side effect: sets self.rt_num if avail'''
        # Revisit: Subnets
        cid = to.gcid.cid
        if self.rit_only:
            return True
        if self.ingress_iface is None: # SSDT
            fr.ssdt_read()
            row = fr.ssdt[cid]
        else: # LPRT
            self.ingress_iface.lprt_read()
            row = self.ingress_iface.lprt[cid]
        found = None
        free = None
        for i in range(len(row)):
            # Revisit: cannot share if VCA's differ
            if row[i].V == 1 and row[i].EI == self.egress_iface.num:
                found = i
                break
            elif row[i].V == 0 and free is None:
                free = i
        # end for
        if found is None and free is None:
            return False
        elif found is not None: # use existing matching entry
            self.rt_num = found
        else: # new entry
            self.rt_num = free
        return True

    def route_info_update(self, to: Component, add: bool):
        cid = to.gcid.cid
        if self.rit_only:
            return # No route info to update
        elif self.ingress_iface is None: # SSDT
            info = self.comp.route_info[cid][self.rt_num]
        else: # LPRT
            info = self.ingress_iface.route_info[cid][self.rt_num]
        if add:
            info.add_route(self)
        else:
            info.remove_route(self)

    def set_ssdt(self, to: Component, valid=1, updateRtNum=False,
                 refcountOnly=False):
        comp = self.comp
        if comp.ssdt is None:
            return
        dcid = (to.tmp_gcid.cid if (not valid and to.tmp_gcid is not None)
                else to.gcid.cid)
        if updateRtNum:
            self.route_entries_avail(comp, to)
            self.route_info_update(to, valid)
        if refcountOnly:
            return
        if comp.is_unreachable(comp.fab.pfm):
            log.debug(f'set_ssdt: {comp} is unreachable from PFM') # Revisit: debug
            return
        mhc, hc, v, wr0, wrN = comp.compute_mhc_hc(dcid, self.rt_num,
                                                   self.hc, valid)
        # Revisit: vca
        if wrN:
            comp.ssdt_write(dcid, self.egress_iface.num,
                            rt=self.rt_num, valid=v, mhc=mhc, hc=hc)
        if wr0:
            comp.ssdt_write(dcid, 0, mhc=mhc, mhcOnly=True)

    def set_lprt(self, to: Component, valid=1, updateRtNum=False,
                 refcountOnly=False):
        comp = self.comp
        iface = self.ingress_iface
        dcid = (to.tmp_gcid.cid if (not valid and to.tmp_gcid is not None)
                else to.gcid.cid)
        if updateRtNum:
            self.route_entries_avail(comp, to)
            self.route_info_update(to, valid)
        if refcountOnly:
            return
        if comp.is_unreachable(comp.fab.pfm):
            log.debug(f'set_lprt: {comp} is unreachable from PFM') # Revisit: debug
            return
        mhc, hc, v, wr0, wrN = iface.compute_mhc_hc(dcid, self.rt_num,
                                                    self.hc, valid)
        # Revisit: vca
        if wrN:
            iface.lprt_write(dcid, self.egress_iface.num,
                             rt=self.rt_num, valid=v, mhc=mhc, hc=hc)
        if wr0:
            iface.lprt_write(dcid, 0, mhc=mhc, mhcOnly=True)

    def to_json(self):
        return str(self)

    def __eq__(self, other):
        if not isinstance(other, RouteElement):
            return NotImplemented
        return self._tuple == other._tuple

    def __lt__(self, other):
        '''Used for ordering Routes by gcid, egress_iface, dr.
        '''
        if not isinstance(other, RouteElement):
            return NotImplemented
        return (self != other and
                (self.gcid < other.gcid or
                 self.egress_iface < other.egress_iface or
                 self.dr < other.dr))

    def __hash__(self):
        return hash(self._tuple)

    def __str__(self):
        # Revisit: handle vca
        return (f'{self.egress_iface}(DR)' if self.dr else
                f'{self.egress_iface}->{self.to_iface}'
                if self.to_iface else f'{self.egress_iface}')

class DirectedRelay(RouteElement):
    def __init__(self, dr_comp: Component,
                 ingress_iface: Interface, dr_iface: Interface,
                 to_iface: Interface = None):
        super().__init__(dr_comp, ingress_iface, dr_iface, to_iface=to_iface,
                         dr=True)

class RouteInfo(Counter):
    '''Every SSDT and LPRT entry has a RouteInfo to keep track of
    all RouteElements that make use of that entry.
    '''
    def add_route(self, elem: RouteElement) -> int:
        self[elem] += 1
        return len(self) # Revisit: total()?

    def remove_route(self, elem: RouteElement) -> int:
        self[elem] -= 1
        if self[elem] <= 0:
            del self[elem]
        return len(self) # Revisit: total()?

    def min_hc(self) -> int:
        # Revisit: maintain min_hc on each add/remove, so this is O(1) not O(N)
        return None if len(self) == 0 else min(self.keys(), key=lambda x: x.hc).hc

class Route():
    def __init__(self, path: List[Component], elems: List[RouteElement] = None,
                 noDR: bool = False):
        path_len = len(path)
        if path_len < 2:
            raise(IndexError)
        self._path = path
        self.ifaces = set()
        self.refcount = RefCount()
        ingress_iface = None
        hc = path_len - 2
        telems = [] # temporary list
        if elems is None:
            for fr, to in moving_window(2, path):
                edge_data = fr.fab.get_edge_data(fr, to)[0]
                egress_iface = edge_data[str(fr.uuid)]
                to_iface = edge_data[str(to.uuid)]
                # never generate a DR route
                elem = RouteElement(fr, ingress_iface, egress_iface, to_iface,
                                    hc=hc)
                telems.append(elem)
                self.ifaces.add(egress_iface)
                self.ifaces.add(to_iface)
                ingress_iface = to_iface
                hc -= 1
            # end for
        else:
            for e in elems:
                if hc > 0: # only the last element can be DR
                    assert not e.dr
                # copy e.dr unless noDR is True
                elem = RouteElement(e.comp, ingress_iface, e.egress_iface,
                                    to_iface=e.to_iface, hc=hc,
                                    dr=0 if noDR else e.dr)
                telems.append(elem)
                self.ifaces.add(e.egress_iface)
                self.ifaces.add(e.to_iface)
                ingress_iface = e.to_iface
                hc -= 1
            # end for
        # end if
        self._elems = tuple(telems)  # _elems is immutable for hash

    @property
    def path(self):
        return self._path

    @property
    def elems(self):
        return self._elems

    @property
    def fr(self):
        return self._path[0]

    @property
    def to(self):
        return self._path[-1]

    @property
    def hc(self):
        return len(self) - 1

    @property
    def is_dr(self):
        return self._elems[-1].dr

    def route_entries_avail(self) -> bool:
        fr = self.fr
        to = self.to
        for elem in self:
            if not elem.route_entries_avail(fr, to):
                return False
        return True

    def route_info_update(self, add: bool):
        to = self.to
        for elem in self:
            try:
                elem.route_info_update(to, add)
            except TypeError:
                log.error(f'route_info_update failed: to={to}, elem={elem}, rt_num={elem.rt_num}')
        # end for

    def invert(self, fab: 'Fabric') -> 'Route':
        # MultiGraph - this guarantees identical links
        elems = []
        ingress_iface = None
        hc = self.hc
        for e in reversed(self._elems):
            fr = e.to_iface.comp
            elem = RouteElement(fr, ingress_iface, e.to_iface, e.egress_iface,
                                hc=hc)
            elems.append(elem)
            ingress_iface = e.egress_iface
            hc -= 1
        # end for
        inverse = Route(self._path[::-1], elems=elems)
        if inverse.route_entries_avail():
            inverse.route_info_update(True)
        else:
            inverse = None
        return inverse

    def multigraph_routes(self) -> List['Route']:
        path_len = len(self._path)
        mg_list = []
        ingress_iface = None
        hc = path_len - 2
        for fr, to in moving_window(2, self._path):
            elem_list = []
            multigraph = fr.fab.get_edge_data(fr, to)
            for edge_data in multigraph.values():
                egress_iface = edge_data[str(fr.uuid)]
                to_iface = edge_data[str(to.uuid)]
                elem = RouteElement(fr, ingress_iface, egress_iface, to_iface,
                                    hc=hc)
                elem_list.append(elem)
            ingress_iface = to_iface # not always right - fixed by Route()
            hc -= 1
            mg_list.append(elem_list)
        mg_combs = product(*mg_list)
        rts = []
        for mg in mg_combs:
            rt = Route(self._path, elems=list(mg))
            if self != rt: # skip original route
                rts.append(rt)
        return rts

    def to_json(self):
        return [e.to_json() for e in self._elems]

    def __getitem__(self, key):
        return self._elems[key]

    def __len__(self):
        return len(self._elems)

    def __iter__(self):
        return iter(self._elems)

    def __hash__(self):
        return hash(self._elems)

    def __eq__(self, other): # all elements in list must match
        if not isinstance(other, Route):
            return NotImplemented
        return self._elems == other._elems

    def __lt__(self, other): # first compare route length (hop count)
        # Revisit: consider bandwidth & latency
        if not isinstance(other, Route):
            return NotImplemented
        self_len = len(self)
        other_len = len(other)
        if self_len != other_len:
            return self_len < other_len
        # if lengths are the same, order by comparing all route elements
        return self._elems < other._elems

    def __repr__(self):
        return '(' + ','.join('{}'.format(e) for e in self._elems) + ')'

class RoutesTuple(NamedTuple):
    new_to:   List[Route]
    new_from: List[Route]
    all_to:   List[Route]
    all_from: List[Route]

class Routes():
    def __init__(self, fab_uuid=None, routes=None):
        self.fab_uuid = fab_uuid
        self.fr_to = {}  # key: (fr:Component, to:Component)
        self.ifaces = {} # key: Interface
        self.mod_timestamp = time.time_ns()
        if routes is not None:
            for rt in routes:
                self.add(rt.fr, rt.to, route=rt)

    def get_routes(self, fr: Component, to: Component) -> List[Route]:
        return [] if fr is to else self.fr_to[(fr, to)]['route_list']

    def add_ifaces(self, route: Route) -> None:
        for iface in route.ifaces:
            try:
                rts = self.ifaces[iface]
            except KeyError:
                self.ifaces[iface] = rts = set()
            rts.add(route)
        #end for

    def remove_ifaces(self, route: Route) -> None:
        for iface in route.ifaces:
            rts = self.ifaces[iface]
            rts.discard(route)
        #end for

    def update_mod_timestamp(self, fr: Component, to: Component, ts=None) -> None:
        if ts is None:
            ts = time.time_ns()
        self.fr_to[(fr, to)]['mod_timestamp'] = ts
        self.mod_timestamp = max(self.mod_timestamp, ts)

    def add(self, fr: Component, to: Component, route: Route, ts=None) -> None:
        try:
            rts = self.get_routes(fr, to)
            for rt in rts:
                if rt == route: # already there
                    return
            # end for
            # not in list - add it - at the proper place
            bisect.insort(rts, route)
        except KeyError: # not in dict - add
            self.fr_to[(fr, to)] = { 'mod_timestamp': 0, 'route_list': [ route ] }
        self.add_ifaces(route)
        self.update_mod_timestamp(fr, to, ts=ts)

    def remove(self, fr: Component, to: Component, route: Route) -> bool:
        try:
            rts = self.get_routes(fr, to)
            rts.remove(route)
        except (KeyError, ValueError):
            return False
        self.remove_ifaces(route)
        self.update_mod_timestamp(fr, to)
        return True

    def impacted(self, iface: Interface):
        try:
            # return a copy of the ifaces[iface] set in order to avoid
            # RuntimeError: Set changed size during iteration
            # in iface_unusable()
            return self.ifaces[iface].copy()
        except KeyError:
            return []

    fr_to_re = re.compile(r'^(?P<fr_class>[\w]+)\((?P<fr_gcid>[^\)]+)\)->(?P<to_class>[\w]+)\((?P<to_gcid>[^\)]+)\)$')

    fr_to_iface_re = re.compile(r'^(?P<fr_gcid>[^\.]+)\.(?P<fr_iface>[\d]+)->(?P<to_gcid>[^\.]+)\.(?P<to_iface>[\d]+)$')

    def parse_fr_to(self, fr_to_str: str, fab):
        m = self.fr_to_re.match(fr_to_str)
        fr_class = m.group('fr_class') # Revisit: unused
        fr_gcid = GCID(str=m.group('fr_gcid'))
        fr = fab.comp_gcids[fr_gcid]
        to_class = m.group('to_class') # Revisit: unused
        to_gcid = GCID(str=m.group('to_gcid'))
        to = fab.comp_gcids[to_gcid]
        return (fr, to)

    def parse_fr_to_iface(self, fr_to_iface_str: str, fab):
        m = self.fr_to_iface_re.match(fr_to_iface_str)
        fr_gcid = GCID(str=m.group('fr_gcid'))
        fr_iface_num = int(m.group('fr_iface'))
        fr = fab.comp_gcids[fr_gcid]
        fr_iface = fr.interfaces[fr_iface_num]
        to_gcid = GCID(str=m.group('to_gcid'))
        to_iface_num = int(m.group('to_iface'))
        to = fab.comp_gcids[to_gcid]
        to_iface = to.interfaces[to_iface_num]
        return (fr_iface, to_iface)

    def parse_route(self, route_list: list, fab) -> Route:
        path = []
        elems = []
        ingress_iface = None
        hc = len(route_list) - 1
        for e in route_list:
            fr_iface, to_iface = self.parse_fr_to_iface(e, fab)
            path.append(fr_iface.comp)
            elem = RouteElement(fr_iface.comp, ingress_iface, fr_iface,
                                to_iface, hc=hc)
            elems.append(elem)
            ingress_iface = to_iface
            hc -= 1
        path.append(to_iface.comp)
        rt = Route(path, elems)
        return rt

    def parse(self, routes_dict: dict, fab, fab_rts=None):
        ret_dict = {}
        for k in routes_dict.keys():
            fr, to = self.parse_fr_to(k, fab)
            rts = Routes(fab.fab_uuid) if fab_rts is None else fab_rts
            mod_timestamp = routes_dict[k]['mod_timestamp']
            for rtl in routes_dict[k]['route_list']:
                rt = self.parse_route(rtl, fab)
                rts.add(fr, to, rt, ts=mod_timestamp)
            # end for rtl
            if fab_rts is None:
                ret_dict[(fr, to)] = rts
        # end for k
        return ret_dict

    def to_json(self):
        routes_dict = {}
        for k, v in self.fr_to.items():
            routes_dict[str(k[0]) + '->' + str(k[1])] = {
                'mod_timestamp': v['mod_timestamp'],
                'route_list': [r.to_json() for r in v['route_list']]
            }
        top_dict = { 'fab_uuid': str(self.fab_uuid),
                     'cur_timestamp': time.time_ns(),
                     'mod_timestamp': self.mod_timestamp,
                     'routes': routes_dict
                    }
        return top_dict

    def __str__(self):
        r = 'fab_uuid: {}, '.format(self.fab_uuid)
        # Revisit: mod_timestamp?
        r += 'routes: {}'.format(self.fr_to)
        return '{' + r + '}'

    def __iter__(self):
        for rts in self.fr_to.values():
            for rt in rts['route_list']:
                yield rt
