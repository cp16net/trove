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

import json
from datetime import datetime

from trove.common import cfg
from trove.common import configurations
from trove.common import utils
from trove.common.exception import ModelNotFoundError
from trove.datastore.models import DatastoreVersion
from trove.db import get_db_api
from trove.db import models as dbmodels
from trove.openstack.common import log as logging
from trove.openstack.common.gettextutils import _
from trove.taskmanager import api as task_api


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class Configurations(object):

    DEFAULT_LIMIT = CONF.configurations_page_size

    @staticmethod
    def load(context):
        if context is None:
            raise TypeError("Argument context not defined.")
        elif id is None:
            raise TypeError("Argument is not defined.")

        if context.is_admin:
            db_info = DBConfiguration.find_all(deleted=False)
            if db_info is None:
                LOG.debug(_("No configurations found"))
        else:
            db_info = DBConfiguration.find_all(tenant_id=context.tenant,
                                               deleted=False)
            if db_info is None:
                LOG.debug(_("No configurations found for tenant % s")
                          % context.tenant)

        limit = int(context.limit or Configurations.DEFAULT_LIMIT)
        if limit > Configurations.DEFAULT_LIMIT:
            limit = Configurations.DEFAULT_LIMIT

        data_view = DBConfiguration.find_by_pagination('configurations',
                                                       db_info,
                                                       "foo",
                                                       limit=limit,
                                                       marker=context.marker)
        next_marker = data_view.next_page_marker
        return data_view.collection, next_marker


class Configuration(object):

    def __init__(self, context, configuration_id):
        self.context = context
        self.configuration_id = configuration_id

    @property
    def instances(self):
        return self.instances

    @property
    def items(self):
        return self.items

    @staticmethod
    def create(name, description, tenant_id, datastore, datastore_version):
        configurationGroup = DBConfiguration.create(
            name=name,
            description=description,
            tenant_id=tenant_id,
            datastore_version_id=datastore_version)
        return configurationGroup

    @staticmethod
    def create_items(cfg_id, values):
        LOG.debug(_("saving the values to the database"))
        LOG.debug(_("cfg_id: %s") % cfg_id)
        LOG.debug(_("values: %s") % values)
        config_items = []
        for key, val in values.iteritems():
            config_item = ConfigurationParameter.create(
                configuration_id=cfg_id,
                configuration_key=key,
                configuration_value=val)
            config_items.append(config_item)
        return config_items

    @staticmethod
    def delete(context, group):
        deleted_at = datetime.utcnow()
        Configuration.remove_all_items(context, group.id, deleted_at)
        group.deleted = True
        group.deleted_at = deleted_at
        group.save()

    @staticmethod
    def remove_all_items(context, id, deleted_at):
        LOG.debug(_("removing the values from the database with configuration"
                    " %s") % id)
        items = ConfigurationParameter.find_all(configuration_id=id,
                                                deleted=False).all()
        LOG.debug(_("removing items: %s") % items)
        for item in items:
            item.deleted = True
            item.deleted_at = deleted_at
            item.save()

    @staticmethod
    def load_configuration_datastore_version(context, id):
        config = Configuration.load(context, id)
        datastore_version = DatastoreVersion.load_by_uuid(
            config.datastore_version_id)
        return datastore_version

    @staticmethod
    def load(context, id):
        try:
            if context.is_admin:
                config_info = DBConfiguration.find_by(id=id,
                                                      deleted=False)
            else:
                config_info = DBConfiguration.find_by(id=id,
                                                      tenant_id=context.tenant,
                                                      deleted=False)
        except ModelNotFoundError:
            msg = _("Configuration group with ID %s could not be found.") % id
            raise ModelNotFoundError(msg)
        return config_info

    @staticmethod
    def load_items(context, id):
        datastore = Configuration.load_configuration_datastore_version(context,
                                                                       id)
        config_items = ConfigurationParameter.find_all(configuration_id=id,
                                                       deleted=False).all()
        rules = configurations.get_validation_rules(
            datastore_manager=datastore.manager)

        def _get_rule(key):
            LOG.debug(_("finding rule with key : %s") % key)
            for rule in rules['configuration-parameters']:
                if str(rule.get('name')) == key:
                    return rule

        for item in config_items:
            rule = _get_rule(str(item.configuration_key))
            if rule.get('type') == 'boolean':
                item.configuration_value = bool(int(item.configuration_value))
            elif rule.get('type') == 'integer':
                item.configuration_value = int(item.configuration_value)
            else:
                item.configuration_value = str(item.configuration_value)
        return config_items

    def get_configuration_overrides(self):
        """Gets the overrides dict to apply to an instance"""
        overrides = {}
        if self.configuration_id:
            config_items = Configuration.load_items(self.context,
                                                    id=self.configuration_id)

            for i in config_items:
                overrides[i.configuration_key] = i.configuration_value
        return overrides

    def does_configuration_need_restart(self):
        config_items = Configuration.load_items(self.context,
                                                id=self.configuration_id)
        for i in config_items:
            details = DatastoreConfigurationParameters.load_parameter_by_name(
                i.configuration_key)
            if bool(details.restart_required):
                return True
        return False

    @staticmethod
    def save(context, configuration, configuration_items, instances):
        DBConfiguration.save(configuration)
        for item in configuration_items:
            item["deleted_at"] = None
            ConfigurationParameter.save(item)

        items = Configuration.load_items(context, configuration.id)

        for instance in instances:
            LOG.debug(_("applying to instance: %s") % instance.id)
            overrides = {}
            for i in items:
                overrides[i.configuration_key] = i.configuration_value

            task_api.API(context).update_overrides(instance.id, overrides)


class DBConfiguration(dbmodels.DatabaseModelBase):
    _data_fields = ['name', 'description', 'tenant_id', 'datastore_version_id',
                    'deleted', 'deleted_at']


class ConfigurationParameter(dbmodels.DatabaseModelBase):
    _data_fields = ['configuration_id', 'configuration_key',
                    'configuration_value', 'deleted',
                    'deleted_at']

    def __hash__(self):
        return self.configuration_key.__hash__()


class DatastoreConfigurationParameters(dbmodels.DatabaseModelBase):
    """Model for storing the configuration parameters on a datastore"""
    _auto_generated_attrs = ['id']
    _data_fields = [
        'name',
        'datastore_version_id',
        'restart_required',
        'max_size',
        'min_size',
        'data_type',
        'deleted',
        'deleted_at',
    ]
    _table_name = "datastore_configuration_parameters"
    preserve_on_delete = True

    @classmethod
    def load_parameters(cls, datastore_version_id):
        config_parameters = get_db_api().find_all(
            cls,
            datastore_version_id=datastore_version_id
        )
        return config_parameters

    @classmethod
    def load_parameter(cls, config_id):
        config_parameter = get_db_api().find_by(cls,
                                                config_id)
        return config_parameter

    @classmethod
    def load_parameter_by_name(cls, config_name):
        config_parameter = get_db_api().find_by(cls,
                                                name=config_name)
        return config_parameter


def create_datastore_configuration_parameter(name, datastore_version_id,
                                             restart_required, data_type,
                                             max_size, min_size):
    get_db_api().configure_db(CONF)
    datastore_version = DatastoreVersion.load_by_uuid(datastore_version_id)
    config = DatastoreConfigurationParameters(
        id=utils.generate_uuid(),
        name=name,
        datastore_version_id=datastore_version.id,
        restart_required=restart_required,
        data_type=data_type,
        max_size=max_size,
        min_size=min_size,
        deleted=False,
    )
    get_db_api().save(config)


def modify_datastore_configuration_parameter(id, name, datastore_version_id,
                                             restart_required, data_type,
                                             max_size, min_size):
    get_db_api().configure_db(CONF)
    config = DatastoreConfigurationParameters.load_parameter(id)
    datastore_version = DatastoreVersion.load_by_uuid(datastore_version_id)
    config.name = name
    config.datastore_version_id = datastore_version.id
    config.restart_required = restart_required
    config.data_type = data_type
    config.max_size = max_size
    config.min_size = min_size
    get_db_api().save(config)


def delete_datastore_configuration_parameter(id):
    get_db_api().configure_db(CONF)
    config = DatastoreConfigurationParameters.load_parameter(id)
    config.delete()


def load_datastore_configuration_parameters(datastore_version_id, config_file):
    with open(config_file) as f:
        config = json.load(f)
        for param in config['configuration-parameters']:
            create_datastore_configuration_parameter(
                param['name'],
                datastore_version_id,
                param['restart_required'],
                param['type'],
                param.get('max'),
                param.get('min'),
            )


def persisted_models():
    return {
        'configurations': DBConfiguration,
        'configuration_parameters': ConfigurationParameter,
        'datastore_configuration_parameters': DatastoreConfigurationParameters,
    }
