from basetestcase import BaseTestCase
import json
import os
import zipfile
import pprint
from membase.helper.cluster_helper import ClusterOperationHelper
import mc_bin_client
from memcached.helper.data_helper import  VBucketAwareMemcached
from mysql_client import MySQLClient
from membase.api.rest_client import RestConnection, Bucket
from couchbase_helper.tuq_helper import N1QLHelper
from couchbase_helper.query_helper import QueryHelper

class RQGTests(BaseTestCase):
    """ Class for defining tests for RQG base testing """

    def setUp(self):
        super(RQGTests, self).setUp()
        self.log.info("==============  RQGTests setup was finished for test #{0} {1} =============="\
                      .format(self.case_number, self._testMethodName))
        self.initial_loading_to_cb= self.input.param("initial_loading_to_cb",True)
        self.database= self.input.param("database","flightstats")
        self.user_id= self.input.param("user_id","root")
        self.password= self.input.param("password","")
        self.mysql_url= self.input.param("mysql_url","localhost")
        self.gen_secondary_indexes= self.input.param("gen_secondary_indexes",False)
        self.gen_gsi_indexes= self.input.param("gen_gsi_indexes",True)
        self.n1ql_server = self.get_nodes_from_services_map(service_type = "n1ql")
        self.query_helper = QueryHelper()
        self._initialize_n1ql_helper()
        if self.initial_loading_to_cb:
            self._initialize_cluster_setup()

    def tearDown(self):
        super(RQGTests, self).tearDown()

    def test_rqg_example(self):
        self._initialize_mysql_client()
        sql_query = "SELECT a1.* FROM ( `ontime_mysiam`  AS a1 INNER JOIN `carriers`  AS a2 ON ( a1.`carrier` = a2.`code` ) )"
        n1ql_query = "SELECT a1.* FROM `ontime_mysiam`  AS a1 INNER JOIN `carriers`  AS a2 ON KEYS [ a1.`carrier` ]"
        # Run n1ql query
        check, msg = self._run_queries_compare(n1ql_query = n1ql_query , sql_query = sql_query)
        self.assertTrue(check, msg)

    def test_rqg_from_list(self):
        self._initialize_mysql_client()
        self.n1ql_file_path= self.input.param("n1ql_file_path","default")
        self.sql_file_path= self.input.param("sql_file_path","default")
        with open(self.n1ql_file_path) as f:
            n1ql_query_list = f.readlines()
        with open(self.sql_file_path) as f:
            sql_query_list = f.readlines()
        self._generate_secondary_indexes(n1ql_query_list)
        i = 0
        check = True
        pass_case = 0
        total =0
        fail_case = 0
        failure_map = {}
        self.assertTrue(len(n1ql_query_list) == len(sql_query_list),
         "number of query mismatch n1ql:{0}, sql:{1}".format(len(n1ql_query_list),len(sql_query_list)))
        for n1ql_query in n1ql_query_list:
            self.log.info(" <<<<<<<<<<<<<<<<<<<<<<<<<<<< BEGIN RUNNING QUERY CASE NUMBER {0} >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>".format(i))
            sql_query = sql_query_list[i]
            i+=1
            # Run n1ql query
            success, msg = self._run_queries_compare(n1ql_query = n1ql_query , sql_query = sql_query)
            total += 1
            check = check and success
            if success:
                pass_case += 1
            else:
                fail_case +=  1
                failure_map["Case :: "+str(i-1)] = { "sql_query":sql_query, "n1ql_query": n1ql_query, "reason for failure": msg}
            self.log.info(" <<<<<<<<<<<<<<<<<<<<<<<<<<<< END RUNNING QUERY CASE NUMBER {0} >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>".format(i-1))
        self.log.info(" Total Queries Run = {0}, Pass = {1}, Fail = {2}".format(total, pass_case, fail_case))
        self.assertTrue(check, failure_map)

    def test_rqg_with_gsi(self):
        self.run_queries= self.input.param("run_queries",True)
        self.run_explain_with_hints= self.input.param("run_explain_with_hints",True)
        self.n1ql_file_path= self.input.param("test_file_path","default")
        with open(self.n1ql_file_path) as f:
            n1ql_query_list = f.readlines()
        i = 0
        check = True
        pass_case = 0
        total =0
        fail_case = 0
        failure_map = {}
        for n1ql_query_info in n1ql_query_list:
            # Run n1ql query
            data = json.loads(n1ql_query_info)
            n1ql_query = data["n1ql"]
            sql_query = data["sql"]
            gsi_indexes = data["gsi_indexes"]
            table_name = data["bucket"]
            hints = self.query_helper._find_hints(n1ql_query)
            self._generate_secondary_indexes_with_index_map(index_map = gsi_indexes, table_name = table_name)
            self.log.info(" <<<<<<<<<<<<<<<<<<<<<<<<<<<< BEGIN RUNNING TEST {0}  >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>".format(total))
            success_query_run = True
            msg_for_query_run = ""
            success_explain_run = "NA"
            success_query_run = "NA"
            if self.run_queries:
                success_query_run, msg_for_query_run = self._run_queries_compare(n1ql_query = n1ql_query , sql_query = sql_query)
            success_explain_run = True
            msg_for_explain_run = []
            if self.run_explain_with_hints:
                success_explain_run, msg_for_explain_run = self._run_queries_with_explain(n1ql_query , gsi_indexes.keys())
            total += 1
            check = check and success_query_run
            check = check and success_explain_run
            if not success_query_run:
                self._run_explain_and_print_result(n1ql_query)
            if check:
                pass_case += 1
            else:
                fail_case +=  1
                failure_map[str(total)] = {"sql_query":sql_query, "n1ql_query": n1ql_query,
                 "query run result": msg_for_query_run,
                 "explain result": str(msg_for_explain_run)}
            self._drop_secondary_indexes_with_index_map(index_map = gsi_indexes, table_name = table_name)
            self.log.info(" <<<<<<<<<<<<<<<<<<<<<<<<<<<< END RUNNING QUERY CASE NUMBER {0} >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>".format(total))
        self.log.info(" Total Queries Run = {0}, Pass = {1}, Fail = {2}".format(total, pass_case, fail_case))
        result = self._generate_result(failure_map)
        self.assertTrue(check, result)

    def test_rqg_from_file(self):
        self.n1ql_file_path= self.input.param("n1ql_file_path","default")
        with open(self.n1ql_file_path) as f:
            n1ql_query_list = f.readlines()
        self._generate_secondary_indexes(n1ql_query_list)
        i = 0
        check = True
        pass_case = 0
        total =0
        fail_case = 0
        failure_map = {}
        for n1ql_query_info in n1ql_query_list:
            # Run n1ql query
            data = json.loads(n1ql_query_info)
            case_number = data["test case number"]
            n1ql_query = data["n1ql_query"]
            sql_query = data["sql_query"]
            expected_result = data["expected_result"]
            hints = self.query_helper._find_hints(n1ql_query)
            self.log.info(" <<<<<<<<<<<<<<<<<<<<<<<<<<<< BEGIN RUNNING QUERY  >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>".format(case_number))

            success, msg = self._run_queries_from_file_and_compare(n1ql_query = n1ql_query , sql_query = sql_query, sql_result = expected_result)
            total += 1
            check = check and success
            if success:
                pass_case += 1
            else:
                fail_case +=  1
                failure_map[case_number] = { "sql_query":sql_query, "n1ql_query": n1ql_query, "reason for failure": msg}
            self.log.info(" <<<<<<<<<<<<<<<<<<<<<<<<<<<< END RUNNING QUERY CASE NUMBER {0} >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>".format(case_number))
        self.log.info(" Total Queries Run = {0}, Pass = {1}, Fail = {2}".format(total, pass_case, fail_case))
        self.assertTrue(check, failure_map)

    def test_n1ql_queries_only(self):
        self.n1ql_file_path= self.input.param("n1ql_file_path","default")
        with open(self.n1ql_file_path) as f:
            n1ql_query_list = f.readlines()
        self._generate_secondary_indexes(n1ql_query_list)
        failure_list = []
        n1ql_query_list = self.query_helper._convert_sql_list_to_n1ql(n1ql_query_list)
        check = True
        for n1ql_query in n1ql_query_list:
            try:
                self._run_n1ql_queries(n1ql_query = n1ql_query)
            except Exception, ex:
                self.log.info(ex)
                check = False
                failure_list.append({"n1ql_query":n1ql_query, "reason":ex})
        self.assertTrue(check, failure_list)

    def test_bootstrap_with_data(self):
        self.log.info(" Data has been bootstrapped !!")
        self.skip_cleanup=True

    def test_take_mysql_query_response_snap_shot(self):
        self._initialize_mysql_client()
        self.file_prefix= self.input.param("file_prefix","default_rqg_test")
        self.data_dump_path= self.input.param("data_dump_path","/tmp")
        self.queries_per_dump_file= self.input.param("queries_per_dump_file",10000)
        self.n1ql_file_path= self.input.param("n1ql_file_path","default")
        self.sql_file_path= self.input.param("sql_file_path","default")
        with open(self.n1ql_file_path) as f:
            n1ql_query_list = f.readlines()
        with open(self.sql_file_path) as f:
            sql_query_list = f.readlines()
        self._generate_secondary_indexes(n1ql_query_list)
        i = 0
        queries =0
        file_number=0
        f = open(self.data_dump_path+"/"+self.file_prefix+"_"+str(file_number)+".txt","w")
        for n1ql_query in n1ql_query_list:
            n1ql_query = n1ql_query.replace("\n","")
            sql_query = sql_query_list[i].replace("\n","")
            hints = self.query_helper._find_hints(n1ql_query)
            columns, rows = self.client._execute_query(query = sql_query)
            sql_result = self.client._gen_json_from_results(columns, rows)
            if hints == "FUN":
                sql_result = self._convert_fun_result(sql_result)
            dump_data = {
              "test case number":(i+1),
              "n1ql_query":n1ql_query,
              "sql_query":sql_query,
              "expected_result":sql_result
               }
            i+=1
            queries += 1
            f.write(json.dumps(dump_data)+"\n")
            if queries > self.queries_per_dump_file:
                queries = 0
                file_number = 1
                f.close()
                f = open(self.data_dump_path+"/"+self.file_prefix+"_"+file_number+".txt","w")
        f.close()

    def test_take_snapshot_of_database(self):
        self._take_snapshot_of_database()

    def test_load_data_of_database(self):
        self._setup_and_load_buckets_from_files()

    def _run_n1ql_queries(self, n1ql_query = None):
        # Run n1ql query
        actual_result = self.n1ql_helper.run_cbq_query(query = n1ql_query, server = self.n1ql_server)

    def _run_queries_compare(self, n1ql_query = None, sql_query = None):
        self.log.info(" SQL QUERY :: {0}".format(sql_query))
        self.log.info(" N1QL QUERY :: {0}".format(n1ql_query))
        # Run n1ql query
        hints = self.query_helper._find_hints(n1ql_query)
        try:
            actual_result = self.n1ql_helper.run_cbq_query(query = n1ql_query, server = self.n1ql_server)
            n1ql_result = actual_result["results"]
            #self.log.info(actual_result)
            # Run SQL Query
            columns, rows = self.client._execute_query(query = sql_query)
            sql_result = self.client._gen_json_from_results(columns, rows)
            #self.log.info(sql_result)
            self.log.info(" result from n1ql query returns {0} items".format(len(n1ql_result)))
            self.log.info(" result from sql query returns {0} items".format(len(sql_result)))
            try:
                self.n1ql_helper._verify_results_rqg(sql_result = sql_result, n1ql_result = n1ql_result, hints = hints)
            except Exception, ex:
                self.log.info(ex)
                return False, ex
            return True, "Pass"
        except Exception, ex:
            return False, ex

    def _run_explain_and_print_result(self, n1ql_query):
        explain_query = "EXPLAIN "+n1ql_query
        try:
            actual_result = self.n1ql_helper.run_cbq_query(query = explain_query, server = self.n1ql_server)
            self.log.info(explain_query)
        except Exception, ex:
            self.log.info(ex)

    def _run_queries_with_explain(self, n1ql_query = None, gsi_index_list =[]):
        error_check = True
        error_messages = []
        # Run n1ql query
        for index_name in gsi_index_list:
            hint = "USE INDEX({0} USING GSI)".format(index_name)
            n1ql = self.query_helper._add_explain_with_hints(n1ql_query, hint)
            self.log.info(n1ql_query)
            error_message = "NA"
            check = True
            try:
                actual_result = self.n1ql_helper.run_cbq_query(query = n1ql, server = self.n1ql_server)
                self.log.info(actual_result)
                check = self.n1ql_helper.verify_index_with_explain(actual_result, index_name)
                error_check = False and error_check
                error_message= " query {0} failed explain result, index {1} not found".format(n1ql_query,index_name)
                self.log.info(error_message)
            except Exception, ex:
                self.log.info(ex)
                error_message = ex
                check = False
            finally:
                error_check = check and error_check
                if not check:
                    error_messages.append(error_message)
        if not error_check:
            return False, error_messages
        return True, "::::".join(error_messages)

    def _run_queries_from_file_and_compare(self, n1ql_query = None, sql_query = None, sql_result = None):
        self.log.info(" SQL QUERY :: {0}".format(sql_query))
        self.log.info(" N1QL QUERY :: {0}".format(n1ql_query))
        # Run n1ql query
        hints = self.query_helper._find_hints(n1ql_query)
        actual_result = self.n1ql_helper.run_cbq_query(query = n1ql_query, server = self.n1ql_server)
        n1ql_result = actual_result["results"]
        self.log.info(actual_result)
        self.log.info(sql_result)
        self.log.info(" result from n1ql query returns {0} items".format(len(n1ql_result)))
        self.log.info(" result from sql query returns {0} items".format(len(sql_result)))
        try:
            self.n1ql_helper._verify_results_rqg(sql_result = sql_result, n1ql_result = n1ql_result, hints = hints)
        except Exception, ex:
            self.log.info(ex)
            return False, ex
        return True, "Pass"

    def _initialize_cluster_setup(self):
        self.use_mysql= self.input.param("use_mysql",True)
        if self.use_mysql:
            self.log.info(" Will load directly from mysql")
            self._initialize_mysql_client()
            self._setup_and_load_buckets()
        else:
            self.log.info(" Will load directly from file snap-shot")
            self._setup_and_load_buckets_from_files()
        self._initialize_n1ql_helper()
        self.sleep(10)
        self._build_primary_indexes()

    def _build_primary_indexes(self, using_gsi= True):
        self.n1ql_helper.create_primary_index(using_gsi = using_gsi, server = self.n1ql_server)

    def _load_data_in_buckets_using_mc_bin_client(self, bucket, data_set):
        client = VBucketAwareMemcached(RestConnection(self.master), bucket)
        try:
            for key in data_set.keys():
                o, c, d = client.set(key, 0, 0, json.dumps(data_set[key]))
        except Exception, ex:
            print 'WARN======================='
            print ex

    def _load_data_in_buckets_using_mc_bin_client_json(self, bucket, data_set):
        client = VBucketAwareMemcached(RestConnection(self.master), bucket)
        try:
            for key in data_set.keys():
                o, c, d = client.set(key.encode("utf8"), 0, 0, json.dumps(data_set[key]))
        except Exception, ex:
            print 'WARN======================='
            print ex

    def _load_data_in_buckets(self, bucket_name, data_set):
        from sdk_client import SDKClient
        scheme = "couchbase"
        host=self.master.ip
        if self.master.ip == "127.0.0.1":
            scheme = "http"
            host="{0}:{1}".format(self.master.ip,self.master.port)
        client = SDKClient(scheme=scheme,hosts = [host], bucket = bucket_name)
        client.upsert_multi(data_set)
        client.close()

    def _initialize_n1ql_helper(self):
        self.n1ql_helper = N1QLHelper(version = "sherlock", shell = None,
            use_rest = True, max_verify = self.max_verify,
            buckets = self.buckets, item_flag = None,
            n1ql_port = self.n1ql_server.n1ql_port, full_docs_list = [],
            log = self.log, input = self.input, master = self.master)

    def _initialize_mysql_client(self):
        self.client = MySQLClient(database = self.database, host = self.mysql_url,
            user_id = self.user_id, password = self.password)

    def _zipdir(self, path, zip_path):
        self.log.info(zip_path)
        zipf = zipfile.ZipFile(zip_path, 'w')
        for root, dirs, files in os.walk(path):
            for file in files:
                zipf.write(os.path.join(root, file))

    def _calculate_secondary_indexing_information(self, query_list = []):
        secondary_index_table_map = {}
        table_field_map = self.client._get_field_list_map_for_tables()
        for table_name in table_field_map.keys():
            field_list = table_field_map[table_name]
            secondary_index_list = set([])
            for query in query_list:
                tokens = query.split(" ")
                check_for_table_name = False
                check_for_as = False
                table_name_alias = None
                for token in tokens:
                    if (not check_for_table_name) and (token == table_name):
                        check = True
                    if (not check_for_as) and check_for_table_name and (token == "AS" or token == "as"):
                        check_for_table_name = True
                    if check_for_table_name and token != " ":
                        table_name_alias  = token
                if table_name in query:
                    list = []
                    for field in table_field_map[table_name]:
                        field_name = field
                        if table_name_alias:
                            field_name = table_name_alias+"."+field_name
                        if field_name in query:
                            list.append(field)
                    if len(list) > 0:
                        secondary_index_list = set(secondary_index_list).union(set(list))
            list = []
            index_map ={}
            if len(secondary_index_list) > 0:
                list = [element for element in secondary_index_list]
                index_name = "{0}_{1}".format(table_name,"_".join(list))
                index_map = {index_name:list}
            for field in list:
                index_name = "{0}_{1}".format(table_name,field)
                index_map[index_name] = [field]
            if len(index_map) > 0:
                secondary_index_table_map[table_name] = index_map
        return secondary_index_table_map

    def _generate_result(self, data):
        result = ""
        for key in data.keys():
            result +="<<<<<<<<<< TEST {0} >>>>>>>>>>> \n".format(key)
            for result_key in data[key].keys():
                result += "{0} :: {1} \n".format(result_key, data[key][result_key])
        return result

    def _generate_secondary_indexes(self, query_list):
        if not self.gen_secondary_indexes:
            return
        secondary_index_table_map = self._calculate_secondary_indexing_information(query_list)
        for table_name in secondary_index_table_map.keys():
            self.log.info(" Building Secondary Indexes for Bucket {0}".format(table_name))
            for index_name in secondary_index_table_map[table_name].keys():
                query = "Create Index {0} on {1}({2}) ".format(index_name, table_name,
                    ",".join(secondary_index_table_map[table_name][index_name]))
                if self.gen_gsi_indexes:
                    query += " using gsi"
                self.log.info(" Running Query {0} ".format(query))
                try:
                    actual_result = self.n1ql_helper.run_cbq_query(query = query, server = self.n1ql_server)
                    check = self.n1ql_helper.is_index_online_and_in_list(table_name, index_name,
                        server = self.n1ql_server, timeout = 240)
                except Exception, ex:
                    self.log.info(ex)
                    raise

    def _generate_secondary_indexes_with_index_map(self, index_map = {}, table_name = "simple_table"):
        self.log.info(" Building Secondary Indexes for Bucket {0}".format(table_name))
        for index_name in index_map.keys():
            query =index_map[index_name]
            self.log.info(" Running Query {0} ".format(query))
            try:
                actual_result = self.n1ql_helper.run_cbq_query(query = query, server = self.n1ql_server)
                check = self.n1ql_helper.is_index_online_and_in_list(table_name, index_name,
                    server = self.n1ql_server, timeout = 240)
            except Exception, ex:
                self.log.info(ex)
                raise

    def _drop_secondary_indexes_with_index_map(self, index_map = {}, table_name = "simple_table"):
        self.log.info(" Dropping Secondary Indexes for Bucket {0}".format(table_name))
        for index_name in index_map.keys():
            query ="DROP INDEX {0}.{1} USING GSI".format(table_name, index_name)
            try:
                self.n1ql_helper.run_cbq_query(query = query, server = self.n1ql_server)
            except Exception, ex:
                self.log.info(ex)
                raise

    def _convert_fun_result(self, result_set):
        list = []
        for data in result_set:
            map = {}
            for key in data.keys():
                val = data[key]
                if val == None:
                    val =0
                if not isinstance(val, int):
                    val = str(val)
                    if val == "":
                        val = 0
                map[key] =  val
            list.append(map)
        return list

    def _take_snapshot_of_database(self):
        self.zip_path= self.input.param("zip_path","flightstats_data.zip")
        self.data_dump_path= self.input.param("data_dump_path","b/resources/flightstats_mysql")
        # Pull information about tables from mysql database and interpret them as no-sql dbs
        table_key_map = self.client._get_primary_key_map_for_tables()
        # Make a list of buckets that we want to create for querying
        bucket_list = table_key_map.keys()
        # Read Data from mysql database and populate the couchbase server
        for bucket_name in bucket_list:
            query = "select * from {0}".format(bucket_name)
            columns, rows = self.client._execute_query(query = query)
            dict = self.client._gen_json_from_results_with_primary_key(
                columns, rows, table_key_map[bucket_name])
            # Take snap-shot of Data in
            f = open(self.data_dump_path+"/"+bucket_name+".txt",'w')
            f.write(json.dumps(dict))
            f.close()
        self._zipdir(self.data_dump_path, self.zip_path)

    def _setup_and_load_buckets_from_files(self):
        bucket_list =[]
        import shutil
        self.data_dump_path= self.input.param("data_dump_path","b/resources/flightstats_mysql/data_set")
        self.zip_path= self.input.param("zip_path","b/resources/flightstats_mysql/flightstats_data.zip")
        shutil.rmtree(self.data_dump_path, ignore_errors=True)
        #Unzip the files and get bucket list
        with zipfile.ZipFile(self.zip_path, "r") as z:
            z.extractall(".")
        from os import listdir
        from os.path import isfile, join
        onlyfiles = [ f for f in listdir(self.data_dump_path) if isfile(join(self.data_dump_path,f))]
        for file in onlyfiles:
            bucket_list.append(file.split(".")[0])
        # Remove any previous buckets
        rest = RestConnection(self.master)
        for bucket in self.buckets:
            rest.delete_bucket(bucket.name)
        self.buckets = []
        # Create New Buckets
        self._create_buckets(self.master, bucket_list, server_id=None, bucket_size=None)
        # Wait till the buckets are up
        self.sleep(15)
        # Read Data from mysql database and populate the couchbase server
        for bucket_name in bucket_list:
             for bucket in self.buckets:
                if bucket.name == bucket_name:
                    file_path = self.data_dump_path+"/"+bucket_name+".txt"
                    with open(file_path) as data_file:
                        data = json.load(data_file)
                        self._load_data_in_buckets_using_mc_bin_client_json(bucket, data)
        shutil.rmtree(self.data_dump_path, ignore_errors=True)

    def _setup_and_load_buckets(self):
        # Remove any previous buckets
        rest = RestConnection(self.master)
        for bucket in self.buckets:
            rest.delete_bucket(bucket.name)
        self.buckets = []
        # Pull information about tables from mysql database and interpret them as no-sql dbs
        table_key_map = self.client._get_primary_key_map_for_tables()
        # Make a list of buckets that we want to create for querying
        bucket_list = table_key_map.keys()
        # Create New Buckets
        self._create_buckets(self.master, bucket_list, server_id=None, bucket_size=None)
        # Wait till the buckets are up
        self.sleep(15)
        # Read Data from mysql database and populate the couchbase server
        for bucket_name in bucket_list:
            query = "select * from {0}".format(bucket_name)
            print query
            columns, rows = self.client._execute_query(query = query)
            dict = self.client._gen_json_from_results_with_primary_key(columns, rows,
                primary_key = table_key_map[bucket_name])
            for bucket in self.buckets:
                if bucket.name == bucket_name:
                    self._load_data_in_buckets_using_mc_bin_client(bucket, dict)





