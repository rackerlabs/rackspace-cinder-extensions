#  Copyright 2013-2016 Rackspace US, Inc.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import webob
from webob import exc

from cinder.api import extensions
from cinder.api.openstack import wsgi
from cinder import db
from cinder import exception
from cinder.openstack.common import log as logging


LOG = logging.getLogger(__name__)


authorize = extensions.extension_authorizer('volume', 'snapshot_progress')


class SnapshotProgressController(wsgi.Controller):
    """Controller for updating snapshot progress field."""

    collection = 'snapshots'

    def __init__(self, *args, **kwargs):
        super(SnapshotProgressController, self).__init__(*args, **kwargs)

    @wsgi.action('os-update_progress')
    def _update_progress(self, req, id, body):
        """Update snapshot progress."""
        context = req.environ['cinder.context']
        authorize(context)
        progress = body['os-update_progress']
        msg = _("Updating snapshot '%(id)s' with '%(progress)r'")
        LOG.debug(msg, {'id': id, 'progress': progress})
        try:
            db.snapshot_update(context, id, {'progress': progress})
        except exception.NotFound, e:
            raise exc.HTTPNotFound(e)
        return webob.Response(status_int=202)


class Snapshot_progress(extensions.ExtensionDescriptor):
    """Enable snapshot progress."""

    name = "SnapshotProgress"
    alias = "os-snapshot-progress"
    namespace = "http://docs.openstack.org/volume/ext/admin-actions/api/v1.1"
    updated = "2012-08-25T00:00:00+00:00"

    def get_controller_extensions(self):
        controller = SnapshotProgressController()
        extension = extensions.ControllerExtension(self,
                                                   'snapshots',
                                                   controller)
        return [extension]
