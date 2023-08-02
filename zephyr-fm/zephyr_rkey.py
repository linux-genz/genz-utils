#!/usr/bin/env python3

# Copyright  ©  2020-2023 IntelliProp Inc.
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
import random
from uuid import UUID, uuid4
from genz.genz_common import RKey
from copy import deepcopy
from pdb import set_trace
from typing import Iterable, List, NamedTuple, Tuple
from collections import defaultdict
from zephyr_conf import log
from zephyr_comp import Component, ALL_RKD, FM_RKD, FM_RKEY, NO_ACCESS_RKEY

class RKD():
    def __init__(self, comps: Iterable[Component], rkd: int,
                 readOnly=False):
        self.comps = frozenset() # set of req Components with RKD enabled
        self.rkd = rkd
        self.add_comps(comps, readOnly=readOnly)
        self.resources = set() # set of ResourceLists using this RKD
        self.assigned_rkeys = set()
        self.rkeys = [] # defer creation until first alloc_rkey()
        self.refill_rkeys = True

    def alloc_rkey(self) -> RKey:
        if self.refill_rkeys:
            # Revisit: find a method that doesn't require storing entire list
            # perhaps using the solutions by orange or aak318, here:
            # https://stackoverflow.com/questions/9755538/how-do-i-create-a-list-of-random-numbers-without-duplicates
            rkd = self.rkd
            # Revisit: limit os range for now to save time & memory
            min = 1 if rkd == ALL_RKD else 0
            #max = 1<<20
            max = 1<<10
            self.rkeys = [ RKey(rkd=rkd, os=n) for n in range(min, max)
                           if RKey(rkd=rkd, os=n) not in self.assigned_rkeys ]
            if rkd == FM_RKD:
                if FM_RKEY in self.rkeys:
                    self.rkeys.remove(FM_RKEY)
                if NO_ACCESS_RKEY in self.rkeys:
                    self.rkeys.remove(NO_ACCESS_RKEY)
            random.shuffle(self.rkeys)
            self.refill_rkeys = False
        # end if refill
        rkey = self.rkeys.pop() # IndexError when empty
        self.assigned_rkeys.add(rkey)
        return rkey

    def free_rkey(self, rkey: RKey) -> None:
        if not isinstance(rkey, RKey):
            raise TypeError('rkey is not an RKey')
        if rkey in self.rkeys or rkey not in self.assigned_rkeys:
            return
        self.assigned_rkeys.remove(rkey)
        self.rkeys.append(rkey)
        # swap free'd rkey (at [-1]) with a random element (could be itself)
        r = random.randint(0, len(self.rkeys) - 1)
        self.rkeys[r], self.rkeys[-1] = self.rkeys[-1], self.rkeys[r]

    def assign_rkey(self, rkey: RKey) -> None:
        '''Used by SFM when PFM tells it RKeys that have been assigned.
        '''
        if not isinstance(rkey, RKey):
            raise TypeError(f'rkey is not an RKey')
        if rkey in self.rkeys:
            self.rkeys.remove(rkey)
        self.assigned_rkeys.add(rkey)

    def add_comps(self, comps: Iterable[Component], readOnly=False):
        self.comps = self.comps.union(comps)
        if not readOnly:
            for comp in comps:
                comp.rkd_write(self, enable=True)

    def remove_comps(self, comps: Iterable[Component], readOnly=False):
        self.comps = self.comps.difference(comps)
        if not readOnly:
            for comp in comps:
                comp.rkd_write(self, enable=False)

    def add_resource(self, res: 'ResourceList'):
        self.resources.add(res)

    def remove_resource(self, res: 'ResourceList') -> bool:
        self.resources.remove(res)
        return not bool(self.resources) # True if empty

    def to_json(self):
        return { 'rkd': self.rkd, 'comps': [c.to_json() for c in self.comps],
                 'assigned_rkeys': list(self.assigned_rkeys) }

    def __repr__(self):
        return f'RKD({self.rkd:03x}, {self.comps})'

    def __hash__(self):
        return hash(self.rkd)

    def __eq__(self, other):
        if isinstance(other, RKD):
            return self.rkd == other.rkd
        return NotImplemented


class RKDs():
    # Revisit: timestamps
    def __init__(self, fab: 'Fabric', rkds: List[RKD] = [],
                 random_rkds=True):
        self.fab = fab
        self.by_comps = {} # key: frozenset(Components), val: RKD (>= 1)
        self.by_rkd = {}   # key: rkd, val: RKD
        self.by_comp = defaultdict(set) # key: Component, val RKD set
        self.refill_rkds = True
        self.random_rkds = random_rkds
        self.mod_timestamp = time.time_ns()
        for rkd in rkds:
            self.add(rkd)

    def add(self, rkd: RKD, ts=None) -> None:
        self.by_rkd[rkd.rkd] = rkd
        if rkd.rkd >= 1 and rkd.rkd < 0xfff: # RKDs 0 & 0xfff are special
            self.by_comps[rkd.comps] = rkd
        for comp in rkd.comps:
            self.by_comp[comp].add(rkd)

    def remove(self, rkd: RKD, ts=None) -> None:
        del self.by_rkd[rkd.rkd]
        if rkd.rkd >= 1 and rkd.rkd < 0xfff: # RKDs 0 & 0xfff are special
            del self.by_comps[rkd.comps]
        for comp in rkd.comps:
            self.by_comp[comp].remove(rkd)

    def alloc_rkey(self, rkd: RKD) -> RKey:
        rkey = rkd.alloc_rkey()
        js = [ rkd.to_json() ]
        js[0]['assigned_rkeys'] = [ rkey ]
        self.fab.send_sfm('sfm_rkds', 'rkds', js, op='add_rkey')
        return rkey

    def free_rkey(self, rkd: RKD, rkey: RKey) -> None:
        rkd.free_rkey(rkey)
        js = [ rkd.to_json() ]
        js[0]['assigned_rkeys'] = [ rkey ]
        self.fab.send_sfm('sfm_rkds', 'rkds', js, op='rm_rkey')

    def add_comps_to_rkd(self, comps: Iterable[Component], rkd: RKD,
                         readOnly=False):
        rkd.add_comps(comps, readOnly=readOnly)
        for comp in comps:
            self.by_comp[comp].add(rkd)

    def remove_comps_from_rkd(self, comps: Iterable[Component], rkd: RKD,
                              readOnly=False):
        rkd.remove_comps(comps, readOnly=readOnly)
        for comp in comps:
            self.by_comp[comp].remove(rkd)

    def choose_rkd_id(self) -> int:
        random_rkds = self.random_rkds
        if self.refill_rkds:
            default_range = (1, 4094) # inclusive; RKDs 0 & 0xfff are special
            rkd_range = self.fab.conf.data.get('rkd_range', default_range)
            min_rkd, max_rkd = rkd_range if len(rkd_range) == 2 else default_range
            self.avail_rkds = (
                random.sample(range(min_rkd, max_rkd+1), max_rkd-min_rkd+1)
                if random_rkds else list(range(max_rkd, min_rkd-1, -1)))
            self.refill_rkds = False
        return self.avail_rkds.pop() # IndexError when empty

    def assign_rkd(self, res: 'ResourceList', prev_cons) -> Tuple[RKD,RKD]:
        '''Assign an RKD for @res. The RKD will be shared with other
        resources if their consumers match.
        @prev_cons is the set of consumers @res had previously. It may be an
        empty set.
        '''
        cons_fs = frozenset(res.consumers)
        prev_cons_fs = frozenset(prev_cons)
        prev_rkd = None if not prev_cons_fs else self.by_comps.get(prev_cons_fs)
        try:
            rkd = self.by_comps[cons_fs]
        except KeyError:
            # If prev_cons had an RKD and if res is the only user of
            # that RKD, then we can add_comps_to_rkd() else need a new RKD
            if (prev_rkd is not None and res in prev_rkd.resources and
                len(prev_rkd.resources) == 1):
                new_cons = cons_fs - prev_cons_fs
                self.add_comps_to_rkd(new_cons, prev_rkd)
                rkd = prev_rkd
                log.info(f'added {new_cons} to {rkd}')
            else: # need new RKD
                rkd_id = self.choose_rkd_id()
                rkd = RKD(res.consumers, rkd_id)
                self.add(rkd)
                log.info(f'new {rkd}')
        # end except
        rkd.add_resource(res)
        res.rkd = rkd
        js = self.to_json()
        self.fab.send_sfm('sfm_rkds', 'rkds', js, op='add')
        # Revisit: send_mgrs?
        return (rkd, prev_rkd)

    def release_rkd(self, res: 'ResourceList', rkd: RKD) -> bool:
        empty = rkd.remove_resource(res)
        if empty:
            log.info(f'remove {rkd}')
            self.remove_comps_from_rkd(res.consumers, rkd)
            self.remove(rkd)
        js = self.to_json()
        self.fab.send_sfm('sfm_rkds', 'rkds', js, op='release')
        # Revisit: send_mgrs?
        return empty

    def parse_rkd(self, rkd_dict):
        rkd_id = rkd_dict['rkd']
        try:
            rkd = self.by_rkd[rkd_id]
        except KeyError:
            comps = [self.fab.cuuid_serial[comp] for comp in rkd_dict['comps']]
            rkd = RKD(comps, rkd_id)
        for rk in rkd_dict['assigned_rkeys']:
            rkd.assign_rkey(RKey(rk))

    def parse(self, rkds_list, fab: 'Fabric', fab_rkds=None):
        set_trace() # Revisit: temp debug
        rkds = RKDs(fab) if fab_rkds is None else fab_rkds
        for rkle in rkds_list:
            rkd = self.parse_rkd(rkle)
            rkds.add(rkd)
        # end for

    def to_json(self):
        return [ rkd.to_json() for rkd in self.by_rkd.values() ]
