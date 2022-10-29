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
from genz.genz_common import GCID, CState
from pdb import set_trace, post_mortem
import traceback

INVALID_GCID = GCID(val=0xffffffff)
INVALID_UUID = UUID(int=0xffffffffffffffffffffffffffffffff)

def get_gcid(comp_path):
    gcid = comp_path / 'gcid'
    try:
        with gcid.open(mode='r') as f:
            return GCID(str=f.readline().rstrip())
    except FileNotFoundError:
        return INVALID_GCID

def get_cuuid(comp_path):
    cuuid = comp_path / 'c_uuid'
    try:
        with cuuid.open(mode='r') as f:
            return UUID(f.readline().rstrip())
    except FileNotFoundError:
        return INVALID_UUID

def get_cclass(comp_path):
    cclass = comp_path / 'cclass'
    try:
        with cclass.open(mode='r') as f:
            return int(f.readline().rstrip())
    except FileNotFoundError:
        return None

def get_serial(comp_path):
    serial = comp_path / 'serial'
    try:
        with serial.open(mode='r') as f:
            return int(f.readline().rstrip(), base=0)
    except FileNotFoundError:
        return None

def get_class_uuid(res_path):
    class_uuid = res_path / 'class_uuid'
    try:
        with class_uuid.open(mode='r') as f:
            return UUID(f.readline().rstrip())
    except FileNotFoundError:
        return None

def get_instance_uuid(res_path):
    instance_uuid = res_path / 'instance_uuid'
    try:
        with instance_uuid.open(mode='r') as f:
            return UUID(f.readline().rstrip())
    except FileNotFoundError:
        return None

def get_driver(res_path):
    drv_link = res_path / 'driver'
    if drv_link.is_symlink():
        drv = drv_link.readlink()
        return drv.name
    return None

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
    if ctl is None:
        return None
    core_path = ctl / 'core@0x0' / 'core'
    try:
        core = get_struct(core_path, map)
        cs = genz.CStatus(core.CStatus, core)
        cstate = CState(cs.field.CState)
    except FileNotFoundError:
        cstate = CState(7)
    return cstate

def cuuid_serial(cuuid, serial):
    return str(cuuid) + ':' + '{:#018x}'.format(serial) if serial is not None else '???'

class Res:
    def __init__(self, path):
        self.path = path
        self.name = path.name.split(':')[-1]
        self.class_uuid = get_class_uuid(path)
        self.instance_uuid = get_instance_uuid(path)
        self.driver = get_driver(path)

    def __lt__(self, other): # sort based on name
        return self.name < other.name

    def __str__(self):
        return '{:19s} {}:{} {}'.format(self.name, self.class_uuid,
                                        self.instance_uuid, self.driver)

class Comp:
    def __init__(self, fabnum, path, map=None, name=None, dr=False, verbosity=0):
        self.fabnum = fabnum
        self.path = path
        self.gcid = get_gcid(path)
        self.cuuid = get_cuuid(path)
        self.cclass = get_cclass(path)
        self.serial = get_serial(path)
        self.cuuid_sn = cuuid_serial(self.cuuid, self.serial)
        self.name = name if name is not None else self.cclass_name
        self.verbosity = verbosity
        self.map = map
        self.dr = dr
        self.cstate = None
        if map is not None:
            self.ctl = path / ('' if self.dr else 'control')
        else:
            self.ctl = None
        self.res = []

    def get_cstate(self):
        self.cstate = get_cstate(self.ctl, self.map)

    @property
    def cclass_name(self):
        try:
            return genz.cclass_name[self.cclass]
        except (IndexError, TypeError):
            return 'Unknown'

    def check_selected(self, args, match_cuuids, match_serials,
                       match_fabrics, match_gcids, match_cclasses):
        selected = True
        if args.cuuid is not None:
            selected &= (self.cuuid in match_cuuids)
        if args.serial is not None:
            selected &= (self.serial in match_serials)
        if args.fabric is not None:
            selected &= (self.fabnum in match_fabrics)
        if args.gcid is not None:
            selected &= (self.gcid in match_gcids)
        if args.cclass is not None:
            selected &= (self.cclass in match_cclasses)
        return selected

    def add_resources(self, resources):
        for res_path in resources:
            res = Res(res_path)
            self.res.append(res)
        # end for res

    def ls_resources(self):
        if self.verbosity > 0:
            try:
                for res in sorted(self.res):
                    print('  {}'.format(res))
            except BrokenPipeError:
                return
        # end if

    def ls_comp(self, ignore_dr=True):
        parents = {}
        drs = []
        # defer cstate read until component is "selected"
        self.get_cstate()
        # one-line component summary first
        print(self)
        if self.verbosity < 1:
            return drs
        # then resources (if any)
        self.ls_resources()
        if self.ctl is None:
            return drs
        # of all structures, do core structure first
        core_path = self.ctl / 'core@0x0' / 'core'
        try:
            core = get_struct(core_path, self.map, verbosity=self.verbosity)
        except FileNotFoundError:
            return drs
        try:
            if self.verbosity > 1:
                print('  {}='.format('core@0x0'), end='')
                print(core)
        except BrokenPipeError:
            return drs
        parents['core@0x0'] = core
        # get (but don't print) the switch structure - save in core for later
        try:
            sw_dir = list(self.ctl.glob('component_switch@*'))[0]
            sw_path = sw_dir / 'component_switch'
            sw = get_struct(sw_path, self.map, verbosity=self.verbosity)
            core.sw = sw
        except IndexError:
            core.sw = None
        # also comp_dest
        try:
            cd_dir = list(self.ctl.glob('component_destination_table@*'))[0]
            cd_path = cd_dir / 'component_destination_table'
            cd = get_struct(cd_path, self.map, verbosity=self.verbosity)
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
            rc = get_struct(rc_path, self.map, verbosity=self.verbosity)
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
        for dir, dirnames, filenames in os.walk(self.ctl):
            dirnames.sort()
            #print('dir={}, dirnames={}, filenames={}'.format(dir, dirnames, filenames))
            if dir[-3:] == '/dr':
                drs.append(Comp(self.fabnum, Path(dir), map=self.map, dr=True,
                                verbosity=self.verbosity))
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
                if self.verbosity < 2 and file != 'interface': # ignore non-interfaces
                    continue;
                try:
                    equals = self.verbosity > 1
                    print('  {}{}'.format(dpath.name, '=' if equals else ' '), end='')
                    fpath = dpath / file
                    parent = get_parent(fpath, dpath, parents)
                    if struct is None:
                        struct = get_struct(fpath, self.map, core=core, parent=parent,
                                            verbosity=self.verbosity)
                    print(struct)
                except BrokenPipeError:
                    return drs
                parents[dpath.name] = struct
            # end for filenames
        # end for dir
        return drs

    def __lt__(self, other): # sort based on GCID
        if type(self) != type(other):
            return NotImplemented
        return self.gcid < other.gcid

    def __str__(self):
        if self.dr:
            return 'dr: {}'.format(self.path) # Revisit: better format
        else:
            return '{}:{} {:10s} {} {}'.format(self.fabnum, self.gcid,
                                               self.name,
                                               self.cuuid_sn, self.cstate)

def main():
    global args
    global cols
    global genz
    parser = argparse.ArgumentParser()
    parser.add_argument('-k', '--keyboard', action='store_true',
                        help='break to interactive keyboard at certain points')
    parser.add_argument('-c', '--cclass', action='store', default=None, nargs='+',
                        help='select only components with this component class (cclass)')
    parser.add_argument('-f', '--fabric', action='store', default=None, nargs='+',
                        help='select only components with this fabric number')
    parser.add_argument('-g', '--gcid', action='store', default=None, nargs='+',
                        help='select only components with this GCID')
    parser.add_argument('-s', '--serial', action='store', default=None, nargs='+',
                        help='select only components with this serial number')
    parser.add_argument('-u', '--cuuid', action='store', default=None, nargs='+',
                        help='select only components with this class UUID (cuuid)')
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
    try:
        match_fabrics = [] if args.fabric is None else [int(f, base=10) for f in args.fabric]
    except ValueError:
        print('invalid fabric number: {}'.format(args.fabric))
        exit(1)
    try:
        match_gcids = [] if args.gcid is None else [GCID(str=g) for g in args.gcid]
    except ValueError:
        print('invalid GCID: {}'.format(args.gcid))
        exit(1)
    try:
        match_serials = [] if args.serial is None else [int(s, base=0) for s in args.serial]
    except ValueError:
        print('invalid serial number: {}'.format(args.serial))
        exit(1)
    try:
        match_cuuids = [] if args.cuuid is None else [UUID(u) for u in args.cuuid]
    except ValueError:
        print('invalid class uuid: {}'.format(args.cuuid))
        exit(1)
    match_cclasses = []
    for c in (args.cclass if args.cclass is not None else []):
        try:
            match_cclasses.extend(genz.cclass_name_to_classes[c])
        except KeyError:
            try:
                match_cclasses.append(int(c, base=0))
            except ValueError:
                print(f'invalid cclass name/number: {c}')
                exit(1)
    if args.fake_root is not None:
        sys_devices = Path(args.fake_root) / 'sys/devices'
    else:
        sys_devices = Path('/sys/devices')
    dev_fabrics = sys_devices.glob('genz*')      # locally-visible Gen-Z devices
    genz_fabrics = Path('/sys/bus/genz/fabrics') # fabric components (FM-only)
    all_comps = {}
    for fab in dev_fabrics:
        comps = {}
        fabnum = component_num(fab)
        bridges = fab.glob('bridge*') # local bridges
        for br_path in bridges:
            brnum = component_num(br_path)
            br = Comp(fabnum, br_path, map=map, name='bridge{}'.format(brnum),
                      verbosity=args.verbosity)
            if args.keyboard:
                set_trace()
            selected = br.check_selected(args, match_cuuids, match_serials,
                                         match_fabrics, match_gcids,
                                         match_cclasses)
            if selected:
                comps[br.cuuid_sn] = br # save br for later printing
        # end for br_path
        fab_comps = genz_fabrics.glob('fabric{}/*:*/*:*:*'.format(fabnum)) # FM-visible components
        for comp_path in fab_comps:
            comp = Comp(fabnum, comp_path, map=map, verbosity=args.verbosity)
            if args.keyboard:
                set_trace()
            selected = comp.check_selected(args, match_cuuids, match_serials,
                                           match_fabrics, match_gcids,
                                           match_cclasses)
            if selected:
                if not comp.cuuid_sn in comps.keys():
                    comps[comp.cuuid_sn] = comp # save comp for later printing
            if args.verbosity < 1:
                continue
        # end for comp
        os_comps = fab.glob('*:*/*:*:*') # other OS-visible Gen-Z devices
        for comp_path in os_comps:
            comp = Comp(fabnum, comp_path, verbosity=args.verbosity)
            if args.keyboard:
                set_trace()
            selected = comp.check_selected(args, match_cuuids, match_serials,
                                           match_fabrics, match_gcids,
                                           match_cclasses)
            if not selected:
                continue
            if comp.cuuid_sn in comps.keys():
                # merge resources into existing Comp
                existing = comps[comp.cuuid_sn]
                existing.add_resources(comp_path.glob('genz{}:*'.format(comp_path.name)))
            else:
                comp.add_resources(comp_path.glob('genz{}:*'.format(comp_path.name)))
                comps[comp.cuuid_sn] = comp # save comp for later printing
        # end for comp_path
        if args.keyboard:
            set_trace()
        # now we actually print things
        for comp in sorted(comps.values()):
            if comp.cuuid_sn not in all_comps.keys():
                drs = comp.ls_comp()
                for dr in drs:
                    _ = dr.ls_comp(ignore_dr=False)
        # end for comp
        all_comps |= comps
    # end for fab
    if args.keyboard:
        set_trace()
    return

if __name__ == '__main__':
    try:
        main()
    except Exception as post_err:
        if args.post_mortem:
            traceback.print_exc()
            post_mortem()
        else:
            raise
