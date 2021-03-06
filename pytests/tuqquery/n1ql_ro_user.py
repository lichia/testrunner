import math

from tuq import QueryTests


class ReadOnlyUserTests(QueryTests):
    def setUp(self):
        super(ReadOnlyUserTests, self).setUp()
        self.create_primary_index_for_3_0_and_greater()
        self.username = self.input.param('username', 'RON1ql')
        self.password = self.input.param('password', 'RO$Pass')
        cli_cmd = "user-manage"
        output, error = self.shell.execute_couchbase_cli(cli_command=cli_cmd,
                                                         options=' --set --ro-username=%s --ro-password=%s ' % (self.username, self.password),
                                                         cluster_host=self.master.ip,
                                                         user=self.master.rest_username,
                                                         password=self.master.rest_password)
        self.log.info(output)
        self.log.error(error)

    def suite_setUp(self):
        super(ReadOnlyUserTests, self).suite_setUp()

    def tearDown(self):
        super(ReadOnlyUserTests, self).tearDown()
        self._kill_all_processes_cbq()

    def suite_tearDown(self):
        super(ReadOnlyUserTests, self).suite_tearDown()

    def test_select(self):
        self._kill_all_processes_cbq()
        self._start_command_line_query(self.master, user=self.username, password=self.password)
        method_name = self.input.param('to_run', 'test_any')
        for bucket in self.buckets:
            getattr(self, method_name)()

    def test_select_indx(self):
        self._kill_all_processes_cbq()
        self._start_command_line_query(self.master, user=self.username, password=self.password)
        for bucket in self.buckets:
            index_name = "my_index"
            try:
                self.query = "CREATE INDEX %s ON %s(VMs) " % (index_name, bucket.name)
                self.run_cbq_query()
            finally:
                self.query = "DROP INDEX %s.%s" % (bucket.name, index_name)
                self.run_cbq_query()

    def test_readonly(self):
        self._kill_all_processes_cbq()
        self._start_command_line_query(self.master, user=self.username, password=self.password)
        for bucket in self.buckets:
            self.query = 'INSERT into %s key "%s" VALUES "%s"' % (bucket.name, 'key1', 'value')
            try:
                actual_result = self.run_cbq_query()
            except Exception, ex:
                self.assertTrue(str(ex).find('request is read-only') != -1, 'Server is not readonly')
                self.assertTrue(str(ex).find('10000') != -1, 'Error code is incorrect.')
                self.log.info('Read only is on')
            else:
                self.fail('server is not read-only')

    def _kill_all_processes_cbq(self):
        if hasattr(self, 'shell'):
           o = self.shell.execute_command("ps -aef| grep cbq-engine")
           if len(o):
               for cbq_engine in o[0]:
                   if cbq_engine.find('grep') == -1:
                       pid = [item for item in cbq_engine.split(' ') if item][1]
                       self.shell.execute_command("kill -9 %s" % pid)
