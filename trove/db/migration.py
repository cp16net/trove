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

"""Database setup and migration commands."""

from trove import utils


IMPL = utils.LazyPluggable('db_backend',
                           config_group='database',
                           sqlalchemy='trove.db.sqlalchemy.migration')


def db_sync(version=None):
    """Migrate the database to `version` or the most recent version."""
    return IMPL.db_sync(version=version)


def db_upgrade(version=None, repo_path=None):
    """Migrate the database to `version` or the most recent version."""
    return IMPL.db_upgrade(version=version, repo_path=repo_path)


def db_version():
    """Display the current database version."""
    return IMPL.db_version()


def db_initial_version():
    """The starting version for the database."""
    return IMPL.db_initial_version()