#!/usr/bin/python

# introspect-for-osds.py - this script automatically generates
# YAML specifying OSDs for an entire OpenStack cluster, no matter how big,
# using filtering parameters to select OSDs from introspection data,
# and using WWN of block device to avoid problems with 
# device name changes after reboot, which happens frequently during
# a tripleo deploy.
#
# Copyright 2012 -- Ben England
# Licensed under the Apache License at http://www.apache.org/licenses/LICENSE-2.0
# See Appendix on this page for instructions pertaining to license.
#
# to get help:
#   ./introspect-for-osds.py -h
# run example:
#   ./introspect-for-osds.py \
#       --device-name-pattern 'sd*[a-z]' --device-size 1.8 \
#       > osd-devices.yaml

import os
import os.path
from os.path import join
import sys
from sys import argv
import json
import subprocess
import re

NOTOK = 1   # process exit status for failure
OK = 0      # process exit status for success


# we accept devices within this fraction of target size

size_tolerance = 0.05  # 10%

def parse_pos_int(intstr):
    try:
        intval = int(intstr)
    except ValueError:
        usage('%s: not an integer' % intstr)
    if intval <= 0:
        usage('%s: not a positive integer' % intval)
    return intval

# all boolean inputs parsed this way

def parsebool(boolstr):
    b = boolstr.upper()
    if b.startswith('Y') or b == 'TRUE' or b == '1':
        return True
    elif b.startswith('N') or b == 'FALSE' or b == '0':
        return False
    else:
        usage('boolean input must be either Y(es)/True/1 or N(o)/False/0')

# used for formatting boolean output

def bool_str(boolval, if_false, if_true):
    if boolval:
        return if_true
    else:
        return if_false

# we write messages to user via stderr because most likely stdout is being
# trapped to a output file

def w(msg):
    sys.stderr.write(msg)
    sys.stderr.write('\n')

# all-purpose error handling

def usage(msg):
    w('ERROR: %s' % msg)
    w('usage: introspect.py')
    w('  --result-dir directory')
    w('  --device-name-pattern regular-expression')
    w('  --device-size GB')
    w('  --rotational Y|N')
    w('  --journal-pattern regular-expression')
    w('  --min-journals-per-node count')
    w('  --debug Y|N')
    w('  --reuse-old-data Y|N')
    w(' NOTE: all parameters optional')
    sys.exit(NOTOK)

# no default values of OSD filter parameters

node_dir = '/var/tmp/introspect_dir'
want_name_regex = None
want_size_GB = None
want_rotational = 'undefined'
want_journal_regex = None
min_j_per_n = None
debug = False
reuse_old_data = None

# parse input parameters

argc = len(argv)
argindex = 1
while argindex < argc:
    pname = argv[argindex]
    if not pname.startswith('--'):
        usage('every parameter name prefixed by "--"')
    pname = pname[2:]
    if argindex == argc - 1:
        usage('every parameter name must have a following value')
    pval = argv[argindex + 1]
    argindex += 2
    if pname == 'device-size':
        want_size_GB = float(pval)
    elif pname == 'rotational':
        want_rotational = parsebool(pval)
    elif pname == 'device-name-pattern':
        want_name_regex = pval
    elif pname == 'journal-pattern':
        want_journal_regex = pval
    elif pname == 'result-dir':
        node_dir = pval
    elif pname == 'min-journals-per-node':
        min_j_per_n = parse_pos_int(pval)
    elif pname == 'debug':
        debug = parsebool(pval)
    elif pname == 'reuse-old-data':
        reuse_old_data = parsebool(pval)
    else:
        usage('invalid parameter name --%s' % pname)

# show parameters that you input

w('result directory: %s' % node_dir)
if want_name_regex: w('device name pattern: %s' % want_name_regex)
if want_journal_regex: w('journal name pattern: %s' % want_journal_regex)
if want_size_GB: w('device size (GB): %6.3f' % want_size_GB)
if want_rotational != 'undefined': w('device rotational? %s' % want_rotational)
if min_j_per_n: w('min journal devs per node: %d' % min_j_per_n)


if not os.path.exists(node_dir):
    os.mkdir(node_dir)
else:
    # don't leave stale YAML around
    for f in os.listdir(node_dir):
        if f.endswith('_devices.yaml'): 
            w('removing stale file %s' % f)
            os.unlink(join(node_dir,f))
        if f.endswith('.params') and not reuse_old_data:
            w('removing old saved introspection data %s' % f)
            os.unlink(join(node_dir,f))

# find out what nodes are in this openstack deployment
# assumes that the user has done source ~/stackrc or equivalent
# we allow program to reuse old data from a previous run 
# for debugging purposes, but default is to go to the source

node_uuids_path = join(node_dir, 'node-uuids.list')
uuid_list = []
if (not os.path.exists(node_uuids_path)) or (not reuse_old_data):
    w('asking openstack for list of bare metal hosts')
    raw_output = subprocess.check_output(
            [ 'openstack', 'baremetal', 'node', 'list' ])
    if debug: w(raw_output)
    for l in raw_output.split('\n'):
        if l.startswith('|'):
            if not l.__contains__('UUID'):
                uuid_list.append(l.split()[1])
    with open(node_uuids_path, 'w') as uuidfile:
        for u in uuid_list:
            uuidfile.write(u + '\n')
else:
    with open(node_uuids_path, 'r') as uuidfile:
        uuid_list.extend( [ uuid.strip() for uuid in uuidfile.readlines() ] )

# build up a table of system block devices so we can filter them out

root_device_table = {}
node_json = {}
for uuid in uuid_list:
    parampath= join(node_dir, '%s.params' % uuid)
    if os.path.exists(parampath):
        stinfo = os.stat(parampath)
        if stinfo.st_size == 0:
            os.unlink(parampath)
    if os.path.exists(parampath) and reuse_old_data:
        with open(parampath, 'r') as prmfile:
            json_obj = json.load(prmfile)
    else:
        w('querying introspection data for host %s' % uuid)
        json_string = subprocess.check_output(
            ['openstack', 'baremetal', 'introspection', 'data', 'save', uuid])
        if debug: w('%s raw per-node json: %s' % (uuid, json_string))
        json_obj = json.loads(json_string)
        with open(parampath, 'w') as prmfile:
            prmfile.write(json_string + '\n')
    node_json[uuid] = json_obj
    root_device_obj = json_obj['root_disk']
    root_devicepath = root_device_obj['name']
    if debug: w('root device = %s' % root_devicepath)
    root_devicename = os.path.basename(root_devicepath)
    # we need WWN (WWID) to identify device stably across reboots
    try:
        root_device_wwid = json_obj['extra']['disk'][root_devicename]['wwn-id']
    except KeyError:
	if debug: w('no WWN for device %s' % root_devicename)
	root_device_wwid = 'name.' + root_devicename
    # save info about root devices indexed by wwid so we can filter them out

    root_device_table[uuid] = (root_device_wwid, root_devicename, root_device_obj)

if debug: w(str(root_device_table))

# build up a table of SSD journals 

journal_table = {}
if want_journal_regex:
  for uuid in uuid_list:
    json_obj = node_json[uuid]
    journal_devs = 0
    journal_candidates = json_obj['extra']['disk'].keys()

    # include device listed as root_disk because introspection may be wrong
    # see bz 1466045
  
    try:
        (root_device_wwid, root_devicename, _) = root_device_table[uuid]
        journal_candidates.append(root_devicename)
    except KeyError:
        pass  # it was NOT in the boot device table, no need to add to candidates

    for device_name in journal_candidates:
        if device_name == 'logical':
            # not a device, just a count of devices
            continue
        try:
            device_obj = json_obj['extra']['disk'][device_name]
        except KeyError:
            if debug:
                w(' journal candidate %s not in extra disk table' % device_name)
            device_obj = json.loads('{}')
        try:
            device_wwid = device_obj['wwn-id']
        except KeyError:
            if debug: 
                w(' journal candidate %s has no wwn-id, using device name instead' 
                  % device_name)
            device_wwid = 'name.' + device_name
        if debug: w('evaluating block device %s id %s' % (device_name, device_wwid))


        # filter on journal regex if provided

        if want_journal_regex == None:
            continue  # we are doing journal co-located with OSD device
        else:      
            if not re.search(want_journal_regex, device_name):
                if debug:
                    w(' not a journal device because %s does not match regex %s' % (
                        device_name, want_journal_regex))
                continue
        journal_devs += 1
        try:
            journal_table[uuid].append(device_wwid)
        except KeyError:
            journal_table[uuid] = [device_wwid]
    if min_j_per_n:
        if journal_devs < min_j_per_n:
            usage('%s: only %d journal devices, expect to have at least %d' %
                  (uuid, journal_devs, min_j_per_n))

  if debug:
    w('journal devices:')
    w(str(journal_table))

# for each device in introspected hosts

osd_count = 0
node_counts = {}

# FIXME: what if we are extending a deployment,
# how do we avoid nuking existing nodes?

# generate yaml for each node defining OSDs in that node.

for uuid in uuid_list:
    w('uuid %s' % uuid)
    osds_in_this_node = 0
    try:
        journal_list = journal_table[uuid]
    except KeyError:
        journal_list = None
    json_obj = node_json[uuid]
    yaml_path = join(node_dir, '%s_devices.yaml' % uuid)
    tmp_path = join(node_dir, 'tmp.yaml')
    yaml_file = open(tmp_path, 'w')
    ywr = lambda line: yaml_file.write('%s\n' % line)
    ywr('    resource_registry:')
    ywr('      OS::TripleO::CephStorageExtraConfigPre: tripleo-heat-templates/puppet/extraconfig/pre_deploy/per_node.yaml')
    ywr('    parameter_defaults:')
    ywr('      NodeDataLookup: >')
    ywr('        {"%s":' % uuid)
    ywr('          {"ceph::profile::params::osds":{')
    osd_candidates = json_obj['extra']['disk'].keys()

    # include device listed as root_disk because introspection may be wrong
    # see bz 1466045
  
    try:
        (root_device_wwid, root_devicename, device_obj) = root_device_table[uuid]
        osd_candidates.append(root_devicename)
    except KeyError:
        pass  # it was NOT in the boot device table, no need to add to candidates

    for device_name in osd_candidates:
        if device_name == 'logical':
            # not a device, just a count of devices
            continue
        try:
            device_obj = json_obj['extra']['disk'][device_name]
        except KeyError:
            if debug:
                w(' device %s not in extra disk table' % device_name)
                w(' root_disk info: %s' % str(device_obj))
        try:
            device_wwid = device_obj['wwn-id']
        except KeyError:
            if debug: 
                w(' device %s has no wwn-id, using device name instead' 
                  % device_name)
            device_wwid = 'name.' + device_name
            continue
        if debug: w('evaluating device %s id %s' % (device_name, device_wwid))

        # do additional user-specified filtering

        if want_name_regex != None:
            if not re.search(want_name_regex, device_name):
                if debug:
                    w('rejecting because %s does not match regex %s' % (
                        device_name, want_name_regex))
                continue

        if want_size_GB != None:
            device_size_GB = float(device_obj['size'])
            abs_diff = abs((device_size_GB - want_size_GB)/device_size_GB)
            if abs_diff > size_tolerance:    # if more than X% different size
                if debug:
                    w((' rejecting because device size %f ' + 
                       ' different than specified size %f') % (
                           device_size_GB, want_size_GB))
                continue

        if want_rotational != 'undefined':
            device_rotational = (str(device_obj['rotational']) == '1')
            if device_rotational != want_rotational:
                if debug:
                  w( (' rejecting because device %s rotational ' + 
                      ' and we want device to %s rotational') % 
                    (bool_str(device_rotational, 'is not', 'is'),
                     bool_str(want_rotational, 'not be', 'be')))
                continue

        # found an OSD! output YAML for it

	osd_count += 1
        osds_in_this_node += 1

        try:
            node_counts[uuid] += 1
        except KeyError:
            node_counts[uuid] = 1

        # determine device pathname to use
        # try to use WWN (WWID) if available
        # PCI NVM devices and the like don't have WWID

        if device_wwid.startswith('name.'):
            devid = "/dev/%s" % device_wwid.split('.')[1]
        else:
            devid = "/dev/disk/by-id/%s" % device_wwid

        # select a journal device if applicable, 
        # round-robin OSDs across available journal devices

        if not want_journal_regex or not journal_list:
            ywr('            # %s' % device_name)
            ywr('            "%s",' % devid)
        else:
            journal_wwid = journal_list[osds_in_this_node % len(journal_list)]
            if journal_wwid.startswith('name.'):
                journal_dev = '/dev/%s' % journal_wwid.split('.')[1]
            else:
                journal_dev = '/dev/disk/by-id/%s' % journal_wwid
            ywr('            # /dev/%s journal=%s' % (device_name, journal_dev))
            ywr('            "%s":{"journal":"%s"},' % (devid, journal_dev))

    ywr('          }')
    ywr('        }')
    ywr('      }')
    yaml_file.close()
    if osds_in_this_node > 0:
        os.rename(tmp_path, yaml_path)

# all done, just report summary of what we found

for uuid in uuid_list:
    try:
        osds_in_node = node_counts[uuid]
        w('%s : %8d' % (uuid, osds_in_node))
    except KeyError:
        pass
w('%d OSD drives output' % osd_count)
w('to see them, # more %s/*_devices.yaml' % node_dir)
