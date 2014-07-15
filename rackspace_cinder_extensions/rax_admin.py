#  Copyright 2014 Rackspace Corporation.
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

from cinder.openstack.common import log as logging
from cinder.db.sqlalchemy.api import model_query
from cinder.db.sqlalchemy import models
from cinder.api.openstack import wsgi
from cinder.api import extensions


LOG = logging.getLogger(__name__)
authorize = extensions.extension_authorizer('rax-admin', 'quota-list')


class RaxAdminController(wsgi.Controller):
    """
    This controller provides a place to put rackspace stuff that doesn't, or
    can't be put anywhere else. For example, you can execute the method
    _quota_list() with the following

    curl -i http://cinder.rackspace.com/v1/{tenant_id}/rax-admin/action \
        -X POST -d '{"quota-list": null}'

    """

    def __init__(self, *args, **kwargs):
        super(RaxAdminController, self).__init__(*args, **kwargs)

    @wsgi.action('quota-list')
    def _quota_list(self, req, body):
        """Fetch Quota stats from the db"""
        # Fetch the context for this request
        context = req.environ['cinder.context']
        # Verify the user accessing this resource is allowed?
        authorize(context)
        # Fetch all quota's that are not the default quota's
        rows = model_query(context, models.QuotaUsage, read_deleted="no").all()
        return dict( quotas=rows )


class Rax_admin(extensions.ExtensionDescriptor):
    """Enable Rax Admin Extension"""

    name = "Rax_admin"
    alias = "rax-admin"
    namespace = "http://docs.openstack.org/volume/ext/admin-actions/api/v1.1"
    updated = "2014-07-08T00:00:00+00:00"

    def get_resources(self):
        extension = extensions.ResourceExtension(
            "rax-admin", RaxAdminController(),
            collection_actions={'action': 'POST'})
        return [extension]
