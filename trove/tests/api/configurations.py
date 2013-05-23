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


import json
import troveclient
from proboscis import SkipTest
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_true
from proboscis.decorators import time_out
from trove.tests.api.instances import assert_unprocessable
from trove.tests.api.instances import instance_info
from trove.tests.api.instances import WaitForGuestInstallationToFinish
from trove.tests.config import CONFIG
from trove.tests.util import create_dbaas_client
from trove.tests.util import poll_until
from trove.tests.util import test_config
from trove.tests.util.check import AttrCheck
from trove.tests.util.mysql import create_mysql_connection
from trove.tests.util.users import Requirements
from troveclient import exceptions


GROUP = "dbaas.api.configurations"
CONFIG_NAME = "test_configuration"
CONFIG_DESC = "configuration description"

configuration_info = None
configuration_href = None
configuration_instance_id = None

def execute_query(host, user_name, password, query):
    with create_mysql_connection(host, user_name, password) as db:
        return db.query(query)


# create configurations tests
#       in unit tests: create a small fake one and make sure it's working as expected
@test(depends_on_classes=[WaitForGuestInstallationToFinish], groups=[GROUP])
class CreateConfigurations(object):

    @test
    def test_expected_configurations_parameters(self):
        """test get expected configurations parameters"""
        expected_attrs = ["configuration-parameters"]
        instance_info.dbaas.configurations.parameters()
        resp, body = instance_info.dbaas.client.last_response
        attrcheck = AttrCheck()
        config_parameters_dict = json.loads(body)
        attrcheck.attrs_exist(config_parameters_dict, expected_attrs,
                              msg="Configurations parameters")
        # sanity check that a few options are in the list
        config_params_list = config_parameters_dict['configuration-parameters']
        config_params_keys = []
        for dict_item in config_params_list:
            for key in dict_item.keys():
                config_params_keys.append(key)
        expected_config_params = ['key_buffer_size', 'connect_timeout']
        for expected_config_item in expected_config_params:
            assert_true(expected_config_item in config_params_keys)

    @test
    def test_configurations_create_invalid_values(self):
        """test create configurations with invalid values"""
        values = '{"this_is_invalid": 123}'
        assert_unprocessable(instance_info.dbaas.configurations.create,
            CONFIG_NAME, values, CONFIG_DESC)

    @test
    def test_configurations_create_invalid_value_type(self):
        """test create configuration with invalild value type"""
        values = '{"key_buffer_size": "this is a string not int"}'
        assert_unprocessable(instance_info.dbaas.configurations.create,
            CONFIG_NAME, values, CONFIG_DESC)

    @test
    def test_configurations_create_value_out_of_bounds(self):
        """test create configuration with value out of bounds"""
        values = '{"connect_timeout": 1000000}'
        assert_unprocessable(instance_info.dbaas.configurations.create,
            CONFIG_NAME, values, CONFIG_DESC)
        values = '{"connect_timeout": -10}'
        assert_unprocessable(instance_info.dbaas.configurations.create,
            CONFIG_NAME, values, CONFIG_DESC)

    @test
    def test_valid_configurations_create(self):
        values = '{"connect_timeout": 120, "key_buffer_size": 1048576}'
        expected_values = json.loads(values)
        result = instance_info.dbaas.configurations.create(CONFIG_NAME,
                                                           values,
                                                           CONFIG_DESC)
        resp, body = instance_info.dbaas.client.last_response
        assert_equal(resp.status, 200)
        global configuration_info
        configuration_info = result
        assert_equal(configuration_info.name, CONFIG_NAME)
        assert_equal(configuration_info.description, CONFIG_DESC)
        assert_equal(configuration_info.values, expected_values)

    # @test(runs_after=[test_valid_configurations_create])
    def test_appending_to_existing_configuration(self):
        values = '{"join_buffer_size": 1048576, "connect_timeout": 60}'
        expected_values = json.loads(values)
        result = instance_info.dbaas.configurations.edit(configuration_info.id,
                                                         values)
        resp, body = instance_info.dbaas.client.last_response
        assert_equal(resp.status, 200)
        global configuration_info
        configuration_info = result
        print(result)
        assert_equal(configuration_info.name, CONFIG_NAME)
        assert_equal(configuration_info.description, CONFIG_DESC)
        assert_equal(configuration_info.values, expected_values)


@test(depends_on=[CreateConfigurations], groups=[GROUP])
class AfterConfigurationsCreation(object):

    @test
    def test_assign_configuration_to_invalid_instance(self):
        invalid_id = "invalid-inst-id"
        try:
            instance_info.dbaas.instances.modify(invalid_id,
                                                 configuration_info.id)
        except exceptions.NotFound as e:
            resp, body = instance_info.dbaas.client.last_response
            assert_equal(resp.status, 404)

    @test
    def test_assign_configuration_to_valid_instance(self):
        instance_info.dbaas.instances.modify(instance_info.id,
                                             configuration_info.id)
        resp, body = instance_info.dbaas.client.last_response
        assert_equal(resp.status, 202)


@test(depends_on=[AfterConfigurationsCreation], groups=[GROUP])
class ListConfigurations(object):

    @test
    def test_configurations_list(self):
        result = instance_info.dbaas.configurations.list()
        assert_equal(1, len(result))
        configuration = result[0]
        assert_equal(configuration.id, configuration_info.id)
        assert_equal(configuration.name, configuration_info.name)
        assert_equal(configuration.description, configuration_info.description)

    @test
    def test_configurations_list_for_instance(self):
        instance = instance_info.dbaas.instances.get(instance_info.id)
        assert_equal(instance.configuration['id'], configuration_info.id)
        assert_equal(instance.configuration['name'], configuration_info.name)
        # expecting two things in links, href and bookmark
        assert_equal(2, len(instance.configuration['links']))
        link = instance.configuration['links'][0]
        global configuration_href
        configuration_href = link['href']

    @test
    def test_configurations_get(self):
        result = instance_info.dbaas.configurations.get(configuration_info.id)
        assert_equal(configuration_info.id, result.id)
        assert_equal(configuration_info.name, result.name)
        assert_equal(configuration_info.description, result.description)

        # Test to make sure that another user is not able to GET this config
        reqs = Requirements(is_admin=False)
        other_user = CONFIG.users.find_user(reqs,
            black_list=[instance_info.user.auth_user])
        other_client = create_dbaas_client(other_user)
        assert_raises(exceptions.NotFound, other_client.configurations.get,
                      configuration_info.id)


@test(depends_on=[ListConfigurations], groups=[GROUP])
class StartInstanceWithConfiguration(object):

    @test
    def test_start_instance_with_configuration(self):
        if test_config.auth_strategy == "fake":
            raise SkipTest("Skipping instance start with configuration "
                           "test for fake mode.")
        result = instance_info.dbaas.instances.create(
            instance_info.name + "_configuration",
            instance_info.dbaas_flavor_href,
            instance_info.volume,
            configuration_ref=configuration_href)
        assert_equal(200, instance_info.dbaas.last_http_code)
        assert_equal("BUILD", result.status)
        global configuration_instance_id
        configuration_instance_id = result.id


@test(depends_on_classes=[StartInstanceWithConfiguration], groups=[GROUP])
class WaitForConfigurationInstanceToFinish(object):

    @test
    @time_out(60 * 32)
    def test_instance_with_configuration_active(self):
        if test_config.auth_strategy == "fake":
            raise SkipTest("Skipping instance start with configuration "
                           "test for fake mode.")

        def result_is_active():
            instance = instance_info.dbaas.instances.get(
                configuration_instance_id)
            if instance.status == "ACTIVE":
                return True
            else:
                assert_equal("BUILD", instance.status)
                return False

        poll_until(result_is_active)


@test(runs_after=[WaitForConfigurationInstanceToFinish], groups=[GROUP])
class DeleteConfigurations(object):

    @test
    def test_delete_invalid_configuration_not_found(self):
        invalid_configuration_id = "invalid-config-id"
        assert_raises(exceptions.NotFound,
                      instance_info.dbaas.configurations.delete,
                      invalid_configuration_id)

    @test
    def test_unable_delete_instance_configurations(self):
        assert_raises(exceptions.BadRequest,
                      instance_info.dbaas.configurations.delete,
                      configuration_info.id)

    @test(runs_after=[test_unable_delete_instance_configurations])
    def test_unassign_configuration_from_instances(self):
        instance_info.dbaas.instances.modify(instance_info.id,
            configuration_ref="")
        resp, body = instance_info.dbaas.client.last_response
        assert_equal(resp.status, 202)
        instance_info.dbaas.instances.modify(configuration_instance_id,
            configuration_ref="")
        resp, body = instance_info.dbaas.client.last_response
        assert_equal(resp.status, 202)

    @test(runs_after=[test_unassign_configuration_from_instances])
    def test_delete_configuration_instance(self):
        instance_info.dbaas.instances.delete(configuration_instance_id)
        assert_equal(202, instance_info.dbaas.last_http_code)

        def instance_is_gone():
            try:
                instance_info.dbaas.instances.get(configuration_instance_id)
                return False
            except exceptions.NotFound:
                return True

        poll_until(instance_is_gone)
        assert_raises(exceptions.NotFound, instance_info.dbaas.instances.get,
                      configuration_instance_id)

    @test(depends_on=[test_unassign_configuration_from_instances])
    def test_delete_unassigned_configuration(self):
        instance_info.dbaas.configurations.delete(configuration_info.id)
        resp, body = instance_info.dbaas.client.last_response
        assert_equal(resp.status, 202)
