# Rackspace Cinder Extensions

Extensions to [OpenStack](http://www.openstack.org/) [Cinder](https://github.com/openstack/cinder),
created by Rackers to enhance operations and the customer experience.

### Installation

The included `setup.py` can be used to build `.deb` or `.rpm` files:

    # to build a Debian/Ubuntu package
    python setup.py --command-packages=stdeb.command bdist_deb

    # to build an rpm package
    python setup.py bdist_rpm

### Snapshot_progress

Add this line to `cinder.conf`:

    osapi_volume_extension=rackspace_cinder_extensions.snapshot_progress.Snapshot_progress

