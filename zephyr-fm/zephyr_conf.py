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
from uuid import UUID
from genz.genz_common import GCID

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

    def set_fab(self, fab):
        self.fab = fab

    def read_conf_file(self):
        with open(self.file, 'r') as f:
            self.data = json.load(f)
            return self.data

    def write_conf_file(self, data):
        self.data = data
        with open(self.file, 'w') as f:
            json.dump(self.data, f, indent=2)

    def add_resource(self, conf_add) -> dict:
        from zephyr_res import ResourceList, Resource
        fab = self.fab
        res_list = ResourceList(fab, [], conf_add)
        for res_dict in conf_add['resources']:
            if res_dict['instance_uuid'] == '???': # new resource
                res = Resource(res_list, res_dict)
                res_list.append(res)
                fab.resources.add(res)
                # Revisit: set up responder ZMMU if res['type'] is DATA (1)
            else: # modification of existing resource - add consumers
                instance_uuid = UUID(res_dict['instance_uuid'])
                res = fab.resources.by_instance_uuid[instance_uuid]
                res_list = res.res_list
                res_list.add_consumers(conf_add['consumers'])
        return res_list.to_json()

    def add_resources(self) -> None:
        add_res = self.data.get('add_resources', [])
        if len(add_res) == 0:
            log.info('add_resources not found in {}'.format(self.file))
        log.info('adding resources from {}'.format(self.file))
        for conf_add in add_res:
            self.add_resource(conf_add)
        log.info('finished adding resources from {}'.format(self.file))

    def remove_resource(self, conf_rm) -> dict:
        fab = self.fab
        for res_dict in conf_rm['resources']:
            if res_dict['instance_uuid'] == '???': # unknown resource
                log.warning('remove resource request missing instance_uuid')
            else: # modification of existing resource - remove consumers
                instance_uuid = UUID(res_dict['instance_uuid'])
                res = fab.resources.by_instance_uuid[instance_uuid]
                res_list = res.res_list
                res_list.remove_consumers(res, conf_rm['consumers'])
        return res_list.to_json()

    def get_resources(self, cuuid_serial) -> List['ResourceList']:
        fab = self.fab
        consumer = fab.cuuid_serial[cuuid_serial]
        return [ res.to_json() for res in fab.resources.by_consumer[consumer] ]

    def __repr__(self):
        return 'Conf(' + repr(self.data) + ')'
