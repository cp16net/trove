# Copyright 2014 Rackspace
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.


from trove.common import exception
from trove.common import wsgi
from trove.common.auth import admin_context
from trove.datastore import models as ds_models
from trove.configuration import models as config_models
from trove.openstack.common import log as logging
from trove.openstack.common.gettextutils import _
import trove.common.apischema as apischema


LOG = logging.getLogger(__name__)


class ConfigurationsParameterController(wsgi.Controller):
    """Controller for configuration parameters functionality"""
    schemas = apischema.mgmt_configuration

    @admin_context
    def create(self, req, body, tenant_id, version_id):
        """Create configuration parameter for datastore."""
        LOG.info(_("Creating configuration parameter for datastore"))
        LOG.debug(_("req : '%s'\n\n") % req)
        LOG.debug(_("body : '%s'\n\n") % body)
        if not body:
            raise exception.BadRequest(_("Invalid request body."))

        parameter = body['configuration-parameter']
        name = parameter['name']
        restart_required = bool(parameter['restart_required'])
        data_type = parameter['data_type']
        max_size = int(parameter['max_size'])
        min_size = int(parameter['min_size'])

        datastore_version = ds_models.DatastoreVersion.load_by_uuid(version_id)

        config_models.DatastoreConfigurationParameters.create(
            name=name,
            datastore_version_id=datastore_version.id,
            restart_required=restart_required,
            data_type=data_type,
            max_size=max_size,
            min_size=min_size
        )
        return wsgi.Result(None, 202)

    @admin_context
    def modify(self, req, body, tenant_id, version_id, parameter_name):
        """Modify configuration parameter for datastore."""
        LOG.info(_("Creating configuration parameter for datastore"))
        LOG.debug(_("req : '%s'\n\n") % req)
        LOG.debug(_("body : '%s'\n\n") % body)
        if not body:
            raise exception.BadRequest(_("Invalid request body."))

        #TODO(cp16net): MAKE THIS WORK AND DELETE
        # Check out if we are going to use uuid's or just the name

        parameter = body['configuration-parameter']
        name = parameter['name']
        restart_required = bool(parameter['restart_required'])
        data_type = parameter['data_type']
        max_size = int(parameter['max_size'])
        min_size = int(parameter['min_size'])

        datastore_version = ds_models.DatastoreVersion.load_by_uuid(version_id)

        config_models.DatastoreConfigurationParameters.create(
            name=name,
            datastore_version_id=datastore_version.id,
            restart_required=restart_required,
            data_type=data_type,
            max_size=max_size,
            min_size=min_size
        )
        return wsgi.Result(None, 202)
