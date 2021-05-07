import os
from netaddr import IPAddress
import yaml

def get_ip(x):
    return x['Internal IP'] or x['Service IP']


def write_kerberos_vars(target_machines, outf):
    kerberos_servers = [m for m in target_machines if m['KDC Master'] or m['KDC Slave']]
    outf.write('kerberos_realm: "{}.ECLOUD.NII.AC.JP"\n'.format(kerberos_servers[0]['Cluster'].upper()))
    outf.write('kerberos_admin_principal: ansible/admin\n')
    outf.write('kerberos_admin_keytab: /home/ansible/.keytab\n')
    outf.write('https_keystore_path: /etc/hadoop/conf/keystore.jks\n')
    #outf.write('https_keystore_pass: "TBD"\n')
    outf.write('https_truststore_path: /etc/hadoop/conf/truststore.jks\n')
    #outf.write('https_truststore_pass: "TBD"\n')
    #outf.write('https_privkey_pass: "TBD"\n')
    kerberos_slaves = [m for m in kerberos_servers if m['KDC Slave']]
    outf.write('kerberos_kdc_slaves:\n{}\n\n'.format('\n'.join(map(lambda x: '  - ' + get_ip(x), kerberos_slaves))))


def write_hadoop_group_vars(target_machines, outf, archive_url, hdp_version='2.4.2.0'):
    namenodes = [m for m in target_machines if m['NameNode']]
    datanodes = [m for m in target_machines if m['DataNode']]
    journalnodes = [m for m in target_machines if m['JournalNode']]
    zknodes = [m for m in target_machines if m['ZooKeeper']]
    resourcemanagers = [m for m in target_machines if m['ResourceManager']]
    timelineservices = [m for m in target_machines if m['TimelineService']]
    nodemanagers = [m for m in target_machines if m['NodeManager']]
    mapreduceHistoryservers = [m for m in target_machines if m['MapReduce HistoryServer']]
    hbaseRegionservers = [m for m in target_machines if m['HBase RegionServer']]
    hbaseMasters = [m for m in target_machines if m['HBase Master']]
    clients = [m for m in target_machines if m['Client']]
    hiveNodes = [m for m in target_machines if m['Hive']]
    pigNodes = [m for m in target_machines if m['Pig']]
    tezNodes = [m for m in target_machines if m['Tez']]
    sparkServers = [m for m in target_machines if m['Spark']]
    sparkHistoryservers = [m for m in target_machines if m['Spark HistoryServer']]
    ganglia_masters = [m for m in target_machines if m['Ganglia']]
    kerberos_servers = [m for m in target_machines if m['KDC Master'] or m['KDC Slave']]

    assert(len(namenodes) == 2)
    assert(nodemanagers == datanodes)
    assert(len(mapreduceHistoryservers) == 1)
    slavenodes = datanodes

    if hdp_version == '2.2.0.0':
        outf.write("""
# HDP repository
base_hdp_hdp_baseurl: 'http://xxx.nii.ac.jp/v1/AUTH_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXX/HDP-2.2/HDP-2.2.0.0'
base_hdp_hdp_gpgcheck: '1'
base_hdp_hdp_gpgkeyurl: 'http://xxx.nii.ac.jp/v1/AUTH_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXX/HDP-2.2/RPM-GPG-KEY/RPM-GPG-KEY-Jenkins'
base_hdp_util_baseurl: 'http://xxx.nii.ac.jp/v1/AUTH_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXX/HDP-2.2/HDP-UTILS-1.1.0.20'
base_hdp_util_gpgcheck: '1'
base_hdp_util_gpgkeyurl: 'http://xxx.nii.ac.jp/v1/AUTH_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXX/HDP-2.2/RPM-GPG-KEY/RPM-GPG-KEY-Jenkins'
""")
    elif hdp_version == '2.3.4.0':
        outf.write("""
# HDP repository
hdp_version: '2.3.4.0-3485'
base_hdp_hdp_baseurl: 'http://public-repo-1.hortonworks.com/HDP/centos6/2.x/updates/2.3.4.0'
base_hdp_hdp_gpgcheck: '1'
base_hdp_hdp_gpgkeyurl: 'http://public-repo-1.hortonworks.com/HDP/centos6/2.x/updates/2.3.4.0/RPM-GPG-KEY/RPM-GPG-KEY-Jenkins'
base_hdp_util_baseurl: 'http://public-repo-1.hortonworks.com/HDP-UTILS-1.1.0.20/repos/centos6'
base_hdp_util_gpgcheck: '1'
base_hdp_util_gpgkeyurl: 'http://public-repo-1.hortonworks.com/HDP/centos6/2.x/updates/2.3.4.0/RPM-GPG-KEY/RPM-GPG-KEY-Jenkins'
""")
    elif hdp_version == '2.4.2.0':
        outf.write("""
# HDP repository
hdp_version: '2.4.2.0-258'
base_hdp_hdp_baseurl: 'http://public-repo-1.hortonworks.com/HDP/centos6/2.x/updates/2.4.2.0'
base_hdp_hdp_gpgcheck: '1'
base_hdp_hdp_gpgkeyurl: 'http://public-repo-1.hortonworks.com/HDP/centos6/2.x/updates/2.4.2.0/RPM-GPG-KEY/RPM-GPG-KEY-Jenkins'
base_hdp_util_baseurl: 'http://public-repo-1.hortonworks.com/HDP-UTILS-1.1.0.20/repos/centos6'
base_hdp_util_gpgcheck: '1'
base_hdp_util_gpgkeyurl: 'http://public-repo-1.hortonworks.com/HDP/centos6/2.x/updates/2.4.2.0/RPM-GPG-KEY/RPM-GPG-KEY-Jenkins'
""")
    else:
        assert False
        
    outf.write('\n# define servers\n')
    outf.write("gmond: '%s'\n" % get_ip(ganglia_masters[0]))
    outf.write("ganglia_cluster: '%s'\n" % ganglia_masters[0]['Cluster'])
    outf.write("ganglia_master: '%s'\n\n" % get_ip(ganglia_masters[0]))
    
    if kerberos_servers:
        write_kerberos_vars(kerberos_servers, outf)

    outf.write("zookeeper_servers:\n")
    for n in zknodes:
        outf.write("  - '%s'\n" % n["Name"])
    outf.write("\n")
    
    outf.write("hadoop_namenode_servers:\n")
    for n in namenodes:
        outf.write("  - '%s'\n" % n["Name"])
    outf.write("\n")
    
    outf.write("hadoop_slavenode_servers:\n")
    for n in slavenodes:
        outf.write("  - '%s'\n" % n["Name"])
    outf.write("\n")
    
    outf.write("hadoop_journalnode_servers:\n")
    for n in journalnodes:
        outf.write("  - '%s'\n" % n["Name"])
    outf.write("\n")
    
    outf.write("hadoop_resourcemanager_servers:\n")
    for n in resourcemanagers:
        outf.write("  - '%s'\n" % n["Name"])
    outf.write("\n")

    if timelineservices:
        outf.write("hadoop_timelineservice_server: '%s'\n" % timelineservices[0]["Name"])
        outf.write("\n")
    
    outf.write("mapreduce_historyserver_address: '%s'\n" % mapreduceHistoryservers[0]['Name'])
    
    outf.write("""
# cgroups
cgroups_scripts_dir: '/var/local/cgroups'

# Java
jdk7_downloadurl: '%s'
jdk8_downloadurl: '%s'
""" % (archive_url, archive_url))

    if hdp_version == '2.2.0.0':
        outf.write("# Swimlane\nswimlane_download_url: 'http://xxx.nii.ac.jp/v1/AUTH_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXX/HDP-2.2/archive'\n\n")
    elif hdp_version == '2.3.4.0':
        outf.write("# Swimlane\nswimlane_tez_version: '0.7.0'\n\n")
    elif hdp_version == '2.4.2.0':
        outf.write("# Swimlane\nswimlane_tez_version: '0.8.4'\n\n")

    outf.write("""# HDFS
dfs_namenode_name_dirs:
  - '/hadoop/data/dfs/namedir'
  
""")
    
    outf.write('dfs_datanode_data_dirs:\n')
    for index in range(0, int(max(map(lambda m: m['DFS Volumes'], datanodes)))):
        outf.write("  - '/hadoop/data%02d/dfs/datadir'\n" % (index + 1))
    
    outf.write("dfs_replication: '3'")

    outf.write("""
dfs_journalnode_edits_dir: '/hadoop/data/jn'

# HBase
hbase_root_dir: '/hbase'

# Hive
hive_metastore_dir: '/hadoop/data/hive/metastore'

# Zookeeper
zookeeper_data_dir: '/hadoop/zookeeper'

# YARN
yarn_nodemanager_delete_debug_delay_sec: '3600'
""")
    containermb = int(min(map(lambda m: m['YARN Total Memory(MB)'] / m['YARN VCPUs'], nodemanagers)))
    outf.write('mapreduce_am_resource_mb: %d\nmapreduce_am_command_opts: "-Xmx%dm"\n' % (containermb, containermb - 256))
    outf.write('mapreduce_map_memory_mb: %d\nmapreduce_map_java_opts: "-Xmx%dm"\n' % (containermb, containermb - 256))
    outf.write('mapreduce_reduce_memory_mb: %d\nmapreduce_reduce_java_opts: "-Xmx%dm"\n' % (containermb, containermb - 256))

    outf.write('''
# Spark
spark_download_url: 'http://xxx.nii.ac.jp/v1/AUTH_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXX/HDP-2.2/archive'
''')
    outf.write("spark_history_server_host: '%s'\n" % sparkHistoryservers[0]['Name'])

                
def write_hadoop_inventory(target_machines, outf):
    cluster = target_machines[0]['Cluster'].lower()
    namenodes = [m for m in target_machines if m['NameNode']]
    datanodes = [m for m in target_machines if m['DataNode']]
    journalnodes = [m for m in target_machines if m['JournalNode']]
    zknodes = [m for m in target_machines if m['ZooKeeper']]
    resourcemanagers = [m for m in target_machines if m['ResourceManager']]
    timelineservices = [m for m in target_machines if m['TimelineService']]
    nodemanagers = [m for m in target_machines if m['NodeManager']]
    mapreduceHistoryservers = [m for m in target_machines if m['MapReduce HistoryServer']]
    hbaseRegionservers = [m for m in target_machines if m['HBase RegionServer']]
    hbaseMasters = [m for m in target_machines if m['HBase Master']]
    clients = [m for m in target_machines if m['Client']]
    hiveNodes = [m for m in target_machines if m['Hive']]
    pigNodes = [m for m in target_machines if m['Pig']]
    tezNodes = [m for m in target_machines if m['Tez']]
    sparkServers = [m for m in target_machines if m['Spark']]
    sparkHistoryservers = [m for m in target_machines if m['Spark HistoryServer']]
    kerberosMasters = [m for m in target_machines if m['KDC Master']]

    assert(1 <= len(namenodes) and len(namenodes) <= 2)
    assert(nodemanagers == datanodes)
    assert(len(mapreduceHistoryservers) == 1)
    slavenodes = datanodes

    hosts_content = { "hadoop_all:children": ["hadoop_master", "hadoop_client", "hadoop_slavenode", "hadoop_hbase", "hadoop_spark"],
                  "hadoop_master:children": ["hadoop_namenode", "hadoop_zookeeperserver", "hadoop_resourcemanager"],
                  "hadoop_namenode_primary": [namenodes[0]],
                  "hadoop_zookeeperserver": [n for n in zknodes],
                  "hadoop_resourcemanager": [n for n in resourcemanagers],
                  "hadoop_timelineservice": [n for n in timelineservices],
                  "hadoop_mapreduce_historyserver": [n for n in mapreduceHistoryservers],
                  "hadoop_tez": [n for n in tezNodes],
                  "hadoop_hbase:children": ["hadoop_hbase_master", "hadoop_hbase_regionserver"],
                  "hadoop_hbase_master": [n for n in hbaseMasters],
                  "hadoop_hbase_regionserver": [n for n in hbaseRegionservers],
                  "hadoop_slavenode": [n for n in slavenodes],
                  "hadoop_client": [n for n in clients],
                  "hadoop_hive": [n for n in hiveNodes],
                  "hadoop_pig": [n for n in pigNodes],
                  "hadoop_swimlane": [n for n in clients],
                  "hadoop_spark": [n for n in sparkServers],
                  "hadoop_spark_history": [n for n in sparkHistoryservers],
                  "kerberos_master": [n for n in kerberosMasters]
                }
    if len(namenodes) == 2:
        hosts_content["hadoop_namenode_backup"] = [namenodes[1]]
        hosts_content["hadoop_namenode:children"] = ["hadoop_namenode_primary", "hadoop_namenode_backup"]
        hosts_content["hadoop_journalnode"] = [n for n in journalnodes]
        hosts_content["hadoop_master:children"].append("hadoop_journalnode")
    else:
        hosts_content["hadoop_namenode:children"] = ["hadoop_namenode_primary"]        

    for (key, addresses) in filter(lambda item: item[1], hosts_content.items()):
        if key.endswith(':children'):
            outf.write("[{group}_{cluster}:children]\n".format(group=key.split(':')[0], cluster=cluster))
        else:
            outf.write("[{group}_{cluster}]\n".format(group=key, cluster=cluster))

        for (index, address) in enumerate(addresses):
            config = ''
            if key == "hadoop_zookeeperserver":
                config = 'zookeeper_server_id=%d' % (index + 1)
            elif key == "hadoop_slavenode":
                nodemanagervcpus = address['YARN VCPUs']
                nodemanagermb = address['YARN Total Memory(MB)']
                config = 'yarn_nodemanager_resource_cpu_vcores=%d yarn_nodemanager_resource_memory_mb=%d ' % (nodemanagervcpus, nodemanagermb)

            if 'Internal IP' in address or 'Service IP' in address:
                outf.write("{} {}\n".format(get_ip(address), config))
            else:
                outf.write("{}_{} {}\n".format(address, cluster, config))
        outf.write("\n")    
    
    aliases = []
    for (key, addresses) in filter(lambda item: item[1], hosts_content.items()):
        if key.endswith(':children'):
            key = key.split(':')[0]
        aliases.append((key, '{group}_{cluster}'.format(group=key, cluster=cluster)))
    return aliases