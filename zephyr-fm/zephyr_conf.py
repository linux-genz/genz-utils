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

from typing import List, Tuple
import logging
import logging.config
import yaml
import json
import time
from uuid import UUID
from pdb import set_trace
from genz.genz_common import GCID, CState

INVALID_GCID = GCID(val=0xffffffff)

with open('zephyr-fm/logging.yaml', 'r') as f:
    yconf = yaml.safe_load(f.read())
    logging.config.dictConfig(yconf)

log = logging.getLogger('zephyr')

def init(a, gz):
    global args
    global genz
    args = a
    genz = gz
    
# Magic to get JSONEncoder to call to_json method, if it exists
def _default(self, obj):
    return getattr(obj.__class__, 'to_json', _default.default)(obj)

_default.default = json.JSONEncoder().default
json.JSONEncoder.default = _default

def uuid_to_json(self):
    return str(self)
UUID.to_json = uuid_to_json

class Conf():
    def __init__(self, file):
        self.file = file
        self.fab = None  # set by set_fab()

    def set_fab(self, fab, writeConf=True):
        self.fab = fab
        if writeConf:
            self.data['mgr_uuid'] = str(fab.mgr_uuid)
            self.data['fm_akey'] = fab.fm_akey
            self.write_conf_file(self.data)

    def read_conf_file(self):
        with open(self.file, 'r') as f:
            self.data = json.load(f)
            return self.data

    def write_conf_file(self, data):
        self.data = data
        with open(self.file, 'w') as f:
            json.dump(self.data, f, indent=2)
            print('', file=f) # add a newline

    def get_assigned_cids(self):
        try:
            return { cuuid_serial: GCID(str=cid) for cuuid_serial, cid in
                     self.data['assigned_cids'].items() }
        except KeyError:
            return {}

    def save_assigned_cids(self, writeConf=True):
        '''Save a dict of cuuid_serial:assigned_cid whose Components are CUp.
        Used by a subsequent --reclaim to avoid (most) CID conflicts.
        '''
        fab = self.fab
        if fab is None:
            return
        cUps = { c.gcid for c in fab.cuuid_serial.values()
                 if c.cstate == CState.CUp }
        assigned = cUps.intersection(fab.assigned_gcids.values())
        self.data['assigned_cids'] = {
            fab.comp_gcids[gcid].cuuid_serial: str(gcid) for gcid in assigned }
        if writeConf:
            self.write_conf_file(self.data)

    def add_resource(self, conf_add, send=True, op=None) -> dict:
        from zephyr_res import ResourceList, Resource
        fab = self.fab
        ro = op is not None
        ts = conf_add.get('mod_timestamp', time.time_ns())
        res_list = ResourceList(fab, [], conf_add, readOnly=ro, ts=ts)
        newRes, addCons = False, False
        for res_dict in conf_add['resources']:
            if op == 'add':
                res = Resource(res_list, res_dict)
                res_list.append(res)
                fab.resources.add(res, ts=ts)
            elif res_dict['instance_uuid'] == '???': # new resource
                if addCons:
                    log.warning('mixed newRes and addCons resources')
                    continue
                newRes = True
                res = Resource(res_list, res_dict, readOnly=ro)
                res_list.append(res)
                fab.resources.add(res)
                # Revisit: set up responder ZMMU if res['type'] is DATA (1)
            else: # modification of existing resource - add consumers
                if newRes:
                    log.warning('mixed newRes and addCons resources')
                    continue
                addCons = True
                instance_uuid = UUID(res_dict['instance_uuid'])
                res = fab.resources.by_instance_uuid[instance_uuid]
                res_list = res.res_list
                res_list.add_consumers(conf_add['consumers'], readOnly=ro)
        # send new/modified resources to SFM and other mgrs
        js = res_list.to_json()
        if send:
            op='add' if newRes else 'add_cons'
            fab.send_sfm('sfm_res', 'resource', js, op=op)
            fab.send_mgrs(['sfm', 'llamas'], 'mgr_res', 'resource', js,
                          op=op, invertTypes=True)
        return js

    def add_resources(self) -> None:
        add_res = self.data.get('add_resources', None)
        if add_res is None:
            log.info('add_resources not found in {}'.format(self.file))
            return
        if len(add_res) == 0:
            log.info('no resources to add from {}'.format(self.file))
            return
        log.info('adding resources from {}'.format(self.file))
        for conf_add in add_res:
            self.add_resource(conf_add)
        log.info('finished adding resources from {}'.format(self.file))

    def fab_resources(self, fab_res, ts=None) -> None:
        '''Called by SFM with resources fetched from PFM
        '''
        if fab_res is None:
            log.error('PFM fab resources is None')
            return
        if len(fab_res) == 0:
            log.info('no PFM fab resources to add')
            return
        log.info('adding resources from PFM')
        if ts is not None:
            self.fab.resources.mod_timestamp = ts
        for fres in fab_res:
            self.add_resource(fres, op='add', send=False)
        log.info('finished adding resources from PFM')

    def remove_resource(self, conf_rm, send=True, op=None) -> dict:
        fab = self.fab
        js = None
        ts = conf_rm.get('mod_timestamp', None)
        for res_dict in conf_rm['resources']:
            if res_dict['instance_uuid'] == '???': # unknown resource
                log.warning('remove resource request missing instance_uuid')
            else: # modification of existing resource - remove consumers
                instance_uuid = UUID(res_dict['instance_uuid'])
                res = fab.resources.by_instance_uuid[instance_uuid]
                res_list = res.res_list
                if js is None: # get json before res_list is modified
                    js = res_list.to_json()
                res_list.remove_consumers(res, conf_rm['consumers'], ts=ts)
                op = 'rm_cons'
                if len(res.consumers) == 0: # last consumer removed
                    fab.resources.remove(res, ts=ts) # remove res itself
                    op = 'remove'
        # send removed/modified resources to SFM
        if send:
            fab.send_sfm('sfm_res', 'resource', js, op=op)
            fab.send_mgrs(['sfm', 'llamas'], 'mgr_res', 'resource', js,
                          op=op, invertTypes=True)
        return js

    def get_resources(self, cuuid_serial) -> List['ResourceList']:
        fab = self.fab
        consumer = fab.cuuid_serial[cuuid_serial]
        return [ res.to_json() for res in fab.resources.by_consumer[consumer] ]

    def __repr__(self):
        return 'Conf(' + repr(self.data) + ')'
