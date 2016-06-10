from oslo_log import log as logging

from rackspace_cinder_extensions.api import contrib


LOG = logging.getLogger(__name__)


def rax_extensions(ext_mgr):
    LOG.warning('The rackspace_cinder_extensions.rax_extensions loader '
                'is deprecated and will be removed in the v0.9 release.')
    contrib.standard_extensions(ext_mgr)
