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
from typing import List, NamedTuple
from collections import defaultdict
from zephyr_conf import log
from zephyr_comp import Component
from zephyr_route import RoutesTuple

class Resource():
    def __init__(self, res_list: 'ResourceList', res_dict: dict):
        self.res_list = res_list
        self.res_dict = res_dict
        if res_dict['instance_uuid'] == '???':
                res_dict['instance_uuid'] = str(uuid4())
        self.instance_uuid = UUID(res_dict['instance_uuid'])
        # Revisit: RKeys

    @property
    def producer(self):
        return self.res_list.producer

    @property
    def consumers(self):
        return self.res_list.consumers

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
        for cons in consumers:
            try:
                cons_comp = self.fab.cuuid_serial[cons]
            except KeyError:
                log.warning(f'consumer component {cons} not found in fabric{self.fab.fabnum}')
                continue
            if cons_comp not in self.consumers:
                self.res_dict['consumers'].append(cons_comp.cuuid_serial)
                self.consumers.add(cons_comp)
                self.update_mod_timestamp()
                if not readOnly:
                    routes = self.fab.setup_bidirectional_routing(
                        cons_comp, self.producer, res=True)
                    self.res_routes.add(cons_comp, routes)
        # end for cons

    def remove_consumers(self, res: Resource, consumers, ts=None):
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
        # end for

    def remove(self, res: Resource, ts=None) -> None:
        del self.by_instance_uuid[res.instance_uuid]
        res_list = res.res_list
        res_list.set_parent(self, ts=ts)
        self.by_producer[res.producer].remove(res_list)
        for cons in res.consumers:
            self.by_consumer[cons].remove(res_list)

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
