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

from oslo_serialization import jsonutils

import webob

from rackspace_cinder_extensions import test
from cinder import context
from cinder import db
from cinder.tests.unit.api import fakes


def app():
    # no auth, just let environ['cinder.context'] pass through
    api = fakes.router.APIRouter()
    mapper = fakes.urlmap.URLMap()
    mapper['/v2'] = api
    return mapper


class SnapshotProgressTestCase(test.TestCase):

    def test_update_progress(self):
        ctx = context.RequestContext('admin', 'fake', True)
        # snapshot in 'error_deleting'
        volume = db.volume_create(ctx, {})
        snapshot = db.snapshot_create(ctx, {'volume_id': volume['id']})
        req = webob.Request.blank('/v2/fake/snapshots/%s/action' %
                                  snapshot['id'])
        req.method = 'POST'
        req.headers['content-type'] = 'application/json'
        # request status of 'error'
        req.body = jsonutils.dumps({'os-update_progress': 'progress!'})
        # attach admin context to request
        req.environ['cinder.context'] = ctx
        resp = req.get_response(app())
        # request is accepted
        self.assertEquals(resp.status_int, 202)
        snapshot = db.snapshot_get(ctx, snapshot['id'])
        # status changed to 'error'
        self.assertEquals(snapshot['progress'], 'progress!')
