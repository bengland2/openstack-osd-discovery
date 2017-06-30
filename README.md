
No matter how large your openstack ceph deployment, you can auto-generate correct per-node yaml for your deployment using the
*introspect-for-osds.py* script.   This implementation prototype is intended to demonstrate how easy it could be to configure large OpenStack clusters if we leverage introspection data to do it.  Features:

* rule-based selection of OSD devices based on immutable, basic attributes:
  * size in GB
  * device name matching using a regular expression
  * rotational|non-rotational
* output YAML specifies OSD devices by WWN
  * uses /dev/disk/by-id/wwn- names that are invariant across reboots
  * does not require the user to specify /dev/disk/by-path names, ever
  * does not assume any device labeling
* automatically assigns SSD journal device to OSD for you
  * user specifies SSD journal devices using regular expression
  * script discovers them if they are there
  * user can specify minimum number of SSD journal devices per node

Unlike previous methods of specifying devices, this works even if some nodes have different device counts than other nodes, or slight variations in disk size. Your ceph-storage.yaml is reduced to around 10 lines that you have to write, and most of that is boilerplate.

To see CLI parameters for this script, 

    # ./introspect-for-osds.py -h

To run it:

    stack# source stackrc
    stack# ./introspect-for-osds.py

All parameters are optional but see warning below.   They are:

* --result-dir (default /var/tmp/introspect_dir) - where YAML data is generated 
* --device-name-pattern - regular expression for candidate device names
* --device-size - size of selected devices in GB +/- 7%
* --rotational - boolean, lets you select rotational/non-rotational devices
* --journal-pattern - regular expression for Ceph journal devices
* --min-journals-per-node - positive integer, error reported if fewer journals than this found on node

WARNING: due to introspection bug 1466045 in reporting system disk info, 
this script doesn't always work correctly unless you specify the OSD size parameter.  
If we decide to implement something based on introspection data we should increase priority of bz 1466045.

I've tested it in two smaller openstack configs, will try to test it in a bigger one if possible.
