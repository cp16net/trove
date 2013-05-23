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

from trove.openstack.common import log as logging

LOG = logging.getLogger(__name__)


class ConfigurationView(object):

    def __init__(self, configuration):
        self.configuration = configuration

    def data(self):
        configuration_dict = {
            "id": self.configuration.id,
            "name": self.configuration.name,
            "description": self.configuration.description
        }

        return {"configuration": configuration_dict}


class ConfigurationsView(object):

    def __init__(self, configurations):
        self.configurations = configurations

    def data(self):
        data = []

        for configuration in self.configurations:
            data.append(self.data_for_configuration(configuration))

        return {"configurations": data}

    def data_for_configuration(self, configuration):
        view = ConfigurationView(configuration)
        return view.data()['configuration']


class DetailedConfigurationView(object):

    def __init__(self, configuration):
        self.configuration = configuration

    def instances(self):
        instances_list = []

        for instance in self.configuration.instances:
            LOG.debug("creating view: %r" % instance)
            instances_list.append(
                {
                    "id": instance.id,
                    "name": instance.name
                }
            )
        return instances_list

    def instances_data(self):
        instances_list = self.instances()
        return {"instances": instances_list}

    def data(self):
        values = {}

        for configItem in self.configuration.items:
            key = configItem.configuration_key
            value = configItem.configuration_value
            values[key] = value

        instances_dict = self.instances()
        configuration_dict = \
            {
                "id": self.configuration.id,
                "name": self.configuration.name,
                "description": self.configuration.description,
                "values": values,
                "instances": instances_dict,
            }

        return {"configuration": configuration_dict}


class ConfigurationParametersView(object):

    def __init__(self, configurationParameters):
        self.configurationParameters = configurationParameters

    def data(self):
        return self.configurationParameters
