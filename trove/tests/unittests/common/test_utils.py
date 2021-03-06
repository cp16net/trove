# Copyright 2014 SUSE Linux GmbH.
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
#
from mock import Mock
from testtools import ExpectedException
from trove.common import exception
from trove.common import utils
from trove.tests.unittests import trove_testtools


class TestTroveExecuteWithTimeout(trove_testtools.TestCase):

    def setUp(self):
        super(TestTroveExecuteWithTimeout, self).setUp()
        self.orig_utils_execute = utils.execute
        self.orig_utils_log_error = utils.LOG.error

    def tearDown(self):
        super(TestTroveExecuteWithTimeout, self).tearDown()
        utils.execute = self.orig_utils_execute
        utils.LOG.error = self.orig_utils_log_error

    def test_throws_process_execution_error(self):
        utils.execute = Mock(
            side_effect=exception.ProcessExecutionError(
                description='test-desc', exit_code=42, stderr='err',
                stdout='out', cmd='test'))

        with ExpectedException(
                exception.ProcessExecutionError,
                "test-desc\nCommand: test\nExit code: 42\n"
                "Stdout: 'out'\nStderr: 'err'"):
            utils.execute_with_timeout('/usr/bin/foo')

    def test_log_error_when_log_output_on_error_is_true(self):
        utils.execute = Mock(
            side_effect=exception.ProcessExecutionError(
                description='test-desc', exit_code=42, stderr='err',
                stdout='out', cmd='test'))
        utils.LOG.error = Mock()

        with ExpectedException(
                exception.ProcessExecutionError,
                "test-desc\nCommand: test\nExit code: 42\n"
                "Stdout: 'out'\nStderr: 'err'"):
            utils.execute_with_timeout(
                '/usr/bin/foo', log_output_on_error=True)

        utils.LOG.error.assert_called_with(
            u"Command 'test' failed. test-desc Exit code: 42\n"
            "stderr: err\nstdout: out")

    def test_unpack_singleton(self):
        self.assertEqual([1, 2, 3], utils.unpack_singleton([1, 2, 3]))
        self.assertEqual(0, utils.unpack_singleton([0]))
        self.assertEqual('test', utils.unpack_singleton('test'))
        self.assertEqual('test', utils.unpack_singleton(['test']))
        self.assertEqual([], utils.unpack_singleton([]))
        self.assertEqual(None, utils.unpack_singleton(None))
        self.assertEqual([None, None], utils.unpack_singleton([None, None]))
        self.assertEqual('test', utils.unpack_singleton([['test']]))
        self.assertEqual([1, 2, 3], utils.unpack_singleton([[1, 2, 3]]))
        self.assertEqual(1, utils.unpack_singleton([[[1]]]))
        self.assertEqual([[1], [2]], utils.unpack_singleton([[1], [2]]))
        self.assertEqual(['a', 'b'], utils.unpack_singleton(['a', 'b']))
