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
from itertools import chain
from genz.genz_common import AKey, DEFAULT_AKEY
from copy import deepcopy
from pdb import set_trace
from typing import Iterable, List, NamedTuple, Tuple, Optional
from collections import defaultdict
from zephyr_conf import log
from zephyr_comp import Component

class AKeys():
    # Revisit: timestamps
    # Revisit: multiple CIDs
    def __init__(self, fab: 'Fabric', random_akeys=True):
        self.fab = fab
        self.by_comps = {} # key: frozenset(Components), val: AKey (>= 1)
        self.by_akey = {}   # key: akey, val: set(Components)
        self.by_comp = defaultdict(dict) # key: Component, val dict(key: AKey, val set(Components))
        self.assigned_akeys = set()
        self.akeys = [] # defer creation until first alloc_akey()
        self.refill_akeys = True
        self.random_akeys = random_akeys
        self.mod_timestamp = time.time_ns()

    def add(self, akey: AKey, comps: Iterable[Component], ts=None) -> None:
        comps_set = set(comps)
        self.by_akey[akey] = comps_set
        if akey >= 1: # AKey 0 is special
            self.by_comps[frozenset(comps)] = akey
        for comp in comps:
            self.by_comp[comp][akey] = comps_set
        log.debug(f'add AKey {akey}, comps: {comps_set}')

    def remove(self, akey: AKey, ts=None) -> None:
        comps = self.by_akey[akey] # KeyError if not found
        log.debug(f'remove AKey {akey}, comps: {comps}')
        del self.by_akey[akey]
        if akey >= 1: # AKey 0 is special
            del self.by_comps[frozenset(comps)]
        for comp in comps:
            del self.by_comp[comp][akey]

    def alloc_akey(self, comps: Iterable[Component],
                   proposed_akey: AKey = None) -> AKey:
        if self.refill_akeys:
            default_range = (1, 63) # inclusive; AKey 0 is special
            akey_range = self.fab.conf.data.get('akey_range', default_range)
            min_akey, max_akey = akey_range if len(akey_range) == 2 else default_range
            self.akeys = [ AKey(n) for n in range(min_akey, max_akey+1)
                           if n not in self.assigned_akeys ]
            if self.random_akeys:
                random.shuffle(self.akeys)
            self.refill_akeys = False
        # end if refill
        if proposed_akey is not None and proposed_akey != DEFAULT_AKEY:
            self.akeys.remove(proposed_akey) # ValueError if not available
            akey = proposed_akey
        else:
            akey = self.akeys.pop() # IndexError when empty
        self.add(akey, comps)
        self.assigned_akeys.add(akey)
        js = self.to_json()
        js['assigned_akeys'] = [ akey ]
        self.fab.send_sfm('sfm_akeys', 'akeys', js, op='add_akey')
        return akey

    def free_akey(self, akey: AKey) -> None:
        if not isinstance(akey, AKey):
            raise TypeError('akey is not an AKey')
        if akey in self.akeys or akey not in self.assigned_akeys:
            return
        self.assigned_akeys.remove(akey)
        self.akeys.append(akey)
        # swap free'd akey (at [-1]) with a random element (could be itself)
        r = random.randint(0, len(self.akeys) - 1)
        self.akeys[r], self.akeys[-1] = self.akeys[-1], self.akeys[r]
        js = self.to_json()
        js['assigned_akeys'] = [ akey ]
        self.fab.send_sfm('sfm_akeys', 'akeys', js, op='rm_akey')

    def add_comps_to_akey(self, comps: Iterable[Component], akey: AKey,
                          readOnly=False) -> None:
        if akey is DEFAULT_AKEY:
            return
        prev_comps = self.by_akey[akey]
        comps_set = set(comps) | prev_comps
        for comp in comps:
            self.by_comp[comp][akey] = comps_set
        del self.by_comps[frozenset(prev_comps)]
        self.by_comps[frozenset(comps_set)] = akey
        self.by_akey[akey] = comps_set

    def remove_comps_from_akey(self, comps: Iterable[Component], akey: AKey,
                               readOnly=False) -> bool:
        if akey is DEFAULT_AKEY:
            return False
        prev_comps = self.by_akey[akey]
        comps_set = prev_comps - set(comps)
        for comp in comps:
            del self.by_comp[comp][akey]
        del self.by_comps[frozenset(prev_comps)]
        if comps_set: # new set is not empty
            self.by_comps[frozenset(comps_set)] = akey
            self.by_akey[akey] = comps_set
            empty = False
        else:
            del self.by_akey[akey]
            empty = True
        return empty

    def parse_akey(self, akey_dict):
        akey_id = akey_dict['akey']
        try:
            akey = self.by_akey[akey_id]
        except KeyError:
            comps = [self.fab.cuuid_serial[comp] for comp in akey_dict['comps']]
            akey = AKey(comps, akey_id)
        for ak in akey_dict['assigned_akeys']:
            rkd.assign_rkey(AKey(ak)) # Revisit: fix this

    def parse(self, akeys_list, fab: 'Fabric', fab_akeys=None):
        akeys = AKeys(fab) if fab_akeys is None else fab_akeys
        for rkle in akeys_list: # Revisit: fix this
            rkd = self.parse_rkd(rkle)
            akeys.add(rkd)
        # end for

    def mask(self, akeys_list):
        mask = 0
        for ak in akeys_list:
            mask |= (1 << ak)
        return mask

    def to_json(self):
        return { 'by_comp': self.by_comp }

class Partition():
    '''Using AKeys to implement component partitions.
    '''
    def __init__(self, fab: 'Fabric', comps: Iterable[Component],
                 fm_comps: Iterable[Component],
                 instance_uuid: UUID = None, proposed_akey: AKey = None):
        self.fab = fab
        self.instance_uuid = uuid4() if instance_uuid is None else instance_uuid
        self.akey = fab.akeys.alloc_akey(comps, proposed_akey=proposed_akey)
        self.fm_comps = set(fm_comps) # in partition but using fm_akey, not akey
        self.mod_timestamp = time.time_ns()

    def add_comps(self, comps: Iterable[Component],
                  fm_comps: Iterable[Component] = []):
        self.fab.akeys.add_comps_to_akey(comps, self.akey)
        self.fm_comps = self.fm_comps | set(fm_comps)
        self.mod_timestamp = time.time_ns()

    def remove_comps(self, comps: Iterable[Component],
                     fm_comps: Iterable[Component] = []):
        self.fab.akeys.remove_comps_from_akey(comps, self.akey)
        self.fm_comps = self.fm_comps - set(fm_comps)
        self.mod_timestamp = time.time_ns()

    def __hash__(self):
        return hash(self.instance_uuid)

    def __del__(self): # Revisit: better way than __del__?
        self.fab.akeys.free_akey(self.akey)

    def to_json(self):
        return { 'mod_timestamp': self.mod_timestamp,
                 'instance_uuid': self.instance_uuid,
                 'akey': self.akey,
                 'comp_list': [ comp.to_json() for comp in
                                self.fab.akeys.by_akey[self.akey] ],
                 'fm_comps': [ comp.to_json() for comp in self.fm_comps ]
                }

class Partitions():
    def __init__(self, fab):
        self.fab = fab
        self.by_uuid = {}  # key: instance_uuid, val: Partition
        self.mod_timestamp = time.time_ns()

    def bidi_ssap_write(self, comp1: Component, comp2: Component, akey: AKey,
                        paIdx: int):
                acreq, acrsp = comp1.acreqrsp(comp2)
                comp1.ssap_write(comp2.gcid.cid, akey,
                                 acreq=acreq, acrsp=acrsp, paIdx=paIdx)
                acreq, acrsp = comp2.acreqrsp(comp1)
                comp2.ssap_write(comp1.gcid.cid, akey,
                                 acreq=acreq, acrsp=acrsp, paIdx=paIdx)

    def add_partition(self, part: Partition):
        self.by_uuid[part.instance_uuid] = part
        comps = self.fab.akeys.by_akey[part.akey]
        for comp in comps:
            if comp.partition is None:
                comp.partition = part
            else:
                pass # Revisit: error handling
        # Revisit: this is an N**2 operation
        for comp in comps:
            for other in comps:
                acreq, acrsp = comp.acreqrsp(other)
                comp.ssap_write(other.gcid.cid, part.akey,
                                acreq=acreq, acrsp=acrsp, paIdx=0)
            # end for
        # end for
        for fm_comp in part.fm_comps:
            fm_comp.partition = part
            for other in comps:
                # update acreq/acrsp but leave other fields
                self.bidi_ssap_write(fm_comp, other, None, None)
            # end for
        # end for
        self.mod_timestamp = time.time_ns()

    def remove_partition(self, part: Partition):
        del self.by_uuid[part.instance_uuid]
        comps = self.fab.akeys.by_akey[part.akey]
        for comp in comps:
            comp.partition = None
        # Revisit: this is an N**2 operation
        for comp in comps:
            for other in comps:
                acreq, acrsp = comp.acreqrsp(other)
                comp.ssap_write(other.gcid.cid, DEFAULT_AKEY,
                                acreq=acreq, acrsp=acrsp, paIdx=0)
            # end for
        # end for
        for fm_comp in part.fm_comps:
            fm_comp.partition = None
            for other in comps:
                # update acreq/acrsp but leave other fields
                self.bidi_ssap_write(fm_comp, other, None, None)
            # end for
        # end for
        del part
        self.mod_timestamp = time.time_ns()

    def add_partition_comps(self, part: Partition, comps: Iterable[Component],
                            fm_comps: Iterable[Component]):
        # check for comps/fm_comps partition not None
        for comp in chain(comps, fm_comps):
            if comp.partition is None:
                comp.partition = part
            else:
                pass # Revisit: error handling
        # end for
        prev_comps = set(self.fab.akeys.by_akey[part.akey])
        prev_fm_comps = set(part.fm_comps)
        part.add_comps(comps, fm_comps)
        for comp in comps:
            for other in prev_comps: # comps/prev_comps are disjoint
                self.bidi_ssap_write(comp, other, part.akey, 0)
            # end for
            for other in prev_fm_comps: # comps/prev_fm_comps are disjoint
                # update acreq/acrsp but leave other fields
                self.bidi_ssap_write(comp, other, None, None)
            # end for
        # end for
        for fm_comp in fm_comps:
            for other in prev_comps:
                # update acreq/acrsp but leave other fields
                self.bidi_ssap_write(fm_comp, other, None, None)
            # end for
            for other in prev_fm_comps: # fm_comps/prev_fm_comps are disjoint
                # update acreq/acrsp but leave other fields
                self.bidi_ssap_write(fm_comp, other, None, None)
            # end for
        # end for

    def remove_partition_comps(self, part: Partition, comps: Iterable[Component],
                               fm_comps: Iterable[Component]):
        # check for comps/fm_comps not in partition
        for comp in chain(comps, fm_comps):
            if comp.partition == part:
                comp.partition = None
            else:
                pass # Revisit: error handling
        # end for
        part.remove_comps(comps, fm_comps)
        remain_comps = set(self.fab.akeys.by_akey[part.akey])
        remain_fm_comps = set(part.fm_comps)
        for comp in comps:
            for other in remain_comps: # comps/remain_comps are disjoint
                self.bidi_ssap_write(comp, other, DEFAULT_AKEY, 0)
            # end for
            for other in remain_fm_comps: # comps/remain_fm_comps are disjoint
                # update acreq/acrsp but leave other fields
                self.bidi_ssap_write(comp, other, None, None)
            # end for
        # end for
        for fm_comp in fm_comps:
            for other in remain_comps:
                # update acreq/acrsp but leave other fields
                self.bidi_ssap_write(fm_comp, other, None, None)
            # end for
            for other in remain_fm_comps: # fm_comps/remain_fm_comps are disjoint
                # update acreq/acrsp but leave other fields
                self.bidi_ssap_write(fm_comp, other, None, None)
            # end for
        # end for

    def find(self, uuid: UUID) -> Partition:
        return self.by_uuid[uuid]

    def parse_uuid(self, uuid_str: str) -> Optional[Partition]:
        try:
            instance_uuid = UUID(uuid_str)
            part = self.find(instance_uuid)
        except (KeyError, ValueError):
            return None
        return part

    def parse(self, body, action: str = None):
        fab = self.fab
        special = { fab.pfm.cuuid_serial } # PFM (and SFM) are special
        if fab.sfm is not None:
            special.add(fab.sfm.cuuid_serial)
        try:
            partition = body['partition']
        except KeyError:
            return { 'failed': ['missing partition'] }
        try:
            uuid_str = partition['instance_uuid']
        except KeyError:
            return { 'failed': ['missing instance_uuid'] }
        try:
            comps = { fab.cuuid_serial[cs] for cs in partition['comp_list']
                      if cs not in special }
            fm_comps = { fab.cuuid_serial[cs] for cs in partition['comp_list']
                         if cs in special }
        except KeyError:
            return { 'failed': ['invalid comp_list'] }
        if action == 'add':
            part = Partition(fab, comps, fm_comps)
            self.add_partition(part)
            return { 'success': [part.instance_uuid] }
        elif action == 'remove':
            part = self.parse_uuid(uuid_str)
            if part is None:
                return { 'failed': [f'invalid instance_uuid {uuid_str}'] }
            self.remove_partition(part)
            return { 'success': [part.instance_uuid] }
        elif action == 'add_comps':
            part = self.parse_uuid(uuid_str)
            if part is None:
                return { 'failed': [f'invalid instance_uuid {uuid_str}'] }
            self.add_partition_comps(part, comps, fm_comps)
            return { 'success': [part.instance_uuid] }
        elif action == 'remove_comps':
            part = self.parse_uuid(uuid_str)
            if part is None:
                return { 'failed': [f'invalid instance_uuid {uuid_str}'] }
            self.remove_partition_comps(part, comps, fm_comps)
            return { 'success': [part.instance_uuid] }
        else:
            return { 'failed': [f'invalid action {action}'] }

    def to_json(self):
        desc = {
            'fab_uuid': str(self.fab.fab_uuid),
            'cur_timestamp': time.time_ns(),
            'mod_timestamp': self.mod_timestamp,
            'partitions': [ part.to_json() for part in self.by_uuid.values() ]
        }
        return desc
