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
from pdb import set_trace
from itertools import product
import bisect
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

class RouteElement():
    def __init__(self, comp: Component,
                 ingress_iface: Interface, egress_iface: Interface,
                 to_iface: Interface = None, rt_num: int = None,
                 hc: int = 0):
        self.comp = comp
        self.ingress_iface = ingress_iface # optional: which lprt to write
        self.egress_iface = egress_iface   # required
        self.to_iface = to_iface           # optional: the peer of egress_iface
        self.dr = False
        self.rt_num = rt_num
        self.hc = hc
        # Revisit: vca

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

    def set_ssdt(self, to: Component, valid=1, update_rt_num=False):
        if update_rt_num:
            self.route_entries_avail(self.comp, to)
        mhc, wr0 = self.comp.compute_mhc(to.gcid.cid, self.rt_num,
                                         self.hc, valid)
        # Revisit: vca
        self.comp.ssdt_write(to.gcid.cid, self.egress_iface.num,
                             rt=self.rt_num, valid=valid, mhc=mhc, hc=self.hc)
        # Revisit: ok to do 2 independent writes? Which order?
        if wr0:
            self.comp.ssdt_write(0, 0, mhc=mhc, mhcOnly=True)

    def set_lprt(self, to: Component, valid=1):
        mhc, wr0 = self.ingress_iface.compute_mhc(to.gcid.cid, self.rt_num,
                                                  self.hc, valid)
        # Revisit: vca
        self.ingress_iface.lprt_write(to.gcid.cid, self.egress_iface.num,
                                      rt=self.rt_num, valid=valid, mhc=mhc,
                                      hc=self.hc)
        # Revisit: ok to do 2 independent writes? Which order?
        if wr0:
            self.ingress_iface.lprt_write(0, 0, mhc=mhc, mhcOnly=True)

    def to_json(self):
        return str(self)

    def __eq__(self, other):
        return (self.comp == other.comp and
                self.ingress_iface == other.ingress_iface and
                self.egress_iface == other.egress_iface and
                self.to_iface == other.to_iface and
                self.dr == other.dr)

    def __str__(self):
        # Revisit: handle self.dr and vca
        return ('{}->{}'.format(self.egress_iface, self.to_iface)
                if self.to_iface else '{}'.format(self.egress_iface))

class DirectedRelay(RouteElement):
    def __init__(self, dr_comp: Component,
                 ingress_iface: Interface, dr_iface: Interface):
        super().__init__(dr_comp, ingress_iface, dr_iface)
        self.dr = True

class RouteInfo():
    def __init__(self):
        self.routes = set() # Revisit: Route or RouteElem?

    def add_route(self, route: 'Route') -> int:
        self.routes.add(route)
        return len(self.routes)

    def remove_route(self, route: 'Route') -> int:
        self.routes.discard(route)
        return len(self.routes)

class Route():
    def __init__(self, path: List[Component], elems: List[RouteElement] = None):
        path_len = len(path)
        if path_len < 2:
            raise(IndexError)
        self._path = path
        self._elems = [] if elems is None else elems
        self.ifaces = set()
        ingress_iface = None
        if elems is None:
            hc = path_len - 2
            for fr, to in moving_window(2, path):
                edge_data = fr.fab.get_edge_data(fr, to)[0]
                egress_iface = edge_data[str(fr.uuid)]
                to_iface = edge_data[str(to.uuid)]
                elem = RouteElement(fr, ingress_iface, egress_iface, to_iface,
                                    hc=hc)
                self._elems.append(elem)
                self.ifaces.add(egress_iface)
                self.ifaces.add(to_iface)
                ingress_iface = to_iface
                hc -= 1
            # end for
        else:
            for elem in elems:
                # fixup ingress_iface
                elem.ingress_iface = ingress_iface
                self.ifaces.add(elem.egress_iface)
                self.ifaces.add(elem.to_iface)
                ingress_iface = elem.to_iface
            # end for
        # end if

    @property
    def fr(self):
        return self._path[0]

    @property
    def to(self):
        return self._path[-1]

    @property
    def hc(self):
        return len(self) - 1

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
        if fab.route_entries_avail(inverse):
            fab.route_info_update(inverse, True)
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
        return self._elems

    def __getitem__(self, key):
        return self._elems[key]

    def __len__(self):
        return len(self._elems)

    def __iter__(self):
        return iter(self._elems)

    def __hash__(self):
        return hash(repr(self))

    def __eq__(self, other): # all elements in list must match
        return self._elems == other._elems

    def __lt__(self, other): # only compare route length (hop count)
        # Revisit: consider bandwidth & latency
        return len(self) < len(other)

    def __repr__(self):
        return '(' + ','.join('{}'.format(e) for e in self._elems) + ')'

class Routes():
    def __init__(self, fab_uuid=None):
        self.fab_uuid = fab_uuid
        self.fr_to = {}  # key: (fr:Component, to:Component)
        self.ifaces = {} # key: Interface

    def get_routes(self, fr: Component, to: Component) -> List[Route]:
        return self.fr_to[(fr, to)]

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

    def add(self, fr: Component, to: Component, route: Route) -> None:
        try:
            rts = self.get_routes(fr, to)
            for rt in rts:
                if rt == route: # already there
                    return
            # end for
            # not in list - add it - at the proper place
            bisect.insort(rts, route)
        except KeyError: # not in dict - add
            self.fr_to[(fr, to)] = [ route ]
        self.add_ifaces(route)

    def remove(self, fr: Component, to: Component, route: Route) -> bool:
        try:
            rts = self.get_routes(fr, to)
            rts.remove(route)
        except (KeyError, ValueError):
            return False
        self.remove_ifaces(route)
        return True

    def impacted(self, iface: Interface):
        try:
            # return a copy of the ifaces[iface] set in order to avoid
            # RuntimeError: Set changed size during iteration
            # in iface_unusable()
            return self.ifaces[iface].copy()
        except KeyError:
            return []

    def to_json(self):
        routes_dict = {}
        for k, v in self.fr_to.items():
            routes_dict[str(k[0]) + '->' + str(k[1])] = v
        top_dict = { 'fab_uuid': str(self.fab_uuid),
                     'routes': routes_dict
                    }
        js = json.dumps(top_dict, indent=2) # Revisit: indent
        return js

    def __str__(self):
        r = 'fab_uuid: {}, '.format(self.fab_uuid)
        r += 'routes: {}'.format(self.fr_to)
        return '{' + r + '}'
