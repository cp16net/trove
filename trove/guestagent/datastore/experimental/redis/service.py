# Copyright (c) 2013 Rackspace
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

import os
import redis
from redis.exceptions import BusyLoadingError, ConnectionError

from oslo_log import log as logging

from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common import instance as rd_instance
from trove.common.stream_codecs import PropertiesCodec, StringConverter
from trove.common import utils as utils
from trove.guestagent.common.configuration import ConfigurationManager
from trove.guestagent.common.configuration import OneFileOverrideStrategy
from trove.guestagent.common import guestagent_utils
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.experimental.redis import system
from trove.guestagent.datastore import service
from trove.guestagent import pkg

LOG = logging.getLogger(__name__)
TIME_OUT = 1200  # FIXME(pmalik): should probably use config timeout
CONF = cfg.CONF
CLUSTER_CFG = 'clustering'
packager = pkg.Package()


class RedisAppStatus(service.BaseDbStatus):
    """
    Handles all of the status updating for the redis guest agent.
    """

    def __init__(self, client):
        super(RedisAppStatus, self).__init__()
        self.__client = client

    def set_client(self, client):
        self.__client = client

    def _get_actual_db_status(self):
        try:
            if self.__client.ping():
                return rd_instance.ServiceStatuses.RUNNING
        except ConnectionError:
            return rd_instance.ServiceStatuses.SHUTDOWN
        except BusyLoadingError:
            return rd_instance.ServiceStatuses.BLOCKED
        except Exception:
            LOG.exception(_("Error getting Redis status."))

        return rd_instance.ServiceStatuses.CRASHED


class RedisApp(object):
    """
    Handles installation and configuration of redis
    on a trove instance.
    """

    @classmethod
    def _init_overrides_dir(cls):
        """Initialize a directory for configuration overrides.
        """
        revision_dir = guestagent_utils.build_file_path(
            os.path.dirname(system.REDIS_CONFIG),
            ConfigurationManager.DEFAULT_STRATEGY_OVERRIDES_SUB_DIR)

        if not os.path.exists(revision_dir):
            operating_system.create_directory(
                revision_dir,
                user=system.REDIS_OWNER, group=system.REDIS_OWNER,
                force=True, as_root=True)

        return revision_dir

    def __init__(self, state_change_wait_time=None):
        """
        Sets default status and state_change_wait_time
        """
        if state_change_wait_time:
            self.state_change_wait_time = state_change_wait_time
        else:
            self.state_change_wait_time = CONF.state_change_wait_time

        revision_dir = self._init_overrides_dir()
        config_value_mappings = {'yes': True, 'no': False, "''": None}
        self._value_converter = StringConverter(config_value_mappings)
        self.configuration_manager = ConfigurationManager(
            system.REDIS_CONFIG,
            system.REDIS_OWNER, system.REDIS_OWNER,
            PropertiesCodec(
                unpack_singletons=False,
                string_mappings=config_value_mappings
            ), requires_root=True,
            override_strategy=OneFileOverrideStrategy(revision_dir))

        self.admin = self._build_admin_client()
        self.status = RedisAppStatus(self.admin)

    def _build_admin_client(self):
        password = self.get_configuration_property('requirepass')
        socket = self.get_configuration_property('unixsocket')

        return RedisAdmin(password=password, unix_socket_path=socket)

    def install_if_needed(self, packages):
        """
        Install redis if needed do nothing if it is already installed.
        """
        LOG.info(_('Preparing Guest as Redis Server.'))
        if not packager.pkg_is_installed(packages):
            LOG.info(_('Installing Redis.'))
            self._install_redis(packages)
        LOG.info(_('Redis installed completely.'))

    def complete_install_or_restart(self):
        """
        finalize status updates for install or restart.
        """
        LOG.debug("Complete install or restart called.")
        self.status.end_install_or_restart()

    def _install_redis(self, packages):
        """
        Install the redis server.
        """
        LOG.debug('Installing redis server.')
        msg = "Creating %s." % system.REDIS_CONF_DIR
        LOG.debug(msg)
        operating_system.create_directory(system.REDIS_CONF_DIR, as_root=True)
        pkg_opts = {}
        packager.pkg_install(packages, pkg_opts, TIME_OUT)
        self.start_redis()
        LOG.debug('Finished installing redis server.')

    def _enable_redis_on_boot(self):
        """
        Enables redis on boot.
        """
        LOG.info(_('Enabling Redis on boot.'))
        operating_system.enable_service_on_boot(system.SERVICE_CANDIDATES)

    def _disable_redis_on_boot(self):
        """
        Disables redis on boot.
        """
        LOG.info(_("Disabling Redis on boot."))
        operating_system.disable_service_on_boot(system.SERVICE_CANDIDATES)

    def stop_db(self, update_db=False, do_not_start_on_reboot=False):
        """
        Stops the redis application on the trove instance.
        """
        LOG.info(_('Stopping redis.'))
        if do_not_start_on_reboot:
            self._disable_redis_on_boot()

        operating_system.stop_service(system.SERVICE_CANDIDATES)
        if not self.status.wait_for_real_status_to_change_to(
                rd_instance.ServiceStatuses.SHUTDOWN,
                self.state_change_wait_time, update_db):
            LOG.error(_('Could not stop Redis.'))
            self.status.end_install_or_restart()

    def restart(self):
        """
        Restarts the redis daemon.
        """
        LOG.debug("Restarting Redis daemon.")
        try:
            self.status.begin_restart()
            self.stop_db()
            self.start_redis()
        finally:
            self.status.end_install_or_restart()

    def update_overrides(self, context, overrides, remove=False):
        if overrides:
            self.configuration_manager.apply_user_override(overrides)

    def apply_overrides(self, client, overrides):
        """Use the 'CONFIG SET' command to apply configuration at runtime.

        Commands that appear multiple times have values separated by a
        white space. For instance, the following two 'save' directives from the
        configuration file...

            save 900 1
            save 300 10

        ... would be applied in a single command as:

            CONFIG SET save "900 1 300 10"

        Note that the 'CONFIG' command has been renamed to prevent
        users from using it to bypass configuration groups.
        """
        for prop_name, prop_args in overrides.items():
            args_string = self._join_lists(
                self._value_converter.to_strings(prop_args), ' ')
            client.config_set(prop_name, args_string)

    def _join_lists(self, items, sep):
        """Join list items (including items from sub-lists) into a string.
        Non-list inputs are returned unchanged.

        _join_lists('1234', ' ') = "1234"
        _join_lists(['1','2','3','4'], ' ') = "1 2 3 4"
        _join_lists([['1','2'], ['3','4']], ' ') = "1 2 3 4"
        """
        if isinstance(items, list):
            return sep.join([sep.join(e) if isinstance(e, list) else e
                             for e in items])
        return items

    def remove_overrides(self):
        self.configuration_manager.remove_user_override()

    def start_db_with_conf_changes(self, config_contents):
        LOG.info(_('Starting redis with conf changes.'))
        if self.status.is_running:
            format = 'Cannot start_db_with_conf_changes because status is %s.'
            LOG.debug(format, self.status)
            raise RuntimeError(format % self.status)
        LOG.info(_("Initiating config."))
        self.configuration_manager.save_configuration(config_contents)
        # The configuration template has to be updated with
        # guestagent-controlled settings.
        self.apply_initial_guestagent_configuration()
        self.start_redis(True)

    def reset_configuration(self, configuration):
        LOG.info(_("Resetting configuration."))
        config_contents = configuration['config_contents']
        self.configuration_manager.save_configuration(config_contents)

    def start_redis(self, update_db=False):
        """
        Start the redis daemon.
        """
        LOG.info(_("Starting redis."))
        self._enable_redis_on_boot()
        operating_system.start_service(system.SERVICE_CANDIDATES)
        if not self.status.wait_for_real_status_to_change_to(
                rd_instance.ServiceStatuses.RUNNING,
                self.state_change_wait_time, update_db):
            LOG.error(_("Start up of redis failed."))
            try:
                utils.execute_with_timeout('pkill', '-9',
                                           'redis-server',
                                           run_as_root=True,
                                           root_helper='sudo')
            except exception.ProcessExecutionError:
                LOG.exception(_('Error killing stalled redis start command.'))
            self.status.end_install_or_restart()

    def apply_initial_guestagent_configuration(self):
        """Update guestagent-controlled configuration properties.
        """

        # Hide the 'CONFIG' command from end users by mangling its name.
        self.admin.set_config_command_name(self._mangle_config_command_name())

        self.configuration_manager.apply_system_override(
            {'daemonize': 'yes',
             'pidfile': system.REDIS_PID_FILE,
             'logfile': system.REDIS_LOG_FILE,
             'dir': system.REDIS_DATA_DIR})

    def get_config_command_name(self):
        """Get current name of the 'CONFIG' command.
        """
        renamed_cmds = self.configuration_manager.get_value('rename-command')
        for name_pair in renamed_cmds:
            if name_pair[0] == 'CONFIG':
                return name_pair[1]

        return None

    def _mangle_config_command_name(self):
        """Hide the 'CONFIG' command from the clients by renaming it to a
        random string known only to the guestagent.
        Return the mangled name.
        """
        mangled = utils.generate_random_password()
        self._rename_command('CONFIG', mangled)
        return mangled

    def _rename_command(self, old_name, new_name):
        """It is possible to completely disable a command by renaming it
        to an empty string.
        """
        self.configuration_manager.apply_system_override(
            {'rename-command': [old_name, new_name]})

    def get_logfile(self):
        """Specify the log file name. Also the empty string can be used to
        force Redis to log on the standard output.
        Note that if you use standard output for logging but daemonize,
        logs will be sent to /dev/null
        """
        return self.get_configuration_property('logfile')

    def get_db_filename(self):
        """The filename where to dump the DB.
        """
        return self.get_configuration_property('dbfilename')

    def get_working_dir(self):
        """The DB will be written inside this directory,
        with the filename specified the 'dbfilename' configuration directive.
        The Append Only File will also be created inside this directory.
        """
        return self.get_configuration_property('dir')

    def get_auth_password(self):
        """Client authentication password for this instance or None if not set.
        """
        return self.get_configuration_property('requirepass')

    def is_appendonly_enabled(self):
        """True if the Append Only File (AOF) persistence mode is enabled.
        """
        return self.get_configuration_property('appendonly', False)

    def get_append_file_name(self):
        """The name of the append only file (AOF).
        """
        return self.get_configuration_property('appendfilename')

    def is_cluster_enabled(self):
        """Only nodes that are started as cluster nodes can be part of a
        Redis Cluster.
        """
        return self.get_configuration_property('cluster-enabled', False)

    def enable_cluster(self):
        """In order to start a Redis instance as a cluster node enable the
        cluster support
        """
        self.configuration_manager.apply_system_override(
            {'cluster-enabled': 'yes'}, CLUSTER_CFG)

    def get_cluster_config_filename(self):
        """Cluster node configuration file.
        """
        return self.get_configuration_property('cluster-config-file')

    def set_cluster_config_filename(self, name):
        """Make sure that instances running in the same system do not have
        overlapping cluster configuration file names.
        """
        self.configuration_manager.apply_system_override(
            {'cluster-config-file': name}, CLUSTER_CFG)

    def get_cluster_node_timeout(self):
        """Cluster node timeout is the amount of milliseconds a node must be
        unreachable for it to be considered in failure state.
        """
        return self.get_configuration_property('cluster-node-timeout')

    def get_configuration_property(self, name, default=None):
        """Return the value of a Redis configuration property.
        Returns a single value for single-argument properties or
        a list otherwise.
        """
        return utils.unpack_singleton(
            self.configuration_manager.get_value(name, default))


class RedisAdmin(object):
    """Handles administrative tasks on the Redis database.
    """

    DEFAULT_CONFIG_CMD = 'CONFIG'

    def __init__(self, password=None, unix_socket_path=None):
        self.__client = redis.StrictRedis(
            password=password, unix_socket_path=unix_socket_path)
        self.__config_cmd_name = self.DEFAULT_CONFIG_CMD

    def set_config_command_name(self, name):
        """Set name of the 'CONFIG' command or None for default.
        """
        self.__config_cmd_name = name or self.DEFAULT_CONFIG_CMD

    def ping(self):
        """Ping the Redis server and return True if a response is received.
        """
        return self.__client.ping()

    def config_set(self, name, value):
        response = self.execute(
            '%s %s' % (self.__config_cmd_name, 'SET'), name, value)
        if not self._is_ok_response(response):
            raise exception.UnprocessableEntity(
                _("Could not set configuration property '%(name)s' to "
                  "'%(value)s'.") % {'name': name, 'value': value})

    def _is_ok_response(self, response):
        """Return True if a given Redis response is 'OK'.
        """
        return response and redis.client.bool_ok(response)

    def execute(self, cmd_name, *cmd_args):
        """Execute a command and return a parsed response.
        """
        try:
            return self._execute_command(cmd_name, *cmd_args)
        except Exception as e:
            LOG.exception(e)
            raise exception.TroveError(
                _("Redis command '%(cmd_name)s %(cmd_args)s' failed.")
                % {'cmd_name': cmd_name, 'cmd_args': ' '.join(cmd_args)})

    def _execute_command(self, *args, **options):
        """Execute a command and return a parsed response.
        """
        return self.__client.execute_command(*args, **options)
