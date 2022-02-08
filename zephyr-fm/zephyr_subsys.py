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

import contextlib
import argparse
import ctypes
import json
import requests
import flask_fat
from flask_fat import ConfigBuilder
from uuid import UUID, uuid4
from pathlib import Path
from importlib import import_module
from genz.genz_common import GCID, CState, IState, RKey, PHYOpStatus, ErrSeverity
import zephyr_conf
from zephyr_conf import log, Conf
from zephyr_iface import Interface
from zephyr_comp import Component
from zephyr_fabric import Fabric
from zephyr_res import ResourceList
from zephyr_uep import netlink_reader
from middleware.netlink_mngr import NetlinkManager
from typing import List, Tuple
from threading import Thread
import multiprocessing as mp
from pdb import set_trace, post_mortem
import traceback

INVALID_UUID = UUID(int=0xffffffffffffffffffffffffffffffff)

# Magic to get JSONEncoder to call to_json method, if it exists
def _default(self, obj):
    return getattr(obj.__class__, 'to_json', _default.default)(obj)

_default.default = json.JSONEncoder().default
json.JSONEncoder.default = _default

def uuid_to_json(self):
    return str(self)
UUID.to_json = uuid_to_json

class FMServer(flask_fat.APIBaseline):
    def __init__(self, conf, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.conf = conf
        self.add_callback = {}
        self.remove_callback = {}

    def get_endpoints(self, consumers):
        add_endpoints = []
        rm_endpoints = []
        for con in consumers:
            try:
                add_endpoints.append(self.add_callback[con])
                rm_endpoints.append(self.remove_callback[con])
            except KeyError:
                log.debug('consumer {} has no subscribed endpoint'.format(con))
        # end for
        return (add_endpoints, rm_endpoints)

def cmd_add(url, **args):
    from datetime import datetime
    data = {
        'timestamp' : datetime.now()
    }
    data.update(args)
    resp = requests.post(url, data)
    if resp is None:
        return {}
    return json.loads(resp.text).get('data', {})


def main():
    global args
    global cols
    global genz
    parser = argparse.ArgumentParser()
    parser.add_argument('-k', '--keyboard', action='count', default=0,
                        help='break to interactive keyboard at certain points')
    parser.add_argument('-v', '--verbosity', action='count', default=0,
                        help='increase output verbosity')
    parser.add_argument('-A', '--accept-cids', action='store_true',
                        help='accept pre-existing HW CIDs for all components')
    parser.add_argument('-r', '--reclaim', action='store_true',
                        help='reclaim C-Up components via reset')
    parser.add_argument('-M', '--max-routes', action='store', default=None, type=int,
                        help='limit number of routes between components')
    parser.add_argument('-R', '--random-cids', action='store_true',
                        help='generate random CIDs for all components')
    parser.add_argument('-S', '--sleep', type=float, default=0.0,
                        help='sleep time inserted at certain points')
    parser.add_argument('-G', '--genz-version', choices=['1.1'],
                        default='1.1',
                        help='Gen-Z spec version of Control Space structures')
    parser.add_argument('-P', '--post_mortem', action='store_true',
                        help='enter debugger on uncaught exception')
    args = parser.parse_args()
    log.debug('Gen-Z version = {}'.format(args.genz_version))
    genz = import_module('genz.genz_{}'.format(args.genz_version.replace('.', '_')))
    zephyr_conf.init(args, genz)
    args_vars = vars(args)
    log.debug('args={}'.format(args_vars))
    nl = NetlinkManager(config='./zephyr-fm/alpaka.conf')
    map = genz.ControlStructureMap()
    mgr_uuid = None # by default, generate new mgr_uuid every run
    conf = Conf('zephyr-fm/zephyr-fabric.conf')
    try:
        data = conf.read_conf_file()
        fab_uuid = UUID(data['fabric_uuid'])
        if args.reclaim:
            mgr_uuid = UUID(data['mgr_uuid'])
    except FileNotFoundError:
        # create new skeleton file
        data = {}
        fab_uuid = uuid4()
        data['fabric_uuid'] = str(fab_uuid)
        data['add_resources'] = []
        data['boundary_interfaces'] = []
        conf.write_conf_file(data)
    log.debug('conf={}'.format(conf))
    fabrics = {}
    if args.keyboard > 3:
        set_trace()
    mainapp = FMServer(conf, 'zephyr', **args_vars)
    thread = Thread(target=mainapp.run)
    thread.start()
    if args.keyboard > 3:
        set_trace()
    mp.set_start_method('forkserver')
    uep_args = { 'genz_version': args.genz_version,
                 'verbosity':    args.verbosity,
                 'url':          'http://localhost:2021/fabric/uep' }
    uep_proc = mp.Process(target=netlink_reader, kwargs=uep_args)
    uep_proc.start()
    sys_devices = Path('/sys/devices')
    fab_paths = sys_devices.glob('genz*')
    for fab_path in sorted(fab_paths):
        fab = Fabric(nl, map, fab_path, random_cids=args.random_cids,
                     accept_cids=args.accept_cids, fab_uuid=fab_uuid,
                     conf=conf, mgr_uuid=mgr_uuid, verbosity=args.verbosity)
        fabrics[fab_path] = fab
        conf.set_fab(fab)
        if args.keyboard > 1:
            set_trace()
        fab.fab_init()
        log.info('finished exploring fabric {}'.format(fab.fabnum))

    if len(fabrics) == 0:
        log.info('no local Gen-Z bridges found')
        return

    if args.keyboard > 3:
        set_trace()

    conf.add_resources()  # Revisit: multiple fabrics

    if args.keyboard > 3:
        set_trace()

    thread.join()

if __name__ == '__main__':
    try:
        main()
    except Exception as post_err:
        if args.post_mortem:
            traceback.print_exc()
            post_mortem()
        else:
            raise
