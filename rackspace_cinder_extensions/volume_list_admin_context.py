from oslo_log import log as logging

from cinder.api import extensions
from cinder.api.openstack import wsgi


LOG = logging.getLogger(__name__)
authorize = extensions.soft_extension_authorizer('volume',
                                                 'volume_list_admin_context')


class VolumeListAdminContextController(wsgi.Controller):
    @wsgi.extends
    def index(self, req):
        context = req.environ['cinder.context']
        if authorize(context):
            req.environ['cinder.context'] = context.elevated()
        yield

    @wsgi.extends
    def detail(self, req):
        context = req.environ['cinder.context']
        if authorize(context):
            req.environ['cinder.context'] = context.elevated()
        yield


class Volume_list_admin_context(extensions.ExtensionDescriptor):
    """Elevate volume list context to an admin context."""

    name = "VolumeListAdminContext"
    alias = "rs-vol-list-admin-context"
    namespace = ("http://docs.rackspace.com/volume/ext/"
                 "volume_list_admin_context/api/v2")
    updated = "2016-06-09T17:48:37+00:00"

    def get_controller_extensions(self):
        controller = VolumeListAdminContextController()
        extension = extensions.ControllerExtension(self, 'volumes', controller)
        return [extension]
