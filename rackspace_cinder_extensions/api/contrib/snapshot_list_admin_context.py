#  Copyright 2013-2016 Rackspace US, Inc.
#
#  Licensed under the Apache License, Version 2.0 (the "License"); you may
#  not use this file except in compliance with the License. You may obtain
#  a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#  WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#  License for the specific language governing permissions and limitations
#  under the License.

from oslo_log import log as logging

from cinder.api import extensions
from cinder.api.openstack import wsgi


LOG = logging.getLogger(__name__)
authorize = extensions.soft_extension_authorizer('snapshot',
                                                 'snapshot_list_admin_context')


class SnapshotListAdminContextController(wsgi.Controller):
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


class Snapshot_list_admin_context(extensions.ExtensionDescriptor):
    """Elevate snapshot list context to an admin context."""

    name = "SnapshotListAdminContext"
    alias = "rs-snap-list-admin-context"
    namespace = ("http://docs.rackspace.com/volume/ext/"
                 "snapshot_list_admin_context/api/v2")
    updated = "2016-06-09T17:48:37+00:00"

    def get_controller_extensions(self):
        controller = SnapshotListAdminContextController()
        extension = extensions.ControllerExtension(self, 'snapshots',
                                                   controller)
        return [extension]
