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

from datetime import datetime
import eventlet
from eventlet import greenthread
import netaddr

from trove.common import cfg
from trove.common import configurations
from trove.common import pagination
from trove.db import models as dbmodels
from trove.openstack.common import log as logging
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

        # TODO(cp16net): Pagination support required!
        if context.is_admin:
            db_info = DBConfiguration.find_all(deleted=False)
        else:
            db_info = DBConfiguration.find_all(tenant_id=context.tenant,
                                               deleted=False)

        limit = int(context.limit or Configurations.DEFAULT_LIMIT)
        if limit > Configurations.DEFAULT_LIMIT:
            limit = Configurations.DEFAULT_LIMIT

        data_view = DBConfiguration.find_by_pagination('configurations',
                                                       db_info,
                                                       "foo",
                                                       limit=limit,
                                                       marker=context.marker)
        next_marker = data_view.next_page_marker

        if data_view is None:
            LOG.debug("No configuration found for tenant % s" % context.tenant)

        return data_view.collection, next_marker


class Configuration(object):

    @property
    def instances(self):
        return self.instances

    @property
    def items(self):
        return self.items

    @staticmethod
    def create(name, description, tenant_id, datastore, datastore_version):
        configurationGroup = DBConfiguration.create(name=name,
                                                    description=description,
                                                    tenant_id=tenant_id,
                                                    datastore_version_id=\
                                                    datastore_version)
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
        deleted_at = datetime.utcnow()
        Configuration.remove_all_items(context, group.id, deleted_at)
        group.deleted = True
        group.deleted_at = deleted_at
        group.save()

    @staticmethod
    def remove_all_items(context, id, deleted_at):
        LOG.debug("removing the values from the database")
        items = ConfigurationItem.find_all(configuration_id=id).all()
        LOG.debug("removing items: %s" % items)
        for item in items:
            item.deleted = True
            item.deleted_at = deleted_at
            item.save()

    @staticmethod
    def load(context, id):
        if context.is_admin:
            config_infos = DBConfiguration.find_by(id=id)
        else:
            config_infos = DBConfiguration.find_by(id=id,
                                                   tenant_id=context.tenant,
                                                   deleted=False)
        return config_infos

    @staticmethod
    def load_items(context, id):
        config_items = ConfigurationItem.find_all(configuration_id=id,
                                                  deleted=False).all()
        # todo(cp16net) list of items values should not all be strings.
        rules = configurations.get_validation_rules()

        def _get_rule(key):
            LOG.debug("finding rule with key : %s" % key)
            for rule in rules['configuration-parameters']:
                if str(rule['name']) == key:
                    return rule
            return None

        for item in config_items:
            rule = _get_rule(str(item.configuration_key))
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
            ConfigurationItem.save(item)

        for instance in instances:
            overrides = {}
            for i in configuration_items:
                overrides[i.configuration_key] = i.configuration_value

            task_api.API(context).update_overrides(instance.id, overrides)



class DBConfiguration(dbmodels.DatabaseModelBase):
    _data_fields = ['name', 'description', 'tenant_id', 'datastore_version_id',
                    'deleted', 'deleted_at']


class ConfigurationItem(dbmodels.DatabaseModelBase):
    _data_fields = ['configuration_id', 'configuration_key',
                    'configuration_value', 'deleted',
                    'deleted_at']

    def __hash__(self):
        return self.configuration_key.__hash__()


def persisted_models():
    return {
        'configurations': DBConfiguration,
        'configuration_items': ConfigurationItem
    }
