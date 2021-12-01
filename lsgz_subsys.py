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
import os
import ctypes
import re
from uuid import UUID
from pathlib import Path
from importlib import import_module
from genz.genz_common import GCID
from pdb import set_trace, post_mortem
import traceback

def get_gcid(comp_path):
    gcid = comp_path / 'gcid'
    with gcid.open(mode='r') as f:
        return GCID(str=f.readline().rstrip())

def get_cuuid(comp_path):
    cuuid = comp_path / 'c_uuid'
    with cuuid.open(mode='r') as f:
        return UUID(f.readline().rstrip())

def get_cclass(comp_path):
    cclass = comp_path / 'cclass'
    with cclass.open(mode='r') as f:
        return int(f.readline().rstrip())

def get_serial(comp_path):
    serial = comp_path / 'serial'
    with serial.open(mode='r') as f:
        return int(f.readline().rstrip(), base=0)

comp_num_re = re.compile(r'.*/([^0-9]+)([0-9]+)')

def component_num(comp_path):
    match = comp_num_re.match(str(comp_path))
    return int(match.group(2))

from functools import wraps
from time import time

def timing(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        start = time()
        result = f(*args, **kwargs)
        end = time()
        print(' [{} elapsed time: {}] '.format(f.__name__, end-start), end='')
        return result
    return wrapper

#@timing
def get_struct(fpath, map, parent=None, core=None, verbosity=0):
    fname = fpath.name.replace(fpath.suffix, '')
    with fpath.open(mode='rb') as f:
        try:  # Revisit: workaround for zero-length files
            data = bytearray(f.read())
        except OSError:
            size = fpath.stat().st_size
            if size == 0:
                return None
            else:
                raise
        struct = map.fileToStruct(fname, data, path=fpath,
                                  parent=parent, core=core,
                                  verbosity=verbosity)
        return struct

def get_parent(fpath, dpath, parents):
    parent = parents['core@0x0']  # default parent, if we do not find another
    for p in reversed(dpath.parents[0].parts):
        if p == 'control' or p == 'dr':
            break
        if '@0x' in p:
            parent = parents[p]
            break
    return parent

def get_cstate(ctl, map):
    core_path = ctl / 'core@0x0' / 'core'
    core = get_struct(core_path, map)
    cs = genz.CStatus(core.CStatus, core)
    cstate = cs._c_state[cs.field.CState]
    return cstate

def ls_comp(ctl, map, ignore_dr=True, verbosity=1):
    parents = {}
    drs = []
    # do core structure first
    core_path = ctl / 'core@0x0' / 'core'
    core = get_struct(core_path, map, verbosity=verbosity)
    try:
        if verbosity > 1:
            print('  {}='.format('core@0x0'), end='')
            print(core)
    except BrokenPipeError:
        return drs
    parents['core@0x0'] = core
    # get (but don't print) the switch structure - save in core for later
    try:
        sw_dir = list(ctl.glob('component_switch@*'))[0]
        sw_path = sw_dir / 'component_switch'
        sw = get_struct(sw_path, map, verbosity=verbosity)
        core.sw = sw
    except IndexError:
        core.sw = None
    # also comp_dest
    try:
        cd_dir = list(ctl.glob('component_destination_table@*'))[0]
        cd_path = cd_dir / 'component_destination_table'
        cd = get_struct(cd_path, map, verbosity=verbosity)
        core.comp_dest = cd
    except IndexError:
        core.comp_dest = None
    rc_dir = None
    if core.sw is not None:
        try:  # Revisit: route control is required, but missing in current HW
            rc_dir = list(sw_dir.glob('route_control@*'))[0]
        except IndexError:
            rc_dir = None
    elif core.comp_dest is not None:
        try:  # Revisit: route control is required, but missing in current HW
            rc_dir = list(cd_dir.glob('route_control@*'))[0]
        except IndexError:
            rc_dir = None
    if rc_dir is not None:
        rc_path = rc_dir / 'route_control'
        rc = get_struct(rc_path, map, verbosity=verbosity)
        core.route_control = rc
        cap1 = genz.RCCAP1(rc.RCCAP1, rc)
        hcs = cap1.field.HCS
        core.sw.HCS = hcs
        core.comp_dest.HCS = hcs
    else:
        core.route_control = None
        if core.sw is not None:
            core.sw.HCS = 0
        if core.comp_dest is not None:
            core.comp_dest.HCS = 0
    for dir, dirnames, filenames in os.walk(ctl):
        dirnames.sort()
        #print('dir={}, dirnames={}, filenames={}'.format(dir, dirnames, filenames))
        if dir[-3:] == '/dr':
            drs.append(Path(dir))
            continue
        elif ignore_dr and dir.find('/dr/') >= 0:
            continue
        dpath = Path(dir)
        for file in sorted(filenames):
            struct = None
            if file == 'core':  # we already did core
                continue
            elif file == 'component_switch':
                struct = core.sw
            elif file == 'component_destination_table':
                struct = core.comp_dest
            if verbosity < 2 and file != 'interface': # ignore non-interfaces
                continue;
            try:
                equals = verbosity > 1
                print('  {}{}'.format(dpath.name, '=' if equals else ' '), end='')
                fpath = dpath / file
                parent = get_parent(fpath, dpath, parents)
                if struct is None:
                    struct = get_struct(fpath, map, core=core, parent=parent,
                                        verbosity=verbosity)
                print(struct)
            except BrokenPipeError:
                return drs
            parents[dpath.name] = struct
        # end for filenames
    # end for dir
    return drs

def main():
    global args
    global cols
    global genz
    parser = argparse.ArgumentParser()
    parser.add_argument('-k', '--keyboard', action='store_true',
                        help='break to interactive keyboard at certain points')
    parser.add_argument('-v', '--verbosity', action='count', default=0,
                        help='increase output verbosity')
    parser.add_argument('-F', '--fake-root', action='store',
                        help='fake root directory')
    parser.add_argument('-G', '--genz-version', choices=['1.1'],
                        default='1.1',
                        help='Gen-Z spec version of Control Space structures')
    parser.add_argument('-P', '--post_mortem', action='store_true',
                        help='enter debugger on uncaught exception')
    parser.add_argument('-S', '--struct', action='store',
                        help='input file representing a single control structure')
    args = parser.parse_args()
    if args.verbosity > 5:
        print('Gen-Z version = {}'.format(args.genz_version))
    genz = import_module('genz.genz_{}'.format(args.genz_version.replace('.', '_')))
    map = genz.ControlStructureMap()
    if args.keyboard:
        set_trace()
    if args.struct:
        fpath = Path(args.struct)
        struct = get_struct(fpath, map, verbosity=args.verbosity)
        print(struct)
        return
    if args.fake_root is not None:
        sys_devices = Path(args.fake_root) / 'sys/devices'
    else:
        sys_devices = Path('/sys/devices')
    dev_fabrics = sys_devices.glob('genz*')
    for fab in dev_fabrics:
        fabnum = component_num(fab)
        #print('fabric: {}, num={}'.format(fab, fabnum))
        bridges = fab.glob('bridge*')
        for br in bridges:
            ctl = br / 'control'
            if args.keyboard:
                set_trace()
            gcid = get_gcid(br)
            cuuid = get_cuuid(br)
            cclass = get_cclass(br)
            serial = get_serial(br)
            cstate = get_cstate(ctl, map)
            brnum = component_num(br)
            print('{}:{} {:10s} {}:{:#018x} {}'.format(fabnum, gcid,
                                                       'bridge{}'.format(brnum),
                                                       cuuid, serial, cstate))
            if args.verbosity < 1:
                continue
            drs = ls_comp(ctl, map, verbosity=args.verbosity)
            for dr in drs:
                print('dr: {}'.format(dr))  # Revisit: better format
                if args.verbosity < 1:
                    continue
                # Revist: handle nested drs?
                _ = ls_comp(dr, map, ignore_dr=False, verbosity=args.verbosity)
        # end for br
    # end for fab
    genz_fabrics = Path('/sys/bus/genz/fabrics')
    fab_comps = genz_fabrics.glob('fabric*/*:*/*:*:*')
    for comp in sorted(fab_comps):
        ctl = comp / 'control'
        cuuid = get_cuuid(comp)
        cclass = get_cclass(comp)
        serial = get_serial(comp)
        cstate = get_cstate(ctl, map)
        print('{} {:10s} {}:{:#018x} {}'.format(comp.name, genz.cclass_name[cclass],
                                                cuuid, serial, cstate))
        if args.verbosity < 1:
            continue
        drs = ls_comp(ctl, map, verbosity=args.verbosity)
        for dr in drs:
            print('dr: {}'.format(dr))  # Revisit: better format
            if args.verbosity < 1:
                continue
            # Revist: handle nested drs?
            _ = ls_comp(dr, map, ignore_dr=False, verbosity=args.verbosity)
        # end for dr
    # end for comp

if __name__ == '__main__':
    try:
        main()
    except Exception as post_err:
        if args.post_mortem:
            traceback.print_exc()
            post_mortem()
        else:
            raise
