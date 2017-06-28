
The idea is that no matter how large your openstack ceph deployment, 
you could just run introspection, run this script, and it will generate correct per-node yaml for your deployment, 
even if some nodes have slightly different device counts than other nodes.   
So your Ceph storage.yaml is reduced to around 10 lines that you have to write, and most of that is boilerplate.   
It does not require or use /dev/disk/by-path, using /dev/disk/by-id names instead wherever possible, 
because these too are stable across node reboots done by OOO.

WARNING: due to introspection bug 1466045 in reporting system disk info, 
this script doesn't always work correctly unless you specify the OSD size parameter.  
If we decide to implement something based on introspection data we should increase priority of bz 1466045.

I've tested it in two smaller openstack configs, will try to test it in a bigger one if possible.
