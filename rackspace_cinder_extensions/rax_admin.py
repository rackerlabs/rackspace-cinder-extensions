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
from cinder.quota import QUOTAS
from sqlalchemy import and_


LOG = logging.getLogger(__name__)
authorize = extensions.extension_authorizer('rax-admin', 'quota-list')


class RaxAdminController(wsgi.Controller):
    """
    This controller provides a place to put rackspace stuff that doesn't, or
    can't be put anywhere else. For example, you can execute the method
    _quota_list() with the following

    curl -i http://cinder.rackspace.com/v1/{tenant_id}/rax-admin/action \
        -X POST -d '{"quota-in-use": null}'

    """
    def __init__(self, *args, **kwargs):
        super(RaxAdminController, self).__init__(*args, **kwargs)

    @wsgi.action('quota-usage')
    def _quota_usage(self, req, body):
        """
        Return a list of all quotas in the db and how
        much of the quota is in use
        """
        # Fetch the context for this request
        context = req.environ['cinder.context']
        # Verify the user accessing this resource is allowed?
        authorize(context)
        rows = model_query(context, models.Quota, models.QuotaUsage,
                           read_deleted="no").\
            filter(models.QuotaUsage.project_id == models.Quota.project_id).\
            filter(models.QuotaUsage.resource == models.Quota.resource).\
            order_by(models.Quota.project_id).all()
        result = [{'project_id': quota.project_id, 'resource': quota.resource,
                   'hard_limit': quota.hard_limit, 'in_use': usage.in_use}
                  for quota, usage in rows]
        return dict(quotas=result)

    @wsgi.action('top-usage')
    def _top_usage(self, req, body):
        """
        Return a list of project_id's with the most usage
        """
        def get_limit(quota, resource_name):
            if quota:
                return quota.hard_limit
            return default_quotas.get(resource_name, 'None')

        # Get the user specified limit, else default to the top 200 projects
        limit = int(body['top-usage'].get('limit', 200))

        result = []
        # Get the context for this request
        context = req.environ['cinder.context']
        # Verify the user accessing this resource is allowed?
        authorize(context)
        # Get all the quota defaults
        default_quotas = QUOTAS.get_defaults(context)
        # Fetch the projects with the most usage
        rows = model_query(context, models.QuotaUsage, read_deleted="no").\
            filter(models.QuotaUsage.resource == "gigabytes").\
            order_by(models.QuotaUsage.in_use.desc()).limit(limit).all()
        for row in rows:
            # For each project, fetch the usage and used
            quotas = model_query(context, models.QuotaUsage, models.Quota,
                                 read_deleted="no").\
                outerjoin(models.Quota, and_(models.QuotaUsage.project_id
                                             == models.Quota.project_id,
                                             models.QuotaUsage.resource
                                             == models.Quota.resource))\
                .filter(models.QuotaUsage.project_id == row.project_id)\
                .all()
            for usage, quota in quotas:
                result.append({
                    'project_id': usage.project_id,
                    'resource': usage.resource,
                    'hard_limit': get_limit(quota, usage.resource),
                    'in_use': usage.in_use})
        return dict(quotas=result)


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
