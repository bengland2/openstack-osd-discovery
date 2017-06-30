
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

All parameters are optional.   They are:

* --result-dir (default /var/tmp/introspect_dir) - where YAML data is generated 
* --device-name-pattern - regular expression for candidate device names
* --device-size - size of selected devices in GB +/- 7%
* --rotational - boolean, lets you select rotational/non-rotational devices
* --journal-pattern - regular expression for Ceph journal devices
* --min-journals-per-node - positive integer, error reported if fewer journals than this found on node

NOTE: due to introspection bug 1466045 in guessing system disk, you may need to provide root disk hints to OOO, this script doesn't do that, yet.

This script has been tested with a 192-OSD scale lab configuration including Dell 730xd servers.  It correctly generated yaml for 192 OSDs.   For example:

    ./introspect-for-osds.py --result-dir ../introspect_dir3 \
      --journal-pattern 'nvme[0-9]n1' \
      --device-size 500 \
      --device-name-pattern 'sd[b-z]' \


For best results:
* review yaml before using it, this tool is new and could have bugs.    
* specify OSD drive size 
* specify journal drive name pattern
* specify OSD device name pattern
