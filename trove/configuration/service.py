# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2013 Rackspace
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


import routes
import webob.exc
import json

from trove.common import cfg
from trove.common import exception
from trove.common import pagination
from trove.common import template
from trove.common import utils
from trove.common import wsgi
from trove.configuration import models
from trove.configuration import views
from trove.configuration.models import ConfigurationItem
from trove.openstack.common import log as logging
from trove.openstack.common.gettextutils import _
from trove.instance import models as instances_models


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class ConfigurationsController(wsgi.Controller):
    def index(self, req, tenant_id):
        context = req.environ[wsgi.CONTEXT_KEY]
        configurations = models.Configurations.load(context)

        return wsgi.Result(views.ConfigurationsView(configurations).data(),
                           200)

    def show(self, req, tenant_id, id):
        context = req.environ[wsgi.CONTEXT_KEY]
        configuration = models.Configuration.load(context, id)
        configuration_items = models.Configuration.load_items(context, id)
        instances = instances_models.DBInstance.find_all(
            tenant_id=context.tenant,
            configuration_id=id,
            deleted=False).all()

        return wsgi.Result(views.DetailedConfigurationView(
                           configuration,
                           configuration_items,
                           instances).data(), 200)

    def instances(self, req, tenant_id, id):
        context = req.environ[wsgi.CONTEXT_KEY]
        configuration = models.Configuration.load(context, id)
        instances = instances_models.DBInstance.find_all(
            tenant_id=context.tenant,
            configuration_id=configuration.id,
            deleted=False).all()

        return wsgi.Result(views.DetailedConfigurationInstancesView(
                           instances).data(), 200)

    def create(self, req, body, tenant_id):
        LOG.debug(_("req : '%s'\n\n") % req)
        LOG.debug(_("body : '%s'\n\n") % req)

        name = body['configuration']['name']
        description = body['configuration'].get('description')
        values = body['configuration']['values']

        configItems = []
        if values:
            # validate that the values passed in are permitted by the operator.
            ConfigurationsController._validate_configuration(
                body['configuration']['values'])

            for k, v in values.iteritems():
                configItems.append(ConfigurationItem(configuration_key=k,
                                                     configuration_value=v))

        cfg_group = models.Configuration.create(name, description, tenant_id)
        cfg_group_items = models.Configuration.create_items(cfg_group.id,
                                                            values)
        view_data = views.DetailedConfigurationView(cfg_group,
                                                    cfg_group_items,
                                                    None)
        return wsgi.Result(view_data.data(), 200)

    def delete(self, req, tenant_id, id):
        context = req.environ[wsgi.CONTEXT_KEY]
        group = models.Configuration.load(context, id)
        instances = instances_models.DBInstance.find_all(
            tenant_id=context.tenant,
            configuration_id=id,
            deleted=False).all()
        if instances:
            raise exception.InstanceAssignedToConfiguration()
        models.Configuration.delete(context, group)
        return wsgi.Result(None, 202)

    def update(self, req, body, tenant_id, id):
        LOG.info(_("Updating configuration for tenant id %s" % tenant_id))
        context = req.environ[wsgi.CONTEXT_KEY]
        group = models.Configuration.load(context, id)
        cfg_items = models.Configuration.load_items(context, id)
        LOG.info(_("loaded configuration cfg_items: %s" % cfg_items))
        instances = instances_models.DBInstance.find_all(
            tenant_id=context.tenant,
            configuration_id=id,
            deleted=False).all()

        # if name/description are provided in the request body, update the
        # model with these values as well.
        if 'name' in body['configuration']:
            group.name = body['configuration']['name']

        if 'description' in body['configuration']:
            group.description = body['configuration']['description']

        items = self._configuration_items_list(group, body['configuration'])
        models.Configuration.remove_all_items(context, group.id)
        LOG.info(_("loaded configuration instances: %s" % instances))
        models.Configuration.save(context, group, items, instances)
        return wsgi.Result(None, 202)

    def edit(self, req, body, tenant_id, id):
        context = req.environ[wsgi.CONTEXT_KEY]
        group = models.Configuration.load(context, id)
        cfg_items = models.Configuration.load_items(context, id)
        LOG.info(_("loaded configuration cfg_items: %s" % cfg_items))
        instances = instances_models.DBInstance.find_all(
            tenant_id=context.tenant,
            configuration_id=id,
            deleted=False).all()
        LOG.info(_("loaded configuration instances: %s" % instances))
        items = self._configuration_items_list(group, body['configuration'])
        models.Configuration.save(context, group, items, instances)

    def _configuration_items_list(self, group, configuration):
        items = []
        LOG.info(_("loaded configuration group: %s" % group))
        if 'values' in configuration:
            # validate that the values passed in are permitted by the operator.
            ConfigurationsController._validate_configuration(
                configuration['values'])
            for k, v in configuration['values'].iteritems():
                items.append(ConfigurationItem(configuration_id=group.id,
                                               configuration_key=k,
                                               configuration_value=v))
        return items

    @staticmethod
    def _validate_configuration(values):
        rules = cfg.get_validation_rules()

        LOG.info(_("Validating configuration values"))
        for k, v in values.iteritems():
            # get the validation rule dictionary, which will ensure there is a
            # rule for the given key name. An exception will be thrown if no
            # valid rule is located.
            rule = ConfigurationsController._get_item(
                k, rules['configuration-parameters'])

            # type checking
            valueType = rule['type']

            if not isinstance(v, ConfigurationsController._find_type(
                    valueType)):
                raise exception.UnprocessableEntity(
                    message=_("Incorrect data type supplied as a value for key"
                              " %s. Expected type of %s." % (k, valueType)))

            # integer min/max checking
            if isinstance(v, int):
                try:
                    min_value = int(rule['min'])
                except ValueError:
                    raise exception.TroveError(_(
                        "Invalid or unsupported min value defined in the "
                        "configuration-parameters configuration file. "
                        "Expected integer."))
                if v < min_value:
                    raise exception.UnprocessableEntity(
                        message=_("Value for %s less than min." % k))

                try:
                    max_value = int(rule['max'])
                except ValueError:
                    raise exception.TroveError(_(
                        "Invalid or unsupported max value defined in the "
                        "configuration-parameters configuration file. "
                        "Expected integer."))
                if v > max_value:
                    raise exception.UnprocessableEntity(
                        message=_("Value for %s greater than max." % k))

    @staticmethod
    def _find_type(valueType):
        if valueType == "boolean":
            return bool
        elif valueType == "string":
            return basestring
        elif valueType == "integer":
            return int
        else:
            raise exception.TroveError(_(
                "Invalid or unsupported type defined in the "
                "configuration-parameters configuration file."))

    @staticmethod
    def _get_item(key, dictList):
        for item in dictList:
            if key == item['name']:
                return item
        raise exception.UnprocessableEntity(
            message=_("%s is not a supported configuration key. Please refer "
                      "to /configuration/parameters for a list of supported "
                      "keys." % key))


class ParametersController(wsgi.Controller):
    def index(self, req, tenant_id):
        rules = cfg.get_validation_rules()
        return wsgi.Result(views.ConfigurationParametersView(rules).data(),
                           200)

    def show(self, req, tenant_id, id):
        rules = cfg.get_validation_rules()
        for rule in rules['configuration-parameters']:
            if rule['name'] == id:
                return wsgi.Result(
                    views.ConfigurationParametersView(rule).data(), 200)
        raise exception.ConfigKeyNotFound(key=id)
