from sg.sg_config_base import GatewayConfigBaseTest
from sg.sg_webhook_base import GatewayWebhookBaseTest
from remote.remote_util import RemoteMachineShellConnection

help_string = ['Usage of /opt/couchbase-sync-gateway/bin/sync_gateway:',
'  -adminInterface="127.0.0.1:4985": Address to bind admin interface to',
'  -bucket="sync_gateway": Name of bucket',
'  -configServer="": URL of server that can return database configs',
'  -dbname="": Name of Couchbase Server database (defaults to name of bucket)',
'  -deploymentID="": Customer/project identifier for stats reporting',
'  -interface=":4984": Address to bind to',
'  -log="": Log keywords, comma separated',
'  -logFilePath="": Path to log file',
'  -personaOrigin="": Base URL that clients use to connect to the server',
'  -pool="default": Name of pool',
'  -pretty=false: Pretty-print JSON responses',
'  -profileInterface="": Address to bind profile interface to',
'  -url="walrus:": Address of Couchbase server',
'  -verbose=false: Log more info about requests']

# Prerequisites:  Install Couchbase server on the local machine and run create_buckets.sh to create buckets.  Creation
# of buckets may also be done with https://github.com/membase/testrunner/blob/master/pytests/basetestcase.py#L347

class SGConfigTests(GatewayConfigBaseTest):
    def setUp(self):
        super(SGConfigTests, self).setUp()
        for server in self.servers:
            shell = RemoteMachineShellConnection(server)
            shell.copy_files_local_to_remote('pytests/sg/resources', '/root')

    def tearDown(self):
        super(SGConfigTests, self).tearDown()

    def configCBS(self):
        for server in self.servers:
            shell = RemoteMachineShellConnection(server)
            self.assertTrue(self.start_sync_gateway_template(shell, self.template))
            if not self.expected_error:
                success, revision = self.create_doc(shell)
                self.assertTrue(success)
                self.assertTrue(self.delete_doc(shell, revision))
            self.assertTrue(self.check_message_in_gatewaylog(shell, self.expected_log))
            shell.disconnect()

    def configStartSgw(self):
        for server in self.servers:
            shell = RemoteMachineShellConnection(server)
            self.assertTrue(self.start_sync_gateway(shell))
            self.assertTrue(self.check_message_in_gatewaylog(shell, self.expected_log))
            if not self.expected_error:
                if self.admin_port:
                    self.assertTrue(self.get_users(shell))
                if self.sync_port:
                    success, revision = self.create_doc(shell)
                    self.assertTrue(success)
                    self.assertTrue(self.delete_doc(shell, revision))
            shell.disconnect()

    def configHelp(self):
        for server in self.servers:
            shell = RemoteMachineShellConnection(server)
            output, error = shell.execute_command_raw('/opt/couchbase-sync-gateway/bin/sync_gateway -help')
            for index, str in enumerate(help_string):
                if index != help_string[index]:
                    self.log.info('configHelp found unmatched help text. error({0}), help({1})'.format(error[index], help_string[index]))
                self.assertEqual(error[index], help_string[index])
            shell.disconnect()

    def configCreateUser(self):
        for server in self.servers:
            shell = RemoteMachineShellConnection(server)
            self.config = 'gateway_config_walrus.json'
            self.assertTrue(self.start_sync_gateway(shell))
            self.assertTrue(self.create_user(shell))
            if not self.expected_stdout:
                self.assertTrue(self.get_user(shell))
                self.delete_user(shell)
            shell.disconnect()

    def configGuestUser(self):
        for server in self.servers:
            shell = RemoteMachineShellConnection(server)
            self.config = 'gateway_config_walrus.json'
            self.assertTrue(self.start_sync_gateway(shell))
            self.assertTrue(self.get_user(shell))
            self.assertFalse(self.delete_user(shell))
            shell.disconnect()

    def configCreateRole(self):
        for server in self.servers:
            shell = RemoteMachineShellConnection(server)
            self.config = 'gateway_config_walrus.json'
            self.assertTrue(self.start_sync_gateway(shell))
            self.assertTrue(self.create_role(shell, self.role_name, self.admin_channels))
            if not self.expected_stdout:
                self.assertTrue(self.get_role(shell))
                self.delete_role(shell)
            shell.disconnect()

    def configUserRolesChannels(self):
        for server in self.servers:
            shell = RemoteMachineShellConnection(server)
            self.config = 'gateway_config_walrus.json'
            self.assertTrue(self.start_sync_gateway(shell))
            self.assertTrue(self.parse_input_create_roles(shell))
            self.assertTrue(self.create_user(shell))
            if not self.expected_stdout:
                self.assertTrue(self.get_user(shell))
                self.delete_user(shell)
            shell.disconnect()

    def configUserRolesNotExist(self):
        for server in self.servers:
            shell = RemoteMachineShellConnection(server)
            self.config = 'gateway_config_walrus.json'
            self.assertTrue(self.start_sync_gateway(shell))
            self.assertTrue(self.create_user(shell))
            if not self.expected_stdout:
                self.assertTrue(self.get_user(shell))
                self.delete_user(shell)
            shell.disconnect()

    def configInspectDocChannel(self):
        for server in self.servers:
            shell = RemoteMachineShellConnection(server)
            self.config = 'gateway_config_walrus.json'
            self.assertTrue(self.start_sync_gateway(shell))
            self.assertTrue(self.parse_input_create_roles(shell))
            if self.doc_channels:
                success, revision = self.create_doc(shell)
                self.assertTrue(success)
                self.assertTrue(self.get_all_docs(shell))
                self.assertTrue(self.delete_doc(shell, revision))
            shell.disconnect()