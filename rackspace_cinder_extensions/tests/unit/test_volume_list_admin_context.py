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

import mock
import webob

from cinder import context
from cinder.tests.unit.api import fakes

from rackspace_cinder_extensions import test


class VolumeListAdminContextTestCase(test.TestCase):

    _authorized_roles = ['fake']
    _unauthorized_roles = []

    def _get_response(self, roles):
        ctx = context.RequestContext('admin', 'fake', False,
                                     roles=roles)

        req = webob.Request.blank('/v2/fake/volumes/detail'
                                  '?host=fake&all_tenants=1')
        req.method = 'GET'

        res = req.get_response(fakes.wsgi_app(fake_auth_context=ctx))

        return res

    @mock.patch('cinder.volume.api.API.get_all')
    def test_authorized_filter_context(self, get_all):
        roles = self._authorized_roles
        res = self._get_response(roles)

        self.assertEqual(200, res.status_int)

        get_all.assert_called_once_with(mock.ANY, mock.ANY, mock.ANY,
                                        filters={'host': 'fake',
                                                 'all_tenants': 1},
                                        offset=mock.ANY,
                                        sort_dirs=mock.ANY,
                                        sort_keys=mock.ANY,
                                        viewable_admin_meta=mock.ANY)

    @mock.patch('cinder.volume.api.API.get_all')
    def test_unauthorized_filter_context(self, get_all):
        roles = self._unauthorized_roles
        res = self._get_response(roles)

        self.assertEqual(200, res.status_int)

        get_all.assert_called_once_with(mock.ANY, mock.ANY, mock.ANY,
                                        filters={},
                                        offset=mock.ANY,
                                        sort_dirs=mock.ANY,
                                        sort_keys=mock.ANY,
                                        viewable_admin_meta=mock.ANY)
