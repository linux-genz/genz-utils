#!/usr/bin/env python3

# Copyright  ©  2020-2021 IntelliProp Inc. All rights reserved.

import argparse
import os
import ctypes
import json
import requests
import logging
import logging.config
import yaml
from uuid import UUID
from importlib import import_module
from pyroute2 import GenericNetlinkSocket
from pyroute2.netlink import genlmsg
from pdb import set_trace, post_mortem
import traceback

# Revisit: copied from zephyr_subsys.py
# Magic to get JSONEncoder to call to_json method, if it exists
def _default(self, obj):
    return getattr(obj.__class__, 'to_json', _default.default)(obj)

_default.default = json.JSONEncoder().default
json.JSONEncoder.default = _default

def uuid_to_json(self):
    return str(self)
UUID.to_json = uuid_to_json

with open('zephyr-fm/logging.yaml', 'r') as f:
    yconf = yaml.safe_load(f.read())
    logging.config.dictConfig(yconf)

log = logging.getLogger('zephyr')

GENZ_FAMILY_NAME = 'genz_cmd' # Revisit: duplicate of alpaka.conf
GENZ_C_NOTIFY_UEP = 10

class uep(genlmsg):
    '''
    Message class for UEPs
    '''
    # Revisit: replace arrays with direct bytes/bytearray
    nla_map = (('GENZ_A_UEP_UNSPEC', 'none'),
               ('GENZ_A_UEP_FLAGS', 'uint64'),
               ('GENZ_A_UEP_MGR_UUID', 'array(uint8)'),
               ('GENZ_A_UEP_BRIDGE_GCID', 'uint32'),
               ('GENZ_A_UEP_TS_SEC', 'uint64'),
               ('GENZ_A_UEP_TS_NSEC', 'uint64'),
               ('GENZ_A_UEP_REC', 'array(uint8)'),
               )


def netlink_reader(*args, **kwargs):
    genz_version = kwargs.get('genz_version', '1.1')
    verbosity = kwargs.get('verbosity', 0)
    url = kwargs.get('url')
    keyboard = kwargs.get('keyboard', False)
    if verbosity > 0:
        log.info('zephyr_uep started, pid={}, genz_version={}, verbosity={}, url={}'.format(
            os.getpid(), genz_version, verbosity, url))
    genz = import_module('genz.genz_{}'.format(genz_version.replace('.', '_')))
    nl = GenericNetlinkSocket()
    nl.bind(GENZ_FAMILY_NAME, uep)
    nl.add_membership('ueps') # Revisit: needed?
    hdrs = {'Content-type': 'application/json', 'Accept': 'text/plain'}
    while True:
        log.debug('waiting for kernel netlink UEP msg')
        try:
            msg = nl.get()
        except KeyboardInterrupt:
            return
        for i in range(len(msg)):
            if msg[i]['cmd'] != GENZ_C_NOTIFY_UEP or msg[i]['version'] != 1:
                continue # Revisit: log warning
            # convert the "attrs" tuples to a dictionary
            attrs = dict(msg[i]['attrs'])
            mgr_uuid = UUID(bytes=bytes(attrs['GENZ_A_UEP_MGR_UUID']))
            flags = attrs['GENZ_A_UEP_FLAGS']
            vers = flags & 0xf
            if vers != 2:
                log.warning(f'unexpected UEP info version: {vers} (expected 2)')
                continue
            attrs['GENZ_A_UEP_MGR_UUID'] = mgr_uuid
            ba = bytearray(attrs['GENZ_A_UEP_REC'])
            uep_rec = genz.UEPEventRecord.dataToRec(ba, verbosity=verbosity)
            attrs['GENZ_A_UEP_REC'] = uep_rec
            # We have to convert to json ourselves because if we try to let
            # requests do it, it doesn't get our magic to_json() stuff
            js = json.dumps(attrs)
            log.debug('kernel UEP msg: {}'.format(js))
            if keyboard:
                set_trace() # Revisit: temp debug
            msg = requests.post(url, data=js, headers=hdrs)
            # Revisit: finish this - msg logging/errors
        # end for
    # end while

def main():
    global args
    global cols
    global genz
    parser = argparse.ArgumentParser()
    parser.add_argument('-k', '--keyboard', action='store_true',
                        help='break to interactive keyboard at certain points')
    parser.add_argument('-v', '--verbosity', action='count', default=0,
                        help='increase output verbosity')
    parser.add_argument('-G', '--genz-version', choices=['1.1'],
                        default='1.1',
                        help='Gen-Z spec version of Control Space structures')
    parser.add_argument('-P', '--post_mortem', action='store_true',
                        help='enter debugger on uncaught exception')
    parser.add_argument('-U', '--url', default=None,
                        help='post UEP json to this url')
    args = parser.parse_args()
    if args.verbosity > 5:
        print('Gen-Z version = {}'.format(args.genz_version))
    netlink_reader(genz_version=args.genz_version, verbosity=args.verbosity,
                   url=args.url, keyboard=args.keyboard)

if __name__ == '__main__':
    try:
        main()
    except Exception as post_err:
        if args.post_mortem:
            traceback.print_exc()
            post_mortem()
        else:
            raise
