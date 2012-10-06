import unittest
import logger
import time
import threading
import os
import testconstants
import subprocess

# membase imports
from membase.api.rest_client import RestConnection, RestHelper
from membase.helper.bucket_helper import BucketOperationHelper
from membase.helper.cluster_helper import ClusterOperationHelper
from membase.helper.rebalance_helper import RebalanceHelper
from membase.performance.stats import StatsCollector
from remote.remote_util import RemoteMachineShellConnection
from perf_engines.cbsoda import StoreCouchbase

# testrunner imports
from TestInput import TestInputSingleton
from perf_defaults import PerfDefaults
from perf_engines import mcsoda
import testconstants


class PerfBase(unittest.TestCase):

    """
    specURL = http://hub.internal.couchbase.org/confluence/display/cbit/Black+Box+Performance+Test+Matrix

    """

    # The setUpBaseX() methods allow subclasses to resequence the setUp() and
    # skip cluster configuration.
    def setUpBase0(self):
        self.log = logger.Logger.get_logger()
        self.input = TestInputSingleton.input
        self.vbucket_count = PerfDefaults.vbuckets
        self.sc = None
        if self.parami("tear_down_on_setup",
                       PerfDefaults.tear_down_on_setup) == 1:
            self.tearDown()  # Tear down in case previous run had unclean death
        master = self.input.servers[0]
        self.set_up_rest(master)

    def setUpBase1(self):
        if self.parami('num_buckets', 1) > 1:
            bucket = 'bucket-0'
        else:
            bucket = self.param('bucket', 'default')
        vBuckets = self.rest.get_vbuckets(bucket)
        self.vbucket_count = len(vBuckets)

    def setUp(self):
        self.setUpBase0()

        mc_threads = self.parami("mc_threads", PerfDefaults.mc_threads)
        if mc_threads != PerfDefaults.mc_threads:
            for node in self.input.servers:
                self.set_mc_threads(node, mc_threads)

        master = self.input.servers[0]

        self.is_multi_node = False
        self.data_path = master.data_path

        # Number of items loaded by load() method.
        # Does not include or count any items that came from set_up_dgm().
        #
        self.num_items_loaded = 0

        if self.input.clusters:
            for cluster in self.input.clusters.values():
                master = cluster[0]
                self.set_up_rest(master)
                self.set_up_cluster(master)
        else:
            master = self.input.servers[0]
            self.set_up_cluster(master)

        # Rebalance
        num_nodes = self.parami("num_nodes", 10)
        self.rebalance_nodes(num_nodes)

        if self.input.clusters:
            for cluster in self.input.clusters.values():
                master = cluster[0]
                self.set_up_rest(master)
                self.set_up_buckets()
        else:
            self.set_up_buckets()

        self.set_up_proxy()

        if self.input.clusters:
            for cluster in self.input.clusters.values():
                master = cluster[0]
                self.set_up_rest(master)
                self.reconfigure()
        else:
            self.reconfigure()

        if self.parami("dgm", getattr(self, "dgm", 1)):
            self.set_up_dgm()

        time.sleep(10)
        self.setUpBase1()

        if self.input.clusters:
            for cluster in self.input.clusters.values():
                self.wait_until_warmed_up(cluster[0])
        else:
            self.wait_until_warmed_up()
        ClusterOperationHelper.flush_os_caches(self.input.servers)

    def set_up_rest(self, master):
        self.rest = RestConnection(master)
        self.rest_helper = RestHelper(self.rest)

    def set_up_cluster(self, master):
        """Initialize cluster"""

        print "[perf.setUp] Setting up cluster"

        self.rest.init_cluster(master.rest_username, master.rest_password)

        memory_quota = self.parami('mem_quota', PerfDefaults.mem_quota)
        self.rest.init_cluster_memoryQuota(master.rest_username,
                                           master.rest_password,
                                           memoryQuota=memory_quota)

    def _get_bucket_names(self, num_buckets):
        """
        Get a list of bucket names
        """
        if num_buckets > 1:
            buckets = ['bucket-{0}'.format(i) for i in range(num_buckets)]
        else:
            buckets = [self.param('bucket', 'default')]

        return buckets

    def get_bucket_conf(self):
        """ retrieve bucket configurations"""

        num_buckets = self.parami('num_buckets', 1)
        self.buckets = self._get_bucket_names(num_buckets)

    def set_up_buckets(self):
        """Set up data bucket(s)"""

        print "[perf.setUp] Setting up buckets"

        self.get_bucket_conf()

        for bucket in self.buckets:
            bucket_ram_quota = self.parami('mem_quota', PerfDefaults.mem_quota)
            bucket_ram_quota = bucket_ram_quota / self.parami('num_buckets', 1)
            replicas = self.parami('replicas', getattr(self, 'replicas', 1))

            self.rest.create_bucket(bucket=bucket, ramQuotaMB=bucket_ram_quota,
                                    replicaNumber=replicas, authType='sasl')

            status = self.rest_helper.vbucket_map_ready(bucket, 60)
            self.assertTrue(status, msg='vbucket_map not ready .. timed out')
            status = self.rest_helper.bucket_exists(bucket)
            self.assertTrue(status,
                            msg='unable to create {0} bucket'.format(bucket))

    def reconfigure(self):
        """Customize basic Couchbase setup"""

        print "[perf.setUp] Customizing setup"

        self.set_loglevel()
        self.set_max_concurrent_reps_per_doc()
        self.set_xdcr_doc_batch_size_kb()
        self.set_autocompaction()

    def set_loglevel(self):
        """Set custom loglevel"""

        loglevel = self.param('loglevel', None)
        if loglevel:
            self.rest.set_global_loglevel(loglevel)

    def set_mc_threads(self, node, mc_threads):
        """Change number of memcached threads"""
        rest = RestConnection(node)
        rest.set_mc_threads(mc_threads)
        print "[perf.setUp] num of memcached threads = %s" % mc_threads

    def set_xdcr_doc_batch_size_kb(self):
        """Set custom XDCR_DOC_BATCH_SIZE_KB"""

        xdcr_doc_batch_size_kb = self.param('xdcr_doc_batch_size_kb', None)
        if xdcr_doc_batch_size_kb:
            for server in self.input.servers:
                rc = RemoteMachineShellConnection(server)
                rc.set_environment_variable('XDCR_DOC_BATCH_SIZE_KB',
                                            xdcr_doc_batch_size_kb)

    def set_max_concurrent_reps_per_doc(self):
        """Set custom MAX_CONCURRENT_REPS_PER_DOC"""

        max_concurrent_reps_per_doc = self.param('max_concurrent_reps_per_doc',
                                                 None)
        if max_concurrent_reps_per_doc:
            for server in self.input.servers:
                rc = RemoteMachineShellConnection(server)
                rc.set_environment_variable('MAX_CONCURRENT_REPS_PER_DOC',
                                            max_concurrent_reps_per_doc)

    def set_ep_compaction(self, comp_ratio):
        """Set up ep_engine side compaction ratio"""
        for server in self.input.servers:
            shell = RemoteMachineShellConnection(server)
            cmd = "/opt/couchbase/bin/cbepctl localhost:11210 "\
                  "set flush_param db_frag_threshold {0}".format(comp_ratio)
            self._exec_and_log(shell, cmd)
            shell.disconnect()

    def set_autocompaction(self, disable_view_compaction=False):
        """Set custom auto-compaction settings"""

        try:
            # Parallel database and view compaction
            parallel_compaction = self.param("parallel_compaction",
                                             PerfDefaults.parallel_compaction)
            # Database fragmentation threshold
            db_compaction = self.parami("db_compaction",
                                        PerfDefaults.db_compaction)
            print "[perf.setUp] database compaction = %d" % db_compaction

            # ep_engine fragementation threshold
            ep_compaction = self.parami("ep_compaction",
                                        PerfDefaults.ep_compaction)
            self.set_ep_compaction(ep_compaction)
            print "[perf.setUp] ep_engine compaction = %d" % ep_compaction

            # View fragmentation threshold
            if disable_view_compaction:
                view_compaction = 100
            else:
                view_compaction = self.parami("view_compaction",
                                              PerfDefaults.view_compaction)
            # Set custom auto-compaction settings
            self.rest.set_auto_compaction(parallelDBAndVC=parallel_compaction,
                                          dbFragmentThresholdPercentage=db_compaction,
                                          viewFragmntThresholdPercentage=view_compaction)
        except Exception as e:
            # It's very hard to determine what exception it can raise.
            # Therefore we have to use general handler.
            print "ERROR while changing compaction settings: {0}".format(e)

    def tearDown(self):
        if self.parami("tear_down", 0) == 1:
            print "[perf.tearDown] tearDown routine skipped"
            return

        print "[perf.tearDown] tearDown routine starts"

        if self.parami("tear_down_proxy", 1) == 1:
            self.tear_down_proxy()
        else:
            print "[perf.tearDown] Proxy tearDown skipped"

        if self.sc is not None:
            self.sc.stop()
            self.sc = None

        if self.parami("tear_down_bucket", 0) == 1:
            self.tear_down_buckets()
        else:
            print "[perf.tearDown] Bucket tearDown skipped"

        if self.parami("tear_down_cluster", 1) == 1:
            self.tear_down_cluster()
        else:
            print "[perf.tearDown] Cluster tearDown skipped"

        print "[perf.tearDown] tearDown routine finished"

    def tear_down_buckets(self):
        print "[perf.tearDown] Tearing down bucket"
        BucketOperationHelper.delete_all_buckets_or_assert(self.input.servers,
                                                           self)
        print "[perf.tearDown] Bucket teared down"

    def tear_down_cluster(self):
        print "[perf.tearDown] Tearing down cluster"
        ClusterOperationHelper.cleanup_cluster(self.input.servers)
        ClusterOperationHelper.wait_for_ns_servers_or_assert(self.input.servers,
                                                             self)
        print "[perf.tearDown] Cluster teared down"

    def set_up_proxy(self, bucket=None):
        """Set up and start Moxi"""

        if self.input.moxis:
            print '[perf.setUp] Setting up proxy'

            bucket = bucket or self.param('bucket', 'default')

            shell = RemoteMachineShellConnection(self.input.moxis[0])
            shell.start_moxi(self.input.servers[0].ip, bucket,
                             self.input.moxis[0].port)
            shell.disconnect()

    def tear_down_proxy(self):
        if len(self.input.moxis) > 0:
            shell = RemoteMachineShellConnection(self.input.moxis[0])
            shell.stop_moxi()
            shell.disconnect()

    # Returns "host:port" of moxi to hit.
    def target_host_port(self, bucket='default', use_direct=False):
        rv = self.param('moxi', None)
        if use_direct:
            return "%s:%s" % (self.input.servers[0].ip,
                              '11210')
        if rv:
            return rv
        if len(self.input.moxis) > 0:
            return "%s:%s" % (self.input.moxis[0].ip,
                              self.input.moxis[0].port)
        return "%s:%s" % (self.input.servers[0].ip,
                          self.rest.get_bucket(bucket).nodes[0].moxi)

    def protocol_parse(self, protocol_in, use_direct=False):
        if protocol_in.find('://') >= 0:
            if protocol_in.find("couchbase:") >= 0:
                protocol = "couchbase"
            else:
                protocol = \
                    '-'.join(((["membase"] +
                    protocol_in.split("://"))[-2] + "-binary").split('-')[0:2])
            host_port = ('@' + protocol_in.split("://")[-1]).split('@')[-1]
            user, pswd = (('@' +
                           protocol_in.split("://")[-1]).split('@')[-2] +
                           ":").split(':')[0:2]
        else:
            protocol = 'memcached-' + protocol_in
            host_port = self.target_host_port(use_direct=use_direct)
            user = self.param("rest_username", "Administrator")
            pswd = self.param("rest_password", "password")
        return protocol, host_port, user, pswd

    def mk_protocol(self, host, port='8091', prefix='membase-binary'):
        return self.param('protocol',
                          prefix + '://' + host + ':' + port)

    def restartProxy(self, bucket=None):
        self.tear_down_proxy()
        self.set_up_proxy(bucket)

    def set_up_dgm(self):
        """Download fragmented, DGM dataset onto each cluster node, if not
        already locally available.

        The number of vbuckets and database schema must match the
        target cluster.

        Shutdown all cluster nodes.

        Do a cluster-restore.

        Restart all cluster nodes."""

        bucket = self.param("bucket", "default")
        ClusterOperationHelper.stop_cluster(self.input.servers)
        for server in self.input.servers:
            remote = RemoteMachineShellConnection(server)
            #TODO: Better way to pass num_nodes and db_size?
            self.get_data_files(remote, bucket, 1, 10)
            remote.disconnect()
        ClusterOperationHelper.start_cluster(self.input.servers)

    def get_data_files(self, remote, bucket, num_nodes, db_size):
        base = 'https://s3.amazonaws.com/database-analysis'
        dir = '/tmp/'
        if remote.is_couchbase_installed():
            dir = dir + '/couchbase/{0}-{1}-{2}/'.format(num_nodes, 256,
                                                         db_size)
            output, error = remote.execute_command('mkdir -p {0}'.format(dir))
            remote.log_command_output(output, error)
            file = '{0}_cb.tar.gz'.format(bucket)
            base_url = base + '/couchbase/{0}-{1}-{2}/{3}'.format(num_nodes,
                                                                  256, db_size,
                                                                  file)
        else:
            dir = dir + '/membase/{0}-{1}-{2}/'.format(num_nodes, 1024,
                                                       db_size)
            output, error = remote.execute_command('mkdir -p {0}'.format(dir))
            remote.log_command_output(output, error)
            file = '{0}_mb.tar.gz'.format(bucket)
            base_url = base + '/membase/{0}-{1}-{2}/{3}'.format(num_nodes,
                                                                1024, db_size,
                                                                file)


        info = remote.extract_remote_info()
        wget_command = 'wget'
        if info.type.lower() == 'windows':
            wget_command = \
                "cd {0} ;cmd /c 'c:\\automation\\wget.exe --no-check-certificate"\
                .format(dir)

        # Check if the file exists on the remote server else download the gzipped version
        # Extract if necessary
        exist = remote.file_exists(dir, file)
        if not exist:
            additional_quote = ""
            if info.type.lower() == 'windows':
                additional_quote = "'"
            command = "{0} -v -O {1}{2} {3} {4} ".format(wget_command, dir,
                                                         file, base_url,
                                                         additional_quote)
            output, error = remote.execute_command(command)
            remote.log_command_output(output, error)

        if remote.is_couchbase_installed():
            if info.type.lower() == 'windows':
                destination_folder = testconstants.WIN_COUCHBASE_DATA_PATH
            else:
                destination_folder = testconstants.COUCHBASE_DATA_PATH
        else:
            if info.type.lower() == 'windows':
                destination_folder = testconstants.WIN_MEMBASE_DATA_PATH
            else:
                destination_folder = testconstants.MEMBASE_DATA_PATH
        if self.data_path:
            destination_folder = self.data_path
        untar_command = 'cd {1}; tar -xzf {0}'.format(dir + file,
                                                      destination_folder)
        output, error = remote.execute_command(untar_command)
        remote.log_command_output(output, error)

    def _exec_and_log(self, shell, cmd):
        """helper method to execute a command and log output"""
        if not cmd or not shell:
            return

        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)

    def _build_tar_name(self, bucket, version="unknown_version",
                        file_base=None):
        """build tar file name.

        {file_base}-{version}-{bucket}.tar.gz
        """
        if not file_base:
            file_base = os.path.splitext(
                os.path.basename(self.param("conf_file",
                                 PerfDefaults.conf_file)))[0]
        return "{0}-{1}-{2}.tar.gz".format(file_base, version, bucket)

    def _save_snapshot(self, server, bucket, file_base=None):
        """Save data files to a snapshot"""

        src_data_path = os.path.dirname(server.data_path or
                                        testconstants.COUCHBASE_DATA_PATH)
        dest_data_path = "{0}-snapshots".format(src_data_path)

        print "[perf: _save_snapshot] server = {0} , src_data_path = {1}, dest_data_path = {2}"\
            .format(server.ip, src_data_path, dest_data_path)

        shell = RemoteMachineShellConnection(server)

        build_name, short_version, full_version = \
            shell.find_build_version("/opt/couchbase/", "VERSION.txt", "cb")

        dest_file = self._build_tar_name(bucket, full_version, file_base)

        self._exec_and_log(shell, "mkdir -p {0}".format(dest_data_path))

        # save as gzip file, if file exsits, overwrite
        # TODO: multiple buckets
        zip_cmd = "cd {0}; tar -cvzf {1}/{2} {3} {3}-data _*"\
            .format(src_data_path, dest_data_path, dest_file, bucket)
        self._exec_and_log(shell, zip_cmd)

        shell.disconnect()
        return True

    def _load_snapshot(self, server, bucket, file_base=None, overwrite=True):
        """Load data files from a snapshot"""

        dest_data_path = os.path.dirname(server.data_path or
                                         testconstants.COUCHBASE_DATA_PATH)
        src_data_path = "{0}-snapshots".format(dest_data_path)

        print "[perf: _load_snapshot] server = {0} , src_data_path = {1}, dest_data_path = {2}"\
            .format(server.ip, src_data_path, dest_data_path)

        shell = RemoteMachineShellConnection(server)

        build_name, short_version, full_version = \
            shell.find_build_version("/opt/couchbase/", "VERSION.txt", "cb")

        src_file = self._build_tar_name(bucket, full_version, file_base)

        if not shell.file_exists(src_data_path, src_file):
            print "[perf: _load_snapshot] file '{0}/{1}' does not exist"\
                .format(src_data_path, src_file)
            shell.disconnect()
            return False

        if not overwrite:
            self._save_snapshot(server, bucket,
                                "{0}.tar.gz".format(
                                    time.strftime(PerfDefaults.strftime)))  # TODO: filename

        rm_cmd = "rm -rf {0}/{1} {0}/{1}-data {0}/_*".format(dest_data_path,
                                                             bucket)
        self._exec_and_log(shell, rm_cmd)

        unzip_cmd = "cd {0}; tar -xvzf {1}/{2}".format(dest_data_path,
                                                       src_data_path, src_file)
        self._exec_and_log(shell, unzip_cmd)

        shell.disconnect()
        return True

    def save_snapshots(self, file_base, bucket):
        """Save snapshots on all servers"""
        if not self.input.servers or not bucket:
            print "[perf: save_snapshot] invalid server list or bucket name"
            return False

        ClusterOperationHelper.stop_cluster(self.input.servers)

        for server in self.input.servers:
            self._save_snapshot(server, bucket, file_base)

        ClusterOperationHelper.start_cluster(self.input.servers)

        return True

    def load_snapshots(self, file_base, bucket):
        """Load snapshots on all servers"""
        if not self.input.servers or not bucket:
            print "[perf: load_snapshot] invalid server list or bucket name"
            return False

        ClusterOperationHelper.stop_cluster(self.input.servers)

        for server in self.input.servers:
            if not self._load_snapshot(server, bucket, file_base):
                ClusterOperationHelper.start_cluster(self.input.servers)
                return False

        ClusterOperationHelper.start_cluster(self.input.servers)

        return True

    def spec(self, reference):
        self.spec_reference = self.param("spec", reference)
        self.log.info("spec: " + reference)

    def mk_stats(self, verbosity):
        return StatsCollector(verbosity)

    def _get_src_version(self):
        """get testrunner version"""
        try:
            result = subprocess.Popen(['git', 'rev-parse', 'HEAD'],
                                      stdout=subprocess.PIPE).communicate()[0]
        except subprocess.CalledProcessError as e:
            print "[perf] unable to get src code version : {0}".format(str(e))
            return "unknown version"
        return result.rstrip()[:7]

    def start_stats(self, stats_spec, servers=None,
                    process_names=['memcached', 'beam.smp', 'couchjs'],
                    test_params=None, client_id='',
                    collect_server_stats=True, ddoc=None):
        if self.parami('stats', 1) == 0:
            return None

        servers = servers or self.input.servers
        sc = self.mk_stats(False)
        bucket = self.param("bucket", "default")
        sc.start(servers, bucket, process_names, stats_spec, 10, client_id,
                 collect_server_stats=collect_server_stats, ddoc=ddoc)
        test_params['testrunner'] = self._get_src_version()
        self.test_params = test_params
        self.sc = sc
        return self.sc

    def end_stats(self, sc, total_stats=None, stats_spec=None):
        if sc is None:
            return
        if stats_spec is None:
            stats_spec = self.spec_reference
        if total_stats:
            sc.total_stats(total_stats)
        self.log.info("stopping stats collector")
        sc.stop()
        self.log.info("stats collector is stopped")
        sc.export(stats_spec, self.test_params)

    def load(self, num_items, min_value_size=None,
             kind='binary',
             protocol='binary',
             ratio_sets=1.0,
             ratio_hot_sets=0.0,
             ratio_hot_gets=0.0,
             ratio_expirations=0.0,
             expiration=None,
             prefix="",
             doc_cache=1,
             use_direct=True,
             report=0,
             start_at= -1,
             collect_server_stats=True,
             is_eperf=False,
             hot_shift=0):
        cfg = {'max-items': num_items,
               'max-creates': num_items,
               'max-ops-per-sec': self.parami("load_mcsoda_max_ops_sec",
                                              PerfDefaults.mcsoda_max_ops_sec),
               'min-value-size': min_value_size or self.parami("min_value_size",
                                                               1024),
               'ratio-sets': self.paramf("load_ratio_sets", ratio_sets),
               'ratio-misses': self.paramf("load_ratio_misses", 0.0),
               'ratio-creates': self.paramf("load_ratio_creates", 1.0),
               'ratio-deletes': self.paramf("load_ratio_deletes", 0.0),
               'ratio-hot': 0.0,
               'ratio-hot-sets': ratio_hot_sets,
               'ratio-hot-gets': ratio_hot_gets,
               'ratio-expirations': ratio_expirations,
               'expiration': expiration or 0,
               'exit-after-creates': 1,
               'json': int(kind == 'json'),
               'batch': self.parami("batch", PerfDefaults.batch),
               'vbuckets': self.vbucket_count,
               'doc-cache': doc_cache,
               'prefix': prefix,
               'report': report,
               'hot-shift': hot_shift,
               'cluster_name': self.param("cluster_name", "")}
        cur = {}
        if start_at >= 0:
            cur['cur-items'] = start_at
            cur['cur-gets'] = start_at
            cur['cur-sets'] = start_at
            cur['cur-ops'] = cur['cur-gets'] + cur['cur-sets']
            cur['cur-creates'] = start_at
            cfg['max-creates'] = start_at + num_items
            cfg['max-items'] = cfg['max-creates']

        cfg_params = cfg.copy()
        cfg_params['test_time'] = time.time()
        cfg_params['test_name'] = self.id()

        # phase: 'load' or 'reload'
        phase = "load"
        if self.parami("hot_load_phase", 0) == 1:
            phase = "reload"

        if is_eperf:
            collect_server_stats = self.parami("prefix", 0) == 0
            client_id = self.parami("prefix", 0)
            sc = self.start_stats("{0}.{1}".format(self.spec_reference, phase), # stats spec e.x: testname.load
                                  test_params=cfg_params, client_id=client_id,
                                  collect_server_stats=collect_server_stats)

        # For Black box, multi node tests
        # always use membase-binary
        if self.is_multi_node:
            protocol = self.mk_protocol(host=self.input.servers[0].ip,
                                        port=self.input.servers[0].port)

        protocol, host_port, user, pswd = \
            self.protocol_parse(protocol, use_direct=use_direct)

        if not user.strip():
            if "11211" in host_port:
                user = self.param("bucket", "default")
            else:
                user = self.input.servers[0].rest_username
        if not pswd.strip():
            if not "11211" in host_port:
                pswd = self.input.servers[0].rest_password

        self.log.info("mcsoda - %s %s %s %s" %
                      (protocol, host_port, user, pswd))
        self.log.info("mcsoda - cfg: " + str(cfg))
        self.log.info("mcsoda - cur: " + str(cur))

        cur, start_time, end_time = \
            self.mcsoda_run(cfg, cur, protocol, host_port, user, pswd,
                            heartbeat=self.parami("mcsoda_heartbeat", 0),
                            why="load", bucket=self.param("bucket", "default"))
        self.num_items_loaded = num_items
        ops = {'tot-sets': cur.get('cur-sets', 0),
               'tot-gets': cur.get('cur-gets', 0),
               'tot-items': cur.get('cur-items', 0),
               'tot-creates': cur.get('cur-creates', 0),
               'tot-misses': cur.get('cur-misses', 0),
               "start-time": start_time,
               "end-time": end_time}

        if is_eperf:
            if self.parami("load_wait_until_drained", 1) == 1:
                self.wait_until_drained()
            if self.parami("load_wait_until_repl",
                PerfDefaults.load_wait_until_repl) == 1:
                self.wait_until_repl()
            self.end_stats(sc, ops, "{0}.{1}".format(self.spec_reference,
                                                     phase))

        return ops, start_time, end_time

    def mcsoda_run(self, cfg, cur, protocol, host_port, user, pswd,
                   stats_collector=None, stores=None, ctl=None,
                   heartbeat=0, why="", bucket="default"):
        return mcsoda.run(cfg, cur, protocol, host_port, user, pswd,
                          stats_collector=stats_collector,
                          stores=stores,
                          ctl=ctl,
                          heartbeat=heartbeat,
                          why=why,
                          bucket=bucket)

    def rebalance_nodes(self, num_nodes):
        """Rebalance cluster(s) if more than 1 node provided"""

        if len(self.input.servers) == 1 or num_nodes == 1:
            print "WARNING: running on single node cluster"
            return
        else:
            print "[perf.setUp] rebalancing nodes: num_nodes = {0}".\
                format(num_nodes)

        if self.input.clusters:
            for cluster in self.input.clusters.values():
                status, _ = RebalanceHelper.rebalance_in(cluster,
                                                         num_nodes - 1,
                                                         do_shuffle=False)
                self.assertTrue(status)
        else:
            status, _ = RebalanceHelper.rebalance_in(self.input.servers,
                                                     num_nodes - 1,
                                                     do_shuffle=False)
            self.assertTrue(status)

    @staticmethod
    def delayed_rebalance_worker(servers, num_nodes, delay_seconds, sc,
                                 max_retries=PerfDefaults.reb_max_retries):
        time.sleep(delay_seconds)
        gmt_now = time.strftime(PerfDefaults.strftime, time.gmtime())
        print "[delayed_rebalance_worker] rebalance started: %s" % gmt_now

        if not sc:
            print "[delayed_rebalance_worker] invalid stats collector"
            return
        status = False
        retries = 0
        while not status and retries <= max_retries:
            start_time = time.time()
            status, nodes = RebalanceHelper.rebalance_in(servers,
                                                         num_nodes - 1,
                                                         do_check=(not retries))
            end_time = time.time()
            print "[delayed_rebalance_worker] status: {0}, nodes: {1}, retries: {2}"\
                .format(status, nodes, retries)
            if not status:
                retries += 1
                time.sleep(delay_seconds)
        sc.reb_stats(start_time, end_time - start_time)

    def delayed_rebalance(self, num_nodes, delay_seconds=10,
                          max_retries=PerfDefaults.reb_max_retries,
                          sync=False):
        print "delayed_rebalance"
        if sync:
            PerfBase.delayed_rebalance_worker(self.input.servers,
                    num_nodes, delay_seconds, self.sc, max_retries)
        else:
            t = threading.Thread(target=PerfBase.delayed_rebalance_worker,
                                 args=(self.input.servers, num_nodes,
                                 delay_seconds, self.sc, max_retries))
            t.daemon = True
            t.start()

    @staticmethod
    def set_auto_compaction(server, parallel_compaction, percent_threshold):
        rest = RestConnection(server)
        rest.set_auto_compaction(parallel_compaction,
                                 dbFragmentThresholdPercentage=percent_threshold,
                                 viewFragmntThresholdPercentage=percent_threshold)

    @staticmethod
    def delayed_compaction_worker(servers, parallel_compaction,
                                  percent_threshold, delay_seconds):
        time.sleep(delay_seconds)
        PerfBase.set_auto_compaction(servers[0], parallel_compaction,
                                     percent_threshold)

    def delayed_compaction(self, parallel_compaction="false",
                           percent_threshold=0.01,
                           delay_seconds=10):
        t = threading.Thread(target=PerfBase.delayed_compaction_worker,
                             args=(self.input.servers,
                                   parallel_compaction,
                                   percent_threshold,
                                   delay_seconds))
        t.daemon = True
        t.start()

    def loop(self, num_ops=None,
             num_items=None,
             max_items=None,
             max_creates=None,
             min_value_size=None,
             exit_after_creates=0,
             kind='binary',
             protocol='binary',
             clients=1,
             ratio_misses=0.0,
             ratio_sets=0.0, ratio_creates=0.0, ratio_deletes=0.0,
             ratio_hot=0.2, ratio_hot_sets=0.95, ratio_hot_gets=0.95,
             ratio_expirations=0.0,
             expiration=None,
             test_name=None,
             prefix="",
             doc_cache=1,
             use_direct=True,
             collect_server_stats=True,
             start_at= -1,
             report=0,
             ctl=None,
             hot_shift=0,
             is_eperf=False,
             ratio_queries=0,
             queries=0,
             ddoc=None):
        num_items = num_items or self.num_items_loaded

        hot_stack_size = \
            self.parami('hot_stack_size', PerfDefaults.hot_stack_size) or \
            (num_items * ratio_hot)

        cfg = {'max-items': max_items or num_items,
               'max-creates': max_creates or 0,
               'max-ops-per-sec': self.parami("mcsoda_max_ops_sec",
                                              PerfDefaults.mcsoda_max_ops_sec),
               'min-value-size': min_value_size or self.parami("min_value_size",
                                                               1024),
               'exit-after-creates': exit_after_creates,
               'ratio-sets': ratio_sets,
               'ratio-misses': ratio_misses,
               'ratio-creates': ratio_creates,
               'ratio-deletes': ratio_deletes,
               'ratio-hot': ratio_hot,
               'ratio-hot-sets': ratio_hot_sets,
               'ratio-hot-gets': ratio_hot_gets,
               'ratio-expirations': ratio_expirations,
               'ratio-queries': ratio_queries,
               'expiration': expiration or 0,
               'threads': clients,
               'json': int(kind == 'json'),
               'batch': self.parami("batch", PerfDefaults.batch),
               'vbuckets': self.vbucket_count,
               'doc-cache': doc_cache,
               'prefix': prefix,
               'queries': queries,
               'report': report,
               'hot-shift': hot_shift,
               'hot-stack': self.parami("hot_stack", PerfDefaults.hot_stack),
               'hot-stack-size': hot_stack_size,
               'hot-stack-rotate': self.parami("hot_stack_rotate",
                                               PerfDefaults.hot_stack_rotate),
               'cluster_name': self.param("cluster_name", ""),
               'observe': self.param("observe", PerfDefaults.observe),
               'obs-backoff': self.paramf('obs_backoff',
                                          PerfDefaults.obs_backoff),
               'obs-max-backoff': self.paramf('obs_max_backoff',
                                              PerfDefaults.obs_max_backoff),
               'obs-persist-count': self.parami('obs_persist_count',
                                                PerfDefaults.obs_persist_count),
               'obs-repl-count': self.parami('obs_repl_count',
                                             PerfDefaults.obs_repl_count),
               'woq-pattern': self.parami('woq_pattern',
                                         PerfDefaults.woq_pattern),
               'woq-verbose': self.parami('woq_verbose',
                                         PerfDefaults.woq_verbose),
               'cor-pattern': self.parami('cor_pattern',
                                         PerfDefaults.cor_pattern),
               'cor-persist': self.parami('cor_persist',
                                         PerfDefaults.cor_persist),
               'carbon': self.parami('carbon', PerfDefaults.carbon),
               'carbon-server': self.param('carbon_server',
                                           PerfDefaults.carbon_server),
               'carbon-port': self.parami('carbon_port',
                                          PerfDefaults.carbon_port),
               'carbon-timeout': self.parami('carbon_timeout',
                                             PerfDefaults.carbon_timeout),
               'carbon-cache-size': self.parami('carbon_cache_size',
                                                PerfDefaults.carbon_cache_size),
               'time': self.parami('time', 0)}

        cfg_params = cfg.copy()
        cfg_params['test_time'] = time.time()
        cfg_params['test_name'] = test_name
        client_id = ''
        stores = None

        if is_eperf:
            client_id = self.parami("prefix", 0)
        sc = None
        if self.parami("collect_stats", 1):
            sc = self.start_stats(self.spec_reference + ".loop",
                                  test_params=cfg_params, client_id=client_id,
                                  collect_server_stats=collect_server_stats,
                                  ddoc=ddoc)

        self.cur = {'cur-items': num_items}
        if start_at >= 0:
            self.cur['cur-gets'] = start_at
        if num_ops is None:
            num_ops = num_items
        if isinstance(num_ops, int):
            cfg['max-ops'] = num_ops
        else:
            # Here, we num_ops looks like "time to run" tuple of...
            # ('seconds', integer_num_of_seconds_to_run)
            cfg['time'] = num_ops[1]

        # For Black box, multi node tests
        # always use membase-binary
        if self.is_multi_node:
            protocol = self.mk_protocol(host=self.input.servers[0].ip,
                                        port=self.input.servers[0].port)

        self.log.info("mcsoda - protocol %s" % protocol)
        protocol, host_port, user, pswd = \
            self.protocol_parse(protocol, use_direct=use_direct)

        if not user.strip():
            if "11211" in host_port:
                user = self.param("bucket", "default")
            else:
                user = self.input.servers[0].rest_username
        if not pswd.strip():
            if not "11211" in host_port:
                pswd = self.input.servers[0].rest_password

        self.log.info("mcsoda - %s %s %s %s" %
                      (protocol, host_port, user, pswd))
        self.log.info("mcsoda - cfg: " + str(cfg))
        self.log.info("mcsoda - cur: " + str(self.cur))

        # For query tests always use StoreCouchbase
        if protocol == "couchbase":
            stores = [StoreCouchbase()]

        self.cur, start_time, end_time = \
            self.mcsoda_run(cfg, self.cur, protocol, host_port, user, pswd,
                            stats_collector=sc, ctl=ctl, stores=stores,
                            heartbeat=self.parami("mcsoda_heartbeat", 0),
                            why="loop", bucket=self.param("bucket", "default"))

        ops = {'tot-sets': self.cur.get('cur-sets', 0),
               'tot-gets': self.cur.get('cur-gets', 0),
               'tot-items': self.cur.get('cur-items', 0),
               'tot-creates': self.cur.get('cur-creates', 0),
               'tot-misses': self.cur.get('cur-misses', 0),
               "start-time": start_time,
               "end-time": end_time}

        # Wait until there are no active indexing tasks
        if self.parami('wait_for_indexer', 0):
            ClusterOperationHelper.wait_for_completion(self.rest, 'indexer')

        # Wait until there are no active view compaction tasks
        if self.parami('wait_for_compaction', 0):
            ClusterOperationHelper.wait_for_completion(self.rest,
                                                       'view_compaction')

        if self.parami("loop_wait_until_drained",
                       PerfDefaults.loop_wait_until_drained):
            self.wait_until_drained()

        if self.parami("loop_wait_until_repl",
                       PerfDefaults.loop_wait_until_repl):
            self.wait_until_repl()

        if self.parami("collect_stats", 1) and \
                not self.parami("reb_no_fg", PerfDefaults.reb_no_fg):
            self.end_stats(sc, ops, self.spec_reference + ".loop")

        return ops, start_time, end_time

    def wait_until_drained(self):
        print "[perf.drain] draining disk write queue : %s"\
            % time.strftime(PerfDefaults.strftime)

        master = self.input.servers[0]
        bucket = self.param("bucket", "default")

        RebalanceHelper.wait_for_stats_on_all(master, bucket,
                                              'ep_queue_size', 0,
                                              fn=RebalanceHelper.wait_for_stats_no_timeout)
        RebalanceHelper.wait_for_stats_on_all(master, bucket,
                                              'ep_flusher_todo', 0,
                                              fn=RebalanceHelper.wait_for_stats_no_timeout)

        print "[perf.drain] disk write queue has been drained: %s"\
            % time.strftime(PerfDefaults.strftime)

        return time.time()

    def wait_until_repl(self):
        print "[perf.repl] waiting for replication: %s"\
            % time.strftime(PerfDefaults.strftime)

        master = self.input.servers[0]
        bucket = self.param("bucket", "default")

        RebalanceHelper.wait_for_stats_on_all(master, bucket,
            'vb_replica_queue_size', 0,
            fn=RebalanceHelper.wait_for_stats_no_timeout)

        RebalanceHelper.wait_for_stats_on_all(master, bucket,
            'ep_tap_replica_queue_itemondisk', 0,
            fn=RebalanceHelper.wait_for_stats_no_timeout)

        RebalanceHelper.wait_for_stats_on_all(master, bucket,
            'ep_tap_rebalance_queue_backfillremaining', 0,
            fn=RebalanceHelper.wait_for_stats_no_timeout)

        RebalanceHelper.wait_for_stats_on_all(master, bucket,
            'ep_tap_replica_qlen', 0,
            fn=RebalanceHelper.wait_for_stats_no_timeout)

        print "[perf.repl] replication is done: %s"\
            % time.strftime(PerfDefaults.strftime)

    def warmup(self, collect_stats=True, flush_os_cache=False):
        """
        Restart cluster and wait for it to warm up.
        In current version, affect the master node only.
        """
        if not self.input.servers:
            print "[warmup error] empty server list"
            return

        if collect_stats:
            client_id = self.parami("prefix", 0)
            test_params = {'test_time': time.time(),
                           'test_name': self.id(),
                           'json': 0}
            sc = self.start_stats(self.spec_reference + ".warmup",
                                  test_params=test_params,
                                  client_id=client_id)

        print "[warmup] preparing to warmup cluster ..."

        server = self.input.servers[0]
        shell = RemoteMachineShellConnection(server)

        start_time = time.time()

        print "[warmup] stopping couchbase ... ({0}, {1})"\
            .format(server.ip, time.strftime(PerfDefaults.strftime))
        shell.stop_couchbase()
        print "[warmup] couchbase stopped ({0}, {1})"\
            .format(server.ip, time.strftime(PerfDefaults.strftime))

        if flush_os_cache:
            print "[warmup] flushing os cache ..."
            shell.flush_os_caches()

        shell.start_couchbase()
        print "[warmup] couchbase restarted ({0}, {1})"\
            .format(server.ip, time.strftime(PerfDefaults.strftime))

        self.wait_until_warmed_up()
        print "[warmup] warmup finished"

        end_time = time.time()
        ops = {'tot-sets': 0,
               'tot-gets': 0,
               'tot-items': 0,
               'tot-creates': 0,
               'tot-misses': 0,
               "start-time": start_time,
               "end-time": end_time}

        if collect_stats:
            self.end_stats(sc, ops, self.spec_reference + ".warmup")

    def wait_until_warmed_up(self, master=None):
        if not master:
            master = self.input.servers[0]

        bucket = self.param("bucket", "default")

        fn = RebalanceHelper.wait_for_mc_stats_no_timeout
        for bucket in self.buckets:
            RebalanceHelper.wait_for_stats_on_all(master, bucket,
                                                  'ep_warmup_thread',
                                                  'complete', fn=fn)
    def set_param(self, name, val):

        input = getattr(self, "input", TestInputSingleton.input)
        input.test_params[name] = str(val)

        return True

    def param(self, name, default_value):
        input = getattr(self, "input", TestInputSingleton.input)
        return input.test_params.get(name, default_value)

    def parami(self, name, default_int):
        return int(self.param(name, default_int))

    def paramf(self, name, default_float):
        return float(self.param(name, default_float))

    def params(self, name, default_str):
        return str(self.param(name, default_str))
