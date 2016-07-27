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
from cinder.api import xmlutil

from lunrclient import client
from lunrclient.base import LunrHttpError
from lunrclient.client import LunrClient, StorageClient


LOG = logging.getLogger(__name__)
authorize = extensions.soft_extension_authorizer('volume',
                                                 'volume_lunr_sessions')


class VolumeLunrSessionsController(wsgi.Controller):
    def _add_lunr_sessions(self, req, resp_volume):
        # tenant attribute may not be populated, it's another extension
        db_volume = req.get_db_volume(resp_volume['id'])
        project_id = db_volume['project_id']
        lunr_sessions = []

        lunr_client = LunrClient('admin')
        try:
            lunr_volume = lunr_client.volumes.get(resp_volume['id'])
            lunr_info = dict(lunr_volume)
            storage_node = lunr_client.nodes.get(lunr_volume['node_id'])
            url = 'http://%s:8081' % storage_node['hostname']
            storage_client = StorageClient(url, timeout=5)
            try:
                export_info = storage_client.exports.get(resp_volume['id'])
                sessions = export_info.get('sessions', [])
                for session in sessions:
                    lunr_sessions.append(session['ip'])
            except LunrHttpError as e:
                if e.code != 404:
                    raise
        except Exception as e:
            lunr_sessions.append("error: %s" % e)

        key = "%s:lunr_sessions" % Volume_lunr_sessions.alias
        resp_volume[key] = lunr_sessions

    @wsgi.extends
    def show(self, req, id):
        context = req.environ['cinder.context']
        if authorize(context):
            authorized = True
            req.environ['cinder.context'] = context.elevated()
            resp_obj = yield
            resp_obj.attach(xml=VolumeLunrSessionsTemplate())
            volume = resp_obj.obj['volume']
            self._add_lunr_sessions(req, volume)
        else:
            yield


class Volume_lunr_sessions(extensions.ExtensionDescriptor):
    """Elevate volume list context to an admin context."""

    name = "VolumeLunrSessions"
    alias = "rs-vol-lunr-sessions"
    namespace = ("http://docs.rackspace.com/volume/ext/"
                 "volume_lunr_sessions/api/v2")
    updated = "2016-06-09T17:48:37+00:00"

    def get_controller_extensions(self):
        controller = VolumeLunrSessionsController()
        extension = extensions.ControllerExtension(self, 'volumes', controller)
        return [extension]


def make_volume(elem):
    elem.set('{%s}lunr_sessions' % Volume_lunr_sessions.namespace,
             '%s:lunr_sessions' % Volume_lunr_sessions.alias)


class VolumeLunrSessionsTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        root = xmlutil.TemplateElement('volume', selector='volume')
        make_volume(root)
        alias = Volume_lunr_sessions.alias
        namespace = Volume_lunr_sessions.namespace
        return xmlutil.SlaveTemplate(root, 1, nsmap={alias: namespace})

