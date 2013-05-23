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

import eventlet
from eventlet import greenthread
import netaddr

from trove.common import cfg
from trove.db import models as dbmodels
from trove.openstack.common import log as logging
from trove.taskmanager import api as task_api


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class Configurations(object):

    @staticmethod
    def load(context):
        if context is None:
            raise TypeError("Argument context not defined.")
        elif id is None:
            raise TypeError("Argument is not defined.")

        # TODO(cp16net): Pagination support required!
        if context.is_admin:
            db_info = DBConfiguration.find_all()
        else:
            db_info = DBConfiguration.find_all(tenant_id=context.tenant)

        if db_info is None:
            LOG.debug("No configuration found for tenant % s" % context.tenant)

        return db_info


class Configuration(object):

    DEFAULT_LIMIT = CONF.instances_page_size

    @property
    def instances(self):
        return self.instances

    @property
    def items(self):
        return self.items

    @staticmethod
    def create(name, description, tenant_id):
        configurationGroup = DBConfiguration.create(name=name,
                                                    description=description,
                                                    tenant_id=tenant_id)
        return configurationGroup

    @staticmethod
    def create_items(cfg_id, values):
        LOG.debug("saving the values to the database")
        LOG.debug("cfg_id: %s" % cfg_id)
        LOG.debug("values: %s" % values)
        config_items = []
        for key, val in values.iteritems():
            config_item = ConfigurationItem.create(configuration_id=cfg_id,
                                                   configuration_key=key,
                                                   configuration_value=val)
            config_items.append(config_item)
        return config_items

    @staticmethod
    def delete(context, group):
        Configuration.remove_all_items(context, group.id)
        DBConfiguration.delete(group)

    @staticmethod
    def remove_all_items(context, id):
        LOG.debug("removing the values from the database")
        items = ConfigurationItem.find_all(configuration_id=id).all()
        LOG.debug("removing items: %s" % items)
        for item in items:
            ConfigurationItem.delete(item)

    @staticmethod
    def load(context, id):
        if context.is_admin:
            config_infos = DBConfiguration.find_by(id=id)
        else:
            config_infos = DBConfiguration.find_by(id=id,
                                                   tenant_id=context.tenant)
        return config_infos

    @staticmethod
    def load_items(context, id):
        config_items = ConfigurationItem.find_all(configuration_id=id).all()
        # todo(cp16net) list of items values should not all be strings.
        rules = cfg.get_validation_rules()
        def _get_rule(key):
            LOG.debug("finding rule with key : %s" % key)
            for rule in rules['configuration-parameters']:
                LOG.debug("rule : %s" % rule)
                if str(rule['name']) == key:
                    return rule
            return None
        for item in config_items:
            rule = _get_rule(str(item.configuration_key))
            LOG.debug("rule : %s" % rule)
            if rule['type'] == 'boolean':
                item.configuration_value = bool(int(item.configuration_value))
            elif rule['type'] == 'integer':
                item.configuration_value = int(item.configuration_value)
            elif rule['type'] == 'string':
                item.configuration_value = str(item.configuration_value)
        return config_items

    @staticmethod
    def save(context, configuration, configuration_items, instances):
        DBConfiguration.save(configuration)
        for item in configuration_items:
            config_item = ConfigurationItem.save(item)

        for instance in instances:
            overrides = {}
            for i in configuration_items:
                overrides[i.configuration_key] = i.configuration_value

            task_api.API(context).update_overrides(instance.id, overrides)


class DBConfiguration(dbmodels.DatabaseModelBase):
    _data_fields = ['name', 'description', 'tenant_id']


class ConfigurationItem(dbmodels.DatabaseModelBase):
    _data_fields = ['configuration_id', 'configuration_key',
                    'configuration_value']

    def __hash__(self):
        return self.configuration_key.__hash__()


def persisted_models():
    return {
        'configuration': DBConfiguration,
        'configuration_item': ConfigurationItem
    }
