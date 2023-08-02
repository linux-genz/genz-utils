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
import time
from uuid import UUID, uuid4
from genz.genz_common import GCID, CState, IState, RKey, PHYOpStatus, ErrSeverity
from copy import deepcopy
from pdb import set_trace
from typing import List, NamedTuple, Optional
from collections import defaultdict
from intervaltree import Interval, IntervalTree
from sortedcontainers import SortedSet
from operator import neg
from math import ceil
from zephyr_conf import log
from zephyr_comp import Component, NO_ACCESS_RKEY, DEFAULT_RKEY
from zephyr_route import RoutesTuple

DynamicRKey = -1 # assign a dynamic RKey

class ChunkTuple(NamedTuple):
    start:   int
    length:  int
    type:    int
    ro_rkey: RKey
    rw_rkey: RKey

    def to_json(self):
        return {'start': self.start, 'length': self.length, 'type': self.type,
                'ro_rkey': int(self.ro_rkey), 'rw_rkey': int(self.rw_rkey)}

class Chunks():
    def __init__(self):
        # We use a list so we can index it; expected length is 1, sometimes 2
        self.chunks = defaultdict(list)  # key: ChunkTuple, val: list of zaddrs

    def add(self, chunk: ChunkTuple, zaddr: int = None):
        if zaddr is None:
            self.chunks[chunk]
        else:
            self.add_za(chunk, zaddr)

    def add_za(self, chunk: ChunkTuple, zaddr: int):
        if zaddr not in self.chunks[chunk]: # guarantee uniqeness
            self.chunks[chunk].append(zaddr)

    def remove_za(self, chunk: ChunkTuple, zaddr: int):
        if zaddr in self.chunks[chunk]:
            self.chunks[chunk].remove(zaddr)

    @property
    def total_size(self):
        return sum(ch.length for ch in self.chunks)

    def __iter__(self):
        return iter(self.chunks)

    def __len__(self):
        return len(self.chunks)

class Resource():
    def __init__(self, res_list: 'ResourceList', res_dict: dict,
                 readOnly=False):
        self.res_list = res_list
        self.res_dict = res_dict
        if res_dict['instance_uuid'] == '???':
                res_dict['instance_uuid'] = str(uuid4())
        self.instance_uuid = UUID(res_dict['instance_uuid'])
        self.chunks = Chunks()
        for mem in res_dict['memory']:
            if mem['rw_rkey'] == DynamicRKey:
                mem['rw_rkey'] = res_list.rw_rkey
            if mem['ro_rkey'] == DynamicRKey:
                mem['ro_rkey'] = NO_ACCESS_RKEY # Revisit: RO not yet supported
            chunk = ChunkTuple(**mem)
            self.chunks.add(chunk)
        # end for
        self.it = self.producer.producer.rsp_pte_alloc(self, readOnly=readOnly)

    @property
    def producer(self):
        return self.res_list.producer

    @property
    def consumers(self):
        return self.res_list.consumers

    @property
    def total_size(self):
        return self.chunks.total_size

    def to_json(self):
        return self.res_dict

    def __hash__(self):
        return hash(self.instance_uuid)


class ResourceList():
    def __init__(self, fab, resources: List[Resource], res_dict: dict,
                 readOnly=False, ts=None):
        self.fab = fab
        self.consumers = set()     # set of Components
        self.resources = resources # list of Resources
        self.res_dict = {}         # dict for to_json()
        self.res_routes = ResourceRoutes(self)
        self.parent = None
        self.rkd = None
        self.ro_rkey = None
        self.rw_rkey = None
        # Revisit: exception handling
        try:
            self.producer = fab.cuuid_serial[res_dict['producer']]
        except KeyError:
            log.warning('producer component {} not found in fabric{}'.format(
                res_dict['producer'], fab.fabnum))
            self.producer = None
            self.res_dict['resources'] = []
            return
        self.res_dict['producer']  = self.producer.cuuid_serial
        self.res_dict['consumers'] = []
        self.res_dict['gcid']      = self.producer.gcid.val
        self.res_dict['cclass']    = self.producer.cclass
        self.res_dict['serial']    = self.producer.serial
        self.res_dict['br_gcid']   = 0 # Revisit: MultiBridge
        self.res_dict['cuuid']     = str(self.producer.cuuid)
        self.res_dict['fru_uuid']  = str(self.producer.fru_uuid)
        self.res_dict['mgr_uuid']  = str(self.producer.mgr_uuid)
        self.res_dict['resources'] = [ res.to_json() for res in self.resources ]
        self.update_mod_timestamp(ts=ts)
        self.add_consumers(res_dict['consumers'], readOnly=readOnly)

    def update_mod_timestamp(self, ts=None):
        if ts is None:
            ts = time.time_ns()
        self.res_dict['mod_timestamp'] = ts
        if self.parent is not None:
            self.parent.mod_timestamp = max(self.parent.mod_timestamp, ts)

    def set_parent(self, parent, ts=None):
        self.parent = parent
        self.update_mod_timestamp(ts=ts)

    def append(self, res):
        self.resources.append(res)
        self.res_dict['resources'].append(res.to_json())
        self.update_mod_timestamp()

    def add_consumers(self, consumers, readOnly=False):
        prev_cons = self.consumers.copy()
        for cons in consumers:
            try:
                cons_comp = self.fab.cuuid_serial[cons]
            except KeyError:
                log.warning(f'consumer component {cons} not found in fabric{self.fab.fabnum}')
                continue
            if cons_comp not in self.consumers:
                # check that cons_comp is in the same partition as producer
                if cons_comp.partition != self.producer.partition:
                    set_trace() # Revisit: do what?
                self.res_dict['consumers'].append(cons_comp.cuuid_serial)
                self.consumers.add(cons_comp)
                self.update_mod_timestamp()
                if not readOnly:
                    routes = self.fab.setup_bidirectional_routing(
                        cons_comp, self.producer, res=True)
                    self.res_routes.add(cons_comp, routes)
        # end for cons
        if prev_cons != self.consumers and not readOnly:
            rkds = self.fab.rkds
            #set_trace() # Revisit: temp debug
            rkd, prev_rkd = rkds.assign_rkd(self, prev_cons) # Revisit: exception handling
            if rkd != prev_rkd:
                # Allocate new RKey - only RW access supported for now
                self.rw_rkey = rkds.alloc_rkey(rkd) # Revisit: exception handling
                if prev_rkd is not None:
                    # Revisit: this is wrong - must defer until all prev_cons
                    # have acknowleged that they've updated to the new RKey
                    rkds.release_rkd(res, prev_rkd)
            pass # Revisit: finish this

    def remove_consumers(self, res: Resource, consumers, ts=None):
        prev_cons = self.consumers.copy()
        for cons in consumers:
            try:
                cons_comp = self.fab.cuuid_serial[cons]
            except KeyError:
                log.warning(f'consumer component {cons} not found in fabric{self.fab.fabnum}')
                continue
            if cons_comp in self.consumers:
                self.res_dict['consumers'].remove(cons_comp.cuuid_serial)
                self.consumers.discard(cons_comp)
                self.update_mod_timestamp(ts=ts)
                self.res_routes.remove(cons_comp)
            else:
                log.warning(f'component {cons} not a consumer of resource {res}')
        # end for cons

    def to_json(self):
        # make deepcopy so later add/remove does not affect it
        return deepcopy(self.res_dict)

    def __iter__(self):
        return iter(self.resources)


class Resources():
    def __init__(self, fab: 'Fabric', resources: List[Resource] = []):
        self.fab = fab
        self.by_producer = defaultdict(set) # key: producer Component, val: ResourceList set
        self.by_consumer = defaultdict(set) # key: consumer Component, val: ResourceList set
        self.by_cons_prod = defaultdict(set) # key: (cons Comp, prod Comp), val: ResourceList set
        self.by_instance_uuid = {} # key: instance UUID, val: Resource
        self.mod_timestamp = time.time_ns()
        for res in resources:
            self.add(res)

    def add(self, res: Resource, ts=None) -> None:
        self.by_instance_uuid[res.instance_uuid] = res
        res_list = res.res_list
        res_list.set_parent(self, ts=ts)
        self.by_producer[res.producer].add(res_list)
        for cons in res.consumers:
            self.by_consumer[cons].add(res_list)
            self.by_cons_prod[(cons, res.producer)].add(res_list)
        # end for

    def remove(self, res: Resource, ts=None) -> None:
        res.producer.producer.rsp_pte_free(res)
        del self.by_instance_uuid[res.instance_uuid]
        res_list = res.res_list
        res_list.set_parent(self, ts=ts)
        self.by_producer[res.producer].remove(res_list)
        for cons in res.consumers:
            self.by_consumer[cons].remove(res_list)
            self.by_cons_prod[(cons, res.producer)].remove(res_list)

    def unreachable(self, cons: Component, prod: Component):
        unreach_res = self.by_cons_prod[(cons, prod)]
        unreach_dict = { 'fab_uuid': str(self.fab.fab_uuid),
                         'cur_timestamp': time.time_ns(),
                         'consumer': cons.cuuid_serial,
                         'producer': prod.cuuid_serial,
                         'resources': [res.to_json() for res in unreach_res]
                        }
        return unreach_dict

    def to_json(self):
        res_dict = { 'fab_uuid': str(self.fab.fab_uuid),
                     'cur_timestamp': time.time_ns(),
                     'mod_timestamp': self.mod_timestamp,
                     'fab_resources': [ res.to_json() for prod in self.by_producer.values() for res in prod ]
                    }
        return res_dict

class ToFr(NamedTuple):
    to: set
    fr: set

class ResourceRoutes():
    '''Track the Routes used by a ResourceList
    '''
    def __init__(self, rl: ResourceList):
        self.rl = rl
        # key: consumer Component, val: ToFr[to: Route set, fr: Route set]
        self.by_consumer = defaultdict(lambda: ToFr(set(), set()))

    def add(self, cons: Component, rts: RoutesTuple):
        for rt in rts.all_to:
            self.by_consumer[cons].to.add(rt)
        for rt in rts.all_from:
            self.by_consumer[cons].fr.add(rt)

    def remove(self, cons: Component): # Revisit: import Component?
        fab = cons.fab
        routes = self.by_consumer[cons]
        fab.teardown_routing(cons, self.rl.producer, routes=routes.to)
        fab.teardown_routing(self.rl.producer, cons, routes=routes.fr)

class Producer():
    def __init__(self, comp: Component):
        self.comp = comp
        self.chunks = Chunks()
        self.tree = IntervalTree()
        self.ps = comp.rsp_page_grid_ps
        self.pte_cnt = comp.pte_cnt

    def rsp_pte_alloc(self, res: Resource, readOnly=False) -> Interval:
        it = self.find_pte_range(res)
        if it is None:
            raise ValueError(f'insufficient space on {self.comp} for {res}') # Revisit: better exception
        ps_bytes = 1 << self.ps
        zaddr = it.begin * ps_bytes
        res_mem = { 'start': zaddr, 'length': res.chunks.total_size }
        for i, ch in enumerate(res.chunks):
            if i == 0:
                res_mem['type'] = ch.type
                res_mem['ro_rkey'] = ch.ro_rkey
                res_mem['rw_rkey'] = ch.rw_rkey
            else:
                if (res_mem['type'] != ch.type or
                    res_mem['ro_rkey'] != ch.ro_rkey or
                    res_mem['rw_rkey'] != ch.rw_rkey):
                    raise ValueError('incompatible chunk type or RKey')
            self.chunks.add_za(ch, zaddr)
            # write the rsp PTEs
            self.comp.rsp_pte_update(ch, zaddr, self.ps, valid=1)
            ch_page_count = ceil(ch.length / ps_bytes)
            zaddr += (ch_page_count * ps_bytes)
        # end for
        # replace multiple memory ranges with one contiguous one in ZA space
        res.res_dict['memory'] = [ res_mem ]
        return it

    def rsp_pte_free(self, res: Resource, readOnly=False) -> None:
        set_trace() # Revisit: temp debug
        for ch in res.chunks:
            za_list = list(self.chunks.chunks[ch]) # copy to iterate over
            for zaddr in za_list:
                self.chunks.remove_za(ch, zaddr)
                # invalidate the rsp PTEs
                self.comp.rsp_pte_update(ch, zaddr, self.ps, valid=0)
        # remove the resource interval
        self.tree.remove(res.it)

    def find_pte_range(self, res: Resource) -> Optional[Interval]:
        # compute Resource page_count
        total_size = res.total_size
        if total_size <= 0:
            raise ValueError(f'invalid resource total_size {total_size}')
        page_count = ceil(total_size / (1 << self.ps))
        min_pte = 0
        max_pte = min_pte + self.pte_cnt - 1
        ss = SortedSet(self.tree.boundary_table, key=neg) # reversed
        for bo in ss:
            its = self.tree[bo] # either empty set or set with 1 Interval
            if its:
                it = its.pop()
                end_pte = it.end - 1
                if (max_pte - end_pte) >= page_count: # range above "it" works
                    min_pte = end_pte + 1
                    break
                else:
                    max_pte = it.begin - 1
        # end for
        if (max_pte - min_pte + 1) >= page_count: # found a range
            # add Interval to tree
            it = Interval(min_pte, min_pte + page_count, res)
            self.tree.add(it)
        else:
            it = None
        return it
