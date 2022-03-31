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
from math import floor
from uuid import UUID
from pathlib import Path
from typing import List
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

array_re = re.compile(r'\[(?P<row>[0-9]+)\](\[(?P<col>[0-9]+)\])?$')

class Operation():
    def __init__(self, op_str: str):
        self.op_str = op_str
        self.parse_op_str()

    def parse_op_str(self):
        eq = self.op_str.find('=')
        self.write = eq > 0
        if self.write:
            # Revisit: support a mask like setpci?
            self.write_val = int(self.op_str[eq+1:], base=0)
            parts = self.op_str[:eq].split('.')
        else:
            parts = self.op_str.split('.')
        # look for 1- or 2-dimensional table indexing
        match = array_re.search(parts[0])
        if match is not None:
            self.row = int(match.group('row'))
            col = match.group('col')
            self.col = None if col is None else int(col)
            self.struct_name = parts[0][:match.span()[0]]
        else:
            self.row = None
            self.col = None
            self.struct_name = parts[0]
        plen = len(parts)
        if plen not in [1, 2, 3]: # struct, struct.field, struct.field.subfield
            raise AttributeError
        self.field_name = None if plen == 1 else parts[1]
        self.subfield_name = None if plen <= 2 else parts[2]

    def __repr__(self):
        r = type(self).__name__ + '('
        r += 'struct={}, row={}, col={}, field={}, subfield={}, write={}'.format(self.struct_name, self.row, self.col, self.field_name, self.subfield_name, self.write)
        r += ', write_val={}'.format(self.write_val) if self.write else ''
        r += ')'
        return r

file_re = re.compile(r'[\d]+$|([\d]*@0x.*$)')

class Comp:
    def __init__(self, fabnum, path, map=None, name=None, dr=False, verbosity=0):
        self.fabnum = fabnum
        self.path = path
        self.gcid = get_gcid(path)
        self.cuuid = get_cuuid(path)
        self.cclass = get_cclass(path)
        self.serial = get_serial(path)
        self.cuuid_sn = cuuid_serial(self.cuuid, self.serial)
        self.name = (name if name is not None else genz.cclass_name[self.cclass]
                     if self.cclass is not None else 'Unknown')
        self.verbosity = verbosity
        self.map = map
        self.dr =dr
        self.cstate = None
        if map is not None:
            self.ctl = path / ('' if self.dr else 'control')
        else:
            self.ctl = None

    def get_cstate(self):
        self.cstate = get_cstate(self.ctl, self.map)

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

    def find_struct(self, struct_name: str, parents):
        # Revisit: DR structures
        if struct_name == 'core' or struct_name == 'core@0x0':
            return self.core
        parts = struct_name.split('/')
        if len(parts) == 1: # no '/'
            fname = file_re.sub('', parts[0])
            paths = list(self.ctl.glob('**/{}*/{}'.format(parts[0], fname)))
        else: # have '/'
            fname = file_re.sub('', parts[1])
            paths = list(self.ctl.glob('**/{}*/**/{}*/{}'.format(parts[0], parts[1], fname)))
        # Revisit: exceptions?
        if len(paths) == 0: # not found
            return None
        elif len(paths) > 1: # ambiguous
            return None
        path = paths[0]
        parent = self.find_parent(path, parents)
        struct = get_struct(path, self.map, parent=parent, core=self.core,
                            verbosity=self.verbosity)
        return struct

    def find_parent(self, path, parents):
        dname = path.parents[0].name
        try:
            return parents[dname]
        except KeyError:
            pass
        parent = parents['core@0x0'] # default parent
        pdpath = path.parent.parents[0]
        ppath = pdpath / file_re.sub('', pdpath.name)
        try:
            parent = get_struct(ppath, self.map, core=self.core,
                                verbosity=self.verbosity)
            parents[dname] = parent
        except FileNotFoundError:
            pass
        return parent

    def field_off_sz(self, field, sz=None, off=0):
        start_bit = field.size & 0xffff
        bit_sz = field.size >> 16
        start_byte = floor(start_bit / 8)
        end_byte = floor((start_bit + bit_sz - 1) / 8)
        byte_sz = end_byte - start_byte + 1
        #print('  start_bit={}, bit_sz={}, start_byte={}, end_byte={}'.format(
        #    start_bit, bit_sz, start_byte, end_byte)) # Revisit
        return (off + field.offset + start_byte, byte_sz)

    def control_write(self, struct, elem, field_name: str,
                      sz=None, off=0, subfield=None):
        # Revisit: handle subfield
        field = getattr(elem.__class__, field_name)
        off, sz = self.field_off_sz(field, sz=sz, off=off)
        if struct.fullEntryWrite:
            sz = elem.Size
            off -= (off % sz) # align (downwards) to sz
        # print('  control_write: off={}, sz={}'.format(off, sz)) # Revisit
        # re-open file
        with struct.path.open(mode='rb+') as f:
            struct.set_fd(f)
            os.pwrite(struct.fd, struct.data[off:off+sz], off)

    def get_val(self, op: Operation, struct):
        val = None
        row = op.row
        col = op.col
        if row is not None and col is not None:
            try:
                elem = struct[row][col]
            except IndexError:
                elem = None
            elem_str = '[{}][{}]'.format(row, col)
            elem_off = struct.cs_offset(row, col)
        elif row is not None:
            try:
                elem = struct[row]
            except IndexError:
                elem = None
            elem_str = '[{}]'.format(row)
            elem_off = struct.cs_offset(row, col)
        else:
            elem = struct
            elem_str = ''
            elem_off = 0
        if elem is not None:
            val = (getattr(elem, op.field_name) if op.field_name is not None
                   else elem)
        return (val, elem, elem_str, elem_off)

    def do_read(self, op: Operation, struct):
        indent = '  ' if struct.verbosity > 0 else ''
        val, elem, elem_str, _ = self.get_val(op, struct)
        if elem is None:
            print('error: structure {}{} does not exist'.format(
                op.struct_name, elem_str))
            return
        if op.field_name is None:
            print('{}{}{} = {}'.format(
                indent, op.struct_name, elem_str, val))
        elif op.subfield_name is not None:
            special = elem.isSpecial(op.field_name)
            if special is None: # field has no subfields
                raise AttributeError
            val = getattr(special, op.subfield_name)
            print('{}{}{}.{}.{} = {:#x}'.format(
                indent, op.struct_name, elem_str, op.field_name, op.subfield_name, val))
        else: # no subfield
            print('{}{}{}.{} = {:#x}'.format(
                indent, op.struct_name, elem_str, op.field_name, val))

    def do_write(self, op: Operation, struct):
        indent = '  ' if struct.verbosity > 0 else ''
        before, elem, elem_str, elem_off = self.get_val(op, struct)
        if op.subfield_name is not None:
            special = elem.isSpecial(op.field_name)
            if special is None: # field has no subfields
                raise AttributeError
            before = getattr(special, op.subfield_name)
            setattr(special, op.subfield_name, op.write_val)
            print('{}{}{}.{}.{} = {:#x} (was {:#x})'.format(
                indent, op.struct_name, elem_str, op.field_name, op.subfield_name, op.write_val, before))
            after = special.val
            setattr(elem, op.field_name, after)
        else: # no subfield
            setattr(elem, op.field_name, op.write_val)
            print('{}{}{}.{} = {:#x} (was {:#x})'.format(indent, op.struct_name, elem_str, op.field_name, op.write_val, before))
        # write back modified value to HW
        self.control_write(struct, elem, op.field_name,
                           off=elem_off, subfield=op.subfield_name)

    def do_op(self, op: Operation, parents):
        struct = self.find_struct(op.struct_name, parents)
        if struct is None:
            print('error: component {} has no structure {}'.format(
                self.gcid, op.struct_name))
            return
        #if self.verbosity > 2:  # Revisit
        #    print(struct)
        try:
            if op.write:
                self.do_write(op, struct)
            else:
                self.do_read(op, struct)
        except AttributeError:
            if op.subfield_name is not None:
                print('error: {} has no field {}.{}'.format(
                    op.struct_name, op.field_name, op.subfield_name))
            else:
                print('error: {} has no field {}'.format(
                    op.struct_name, op.field_name))

    def set_comp(self, ops: List[Operation], ignore_dr=True):
        parents = {}
        drs = []
        # defer cstate read until component is "selected"
        self.get_cstate()
        # one-line component summary first (if verbose)
        if self.verbosity > 0:
            print(self)
        if self.ctl is None:
            return drs
        # get (but don't modify) the core structure
        core_path = self.ctl / 'core@0x0' / 'core'
        try:
            core = get_struct(core_path, self.map, verbosity=self.verbosity)
        except FileNotFoundError:
            return drs
        parents['core@0x0'] = core
        # get (but don't modify) the switch structure - save in core for later
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
        self.core = core
        for op in ops:
            self.do_op(op, parents)
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
    parser.add_argument('operations', type=str, nargs='+',
                        help='the read/write operations to perform')
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
    try:
        # Revisit: allow cclass names
        match_cclasses = [] if args.cclass is None else [int(c, base=0) for c in args.cclass]
    except ValueError:
        print('invalid cclass number: {}'.format(args.cclass))
        exit(1)
    ops = [Operation(op) for op in args.operations]
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
                comps[br.cuuid_sn] = br # save br for later processing
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
                    comps[comp.cuuid_sn] = comp # save comp for later processing
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
        # end for comp_path
        if args.keyboard:
            set_trace()
        # now we actually process things
        for comp in sorted(comps.values()):
            if comp.cuuid_sn not in all_comps.keys():
                drs = comp.set_comp(ops)
                # Revisit: how does user name a DR component?
                #for dr in drs:
                #    _ = dr.ls_comp(ignore_dr=False)
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
