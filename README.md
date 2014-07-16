# Rackspace Cinder Extensions

Extensions to [OpenStack](http://www.openstack.org/) [Cinder](https://github.com/openstack/cinder),
created by Rackers to enhance operations and the customer experience.

### Installation

The included `setup.py` can be used to build `.deb` files for Debian or Ubuntu.
First you'll need to install some prerequisite packages:

    apt-get install python-stdeb fakeroot python-all

To build for a specific release create a `stdeb.cfg` file and add the following,
replacing `precise` with your release codename:

    [DEFAULT]
    Suite: precise

Now build the `.deb` file:

    python setup.py --command-packages=stdeb.command bdist_deb

### Load all Extensions in the rackspace Extension package

Add this line to `cinder.conf`:

    osapi_volume_extension = rackspace_cinder_extensions.rax_extensions

### Load Extension: os-snapshot-progress

Add this line to `cinder.conf`:

    osapi_volume_extension=rackspace_cinder_extensions.snapshot_progress.Snapshot_progress

### Load Extension: rax-admin

Add this line to `cinder.conf`:

    osapi_volume_extension=rackspace_cinder_extensions.rax_admin.Rax_admin

