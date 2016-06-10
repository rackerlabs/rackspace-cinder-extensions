import webob
import mock

from cinder import context
from cinder.tests.unit.api import fakes

from rackspace_cinder_extensions import test


class VolumeListAdminContextTestCase(test.TestCase):

    _authorized_roles = ['fake']
    _unauthorized_roles = []

    def _get_response(self, roles):
        ctx = context.RequestContext('admin', 'fake', False,
                                     roles=roles)

        req = webob.Request.blank('/v2/fake/volumes/detail?host=fake&all_tenants=1')
        req.method = 'GET'

        res = req.get_response(fakes.wsgi_app(fake_auth_context=ctx))

        return res

    @mock.patch('cinder.volume.api.API.get_all')
    def test_authorized_filter_context(self, get_all):
        roles = self._authorized_roles
        res = self._get_response(roles)

        self.assertEqual(200, res.status_int)

        get_all.assert_called_once_with(mock.ANY, mock.ANY, mock.ANY,
                                        filters={'host': 'fake', 'all_tenants': 1},
                                        offset=mock.ANY,
                                        sort_dirs=mock.ANY, sort_keys=mock.ANY,
                                        viewable_admin_meta=mock.ANY)

    @mock.patch('cinder.volume.api.API.get_all')
    def test_unauthorized_filter_context(self, get_all):
        roles = self._unauthorized_roles
        res = self._get_response(roles)

        self.assertEqual(200, res.status_int)

        get_all.assert_called_once_with(mock.ANY, mock.ANY, mock.ANY,
                                        filters={},
                                        offset=mock.ANY,
                                        sort_dirs=mock.ANY, sort_keys=mock.ANY,
                                        viewable_admin_meta=mock.ANY)
