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
import time
import flask_fat
from flask_fat import ConfigBuilder
from uuid import UUID, uuid4
from pathlib import Path
from importlib import import_module
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from base64 import b64encode, b64decode
from collections import defaultdict
from genz.genz_common import GCID, CState, IState, RKey, PHYOpStatus, ErrSeverity, AKey
import zephyr_conf
from zephyr_conf import log, Conf
from zephyr_iface import Interface
from zephyr_comp import Component
from zephyr_fabric import Fabric
from zephyr_uep import netlink_reader
from middleware.netlink_mngr import NetlinkManager
from typing import List, Tuple
from threading import Thread
import multiprocessing as mp
import atexit
import socket
import os
import sys
import signal
from datetime import datetime
from zeroconf import IPVersion, ServiceInfo, Zeroconf
from setproctitle import getproctitle, setproctitle
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

# Enhanced version of https://stackoverflow.com/questions/18499497/how-to-process-sigterm-signal-gracefully
class TerminateProtected:
    """Protect a piece of code from being killed by SIGINT or SIGTERM.
    It can still be killed by a force kill.

    Example:
        with TerminateProtected():
            run_func_1()
            run_func_2()

    Both functions will be executed even if a sigterm or sigkill has
    been received, unless @immediate is True, in which case the exit
    is immediate.

    """
    killed = False

    def __init__(self, immediate=False):
        self._imm = immediate

    def _handler(self, signum, frame):
        self.killed = True
        self.signum = signum
        if self._imm:
            log.error("Received SIGINT or SIGTERM! Exiting immediately.")
            sys.exit(128 + self.signum)
        else:
            log.error("Received SIGINT or SIGTERM! Finishing this block, then exiting.")

    def __enter__(self):
        self.old_sigint = signal.signal(signal.SIGINT, self._handler)
        self.old_sigterm = signal.signal(signal.SIGTERM, self._handler)

    def __exit__(self, type, value, traceback):
        if self.killed:
            sys.exit(128 + self.signum)
        signal.signal(signal.SIGINT, self.old_sigint)
        signal.signal(signal.SIGTERM, self.old_sigterm)


class Callbacks():
    def __init__(self, ts=None):
        self.endpoints = defaultdict(lambda: defaultdict(dict))
        if ts is None:
            ts = time.time_ns()
        self.mod_timestamp = ts

    def set_endpoints(self, cuuid_serial: str, endpoints: dict, ts=None) -> None:
        '''cuuid_serial can instead be an instance_uuid, for managers that
        are not associated with a Gen-Z component
        endpoints data model:
        {
        'callbacks' : { },
        'mgr_type'  : 'string', # 'llamas', 'sfm', or <any other string>
        'mod_timestamp' : int,
        }
        '''
        if ts is None:
            ts = time.time_ns()
        endpoints['mod_timestamp'] = ts
        mgr_type = endpoints['mgr_type']
        self.endpoints[cuuid_serial][mgr_type] = endpoints
        self.mod_timestamp = max(self.mod_timestamp, ts)

    def remove_endpoints(self, cuuid_serial: str, endpoints: dict, ts=None) -> None:
        '''cuuid_serial can instead be an instance_uuid, for managers that
        are not associated with a Gen-Z component
        endpoints data model:
        {
        'callbacks' : { },
        'mgr_type'  : 'string', # 'llamas', 'sfm', or <any other string>
        'mod_timestamp' : int,
        }
        '''
        if ts is None:
            ts = time.time_ns()
        mgr_type = endpoints['mgr_type']
        del self.endpoints[cuuid_serial][mgr_type]
        if len(self.endpoints[cuuid_serial]) == 0:
            del self.endpoints[cuuid_serial]
        self.mod_timestamp = max(self.mod_timestamp, ts)

    def send_endpoints_update(self, fab, cuuid_serial,
                              mgr_type: str = None, op=None):
        ep = self.get_endpoints(cuuid_serial, mgr_type=mgr_type)
        if mgr_type is None:
            js = { cuuid_serial: ep }
        else:
            js = { cuuid_serial: { mgr_type: ep } }
        fab.send_mgrs(['sfm'], 'mgr_endpoints', 'endpoints', js, op=op)

    def get_endpoints(self, cuuid_serial: str, mgr_type: str = None):
        if mgr_type is None:
            return self.endpoints[cuuid_serial]
        else:
            return self.endpoints[cuuid_serial][mgr_type]

    def get_callbacks(self, mgr_types: List[str], callback: str,
                      invertTypes=False):
        for eps in self.endpoints.values():
            for type, ep in eps.items():
                if not invertTypes:
                    if type in mgr_types and callback in ep['callbacks']:
                        yield ep['callbacks'][callback]
                else: # invertTypes
                    if type not in mgr_types and callback in ep['callbacks']:
                        yield ep['callbacks'][callback]
            # end for type
        # end for eps

    def match(self, mgr_type: str, callbacks: dict):
        for eps in self.endpoints.values():
            for type, ep in eps.items():
                if (type == mgr_type and 'callbacks' in ep and
                    callbacks == ep['callbacks']):
                    return True
        return False

    def set_fm_endpoints(self, endpoints: dict,
                         cur_ts: int, mod_ts: int, skipSFM=True) -> dict:
        for cuuid_serial, eps in endpoints.items():
            for type, ep in eps.items():
                if skipSFM and type == 'sfm':
                    continue
                self.set_endpoints(cuuid_serial, ep, ts=ep['mod_timestamp'])
        self.mod_timestamp = mod_ts
        return { 'success': [] }

    def remove_fm_endpoints(self, endpoints: dict,
                            cur_ts: int, mod_ts: int, skipSFM=True) -> dict:
        for cuuid_serial, eps in endpoints.items():
            for type, ep in eps.items():
                if skipSFM and type == 'sfm':
                    continue
                self.remove_endpoints(cuuid_serial, ep, ts=ep['mod_timestamp'])
        self.mod_timestamp = mod_ts
        return { 'success': [] }


class FMServer(flask_fat.APIBaseline):
    def __init__(self, config, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.conf = config
        self.callbacks = Callbacks()
        self.init_socket()

    def get_endpoints(self, consumers, llamas, mgr_type, name):
        endpoints = []
        ids = llamas if llamas is not None else consumers
        for id in ids:
            try:
                endpoints.append(self.callbacks.get_endpoints(id, mgr_type)['callbacks'][name])
            except KeyError:
                log.debug(f'consumer {id} has no subscribed {name} endpoint')
        # end for
        return endpoints

    def init_socket(self):
        # choose a random available port by setting config PORT to 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((self.config['HOST'], self.config['PORT']))
        self.sock.listen()
        # tell the underlying WERKZEUG server to use the socket we just created
        os.environ['WERKZEUG_SERVER_FD'] = str(self.sock.fileno())
        _, self.port = self.sock.getsockname()
        self.hostname = socket.gethostname()
        self.ip = socket.gethostbyname(self.hostname)

def cmd_add(url, **args):
    data = {
        'timestamp' : datetime.now()
    }
    data.update(args)
    resp = requests.post(url, data)
    if resp is None:
        return {}
    return json.loads(resp.text).get('data', {})


def zeroconf_register(fab, mainapp):
    desc = {'mgr_uuid': fab.mgr_uuid.bytes,
            'fab_uuid': fab.fab_uuid.bytes,
            'instance_uuid': fab.instance_uuid.bytes,
            'pfm': int(not zephyr_conf.is_sfm)}
    info = ServiceInfo(
        '_genz-fm._tcp.local.',
        f'zephyr{fab.fabnum}.{mainapp.hostname}._genz-fm._tcp.local.',
        addresses=[socket.inet_aton(mainapp.ip)],
        port=mainapp.port,
        properties=desc,
        server=f'{mainapp.hostname}.local.'
    )

    mainapp.zeroconfInfo = info
    ip_version = (IPVersion.All if args.ip6 else
                  IPVersion.V6Only if args.ip6_only else IPVersion.V4Only)
    zeroconf = Zeroconf(ip_version=ip_version)
    zeroconf.register_service(info)
    return zeroconf


def atexit_handler(mainapp, uep_proc):
    if zephyr_conf.is_sfm:
        log.info('unsubscribe SFM endpoints')
        mainapp.conf.fab.unsubscribe_sfm(mainapp.conf.fab.pfm_fm)
    else: # PFM
        mainapp.conf.fab.set_pfm(None)
        mainapp.conf.save_assigned_cids()
    log.info('zeroconf unregister service')
    try:
        mainapp.zeroconf.unregister_service(mainapp.zeroconfInfo)
        mainapp.zeroconf.close()
    except AttributeError:
        pass
    log.info('terminate UEP process')
    uep_proc.terminate()
    uep_proc.join()


def main():
    global args
    global cols
    global genz
    script_name = Path(__file__).name
    proc_title = script_name + ' ' + ' '.join(sys.argv[1:])
    setproctitle(proc_title)
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--conf', default='zephyr-fm/zephyr-fabric.conf',
                        help='fabric config file')
    parser.add_argument('-k', '--keyboard', action='count', default=0,
                        help='break to interactive keyboard at certain points')
    parser.add_argument('-v', '--verbosity', action='count', default=0,
                        help='increase output verbosity')
    parser.add_argument('--cfg', default=None,
                        help='cfg file')
    parser.add_argument('-r', '--reclaim', action='store_true',
                        help='reclaim fabric components using previous MGR-UUID')
    parser.add_argument('-s', '--sfm', action='store_true',
                        help='run as Secondary Fabric Manager')
    parser.add_argument('-H', '--sfm-heartbeat', default=5, type=float,
                        help='SFM heartbeat interval')
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
    parser.add_argument('--control-to', action='store', default=1e-3,
                        type=float, help='Control TO')
    parser.add_argument('--control-drto', action='store', default=10e-3,
                        type=float, help='Control DRTO')
    parser.add_argument('--uert', action='store', default=200e-3,
                        type=float, help='UEP retransmission timer (default: %(default)f)')
    parser.add_argument('--ptrt', action='store', default=500e-3,
                        type=float, help='Precision Time retransmission timer (default: %(default)f)')
    parser.add_argument('--no-akeys', action='store_true',
                        help='do not enable AKeys')
    parser.add_argument('--no-nonce', action='store_true',
                        help='do no nonce exchanges')
    parser.add_argument('--reversed', action='store_true',
                        help='explore interfaces reversed (high to low)')
    parser.add_argument('--write-mgruuid', action='store_true',
                        help='Write MGR-UUID workaround for broken capture')
    parser.add_argument('--pause-after', action='store', default=None, type=int,
                        help='pause after initializing this many components')
    ip_group = parser.add_mutually_exclusive_group()
    ip_group.add_argument('--ip6', action='store_true',
                          help='listen on IPv4 and IPv6')
    ip_group.add_argument('--ip6-only', action='store_true',
                          help='listen on IPv6 only')
    args = parser.parse_args()
    log.debug(f'"{proc_title}": Gen-Z version = {args.genz_version}')
    genz = import_module('genz.genz_{}'.format(args.genz_version.replace('.', '_')))
    zephyr_conf.init(args, genz)
    args_vars = vars(args)
    log.debug('args={}'.format(args_vars))
    nl = NetlinkManager(config='./zephyr-fm/alpaka.conf')
    map = genz.ControlStructureMap()
    mgr_uuid = None # by default, PFM generates new mgr_uuid every run
    fm_akey = None  # same for fm_akey
    conf = Conf(args.conf)
    try:
        data = conf.read_conf_file()
        if data is None:
            log.error(f'{conf.file} has zero length')
            return
        fab_uuid = UUID(data['fabric_uuid'])
        if args.reclaim:
            try:
                mgr_uuid = UUID(data['mgr_uuid'])
                fm_akey = AKey(data['fm_akey'])
            except (KeyError, ValueError):
                log.error('Missing/invalid conf file mgr_uuid/fm_akey with --reclaim')
                return
    except FileNotFoundError:
        # create new skeleton file
        data = {}
        fab_uuid = uuid4()
        key = AESGCM.generate_key(bit_length=256)
        data['fabric_uuid'] = str(fab_uuid)
        data['add_resources'] = []
        data['boundary_interfaces'] = []
        data['cid_range'] = []
        data['assigned_cids'] = {}
        data['local_bridges'] = []
        # Revisit: use pub/priv keys to establish a session key
        data['aesgcm_key'] = b64encode(key).decode('ascii')
        conf.write_conf_file(data)
    log.debug(f'conf={conf}')
    fabrics = {}
    if args.keyboard > 3:
        set_trace()
    mainapp = FMServer(conf, 'zephyr', **args_vars)
    thread = Thread(target=mainapp.run, daemon=True)
    thread.start()
    if args.keyboard > 3:
        set_trace()
    mp.set_start_method('forkserver')
    uep_args = { 'genz_version': args.genz_version,
                 'verbosity':    args.verbosity,
                 'url':          f'http://localhost:{mainapp.port}/fabric/uep' }
    uep_proc = mp.Process(target=netlink_reader, kwargs=uep_args)
    atexit.register(atexit_handler, mainapp, uep_proc)
    uep_proc.start()
    sys_devices = Path('/sys/devices')
    fab_paths = sys_devices.glob('genz*')
    for fab_path in sorted(fab_paths):
        fab = Fabric(nl, mainapp, map, fab_path, random_cids=args.random_cids,
                     fab_uuid=fab_uuid, fm_akey=fm_akey,
                     conf=conf, mgr_uuid=mgr_uuid, verbosity=args.verbosity)
        fabrics[fab_path] = fab
        conf.set_fab(fab, writeConf=(not args.sfm))
        if args.keyboard > 1:
            set_trace()
        if args.sfm:
            fab.sfm_init()
        else:
            start = datetime.now()
            fab.fab_init(reclaim=args.reclaim)
            end = datetime.now()
            log.info(f'finished exploring fabric {fab.fabnum}, exploration took {end-start}')
    # end for fab_path

    if len(fabrics) == 0:
        log.info('no local Gen-Z bridges found')
        return

    if not args.sfm:
        if args.keyboard > 3:
            set_trace()
        conf.save_assigned_cids()
        conf.add_resources()

    if args.keyboard > 3:
        set_trace()

    mainapp.zeroconf = zeroconf_register(fab, mainapp)
    if zephyr_conf.is_sfm:
        log.info('running as secondary fabric manager')
        mainapp.zeroconfBrowser = fab.zeroconf_browser(mainapp.zeroconf)

    if args.keyboard > 0:
        set_trace()

    with TerminateProtected(immediate=True):
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
