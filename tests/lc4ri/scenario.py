"""Operator steps for the disposable Hadoop cluster."""
import csv
import io
import json
import os
import re

import yaml

MIRROR = 'http://172.29.88.1:18555'
ADDRESSES = {'nn1': '172.29.88.10', 'nn2': '172.29.88.11', 'dn1': '172.29.88.12'}


def host_table(template, security):
    header = next(csv.reader(io.StringIO(template)))
    rows = []
    for name, address in ADDRESSES.items():
        row = dict.fromkeys(header, '')
        row.update(Cluster='TestCluster', Type='qemu', Name=name, **{
            'Service IP': address, 'VCPUs': '2', 'Memory(MiB)': '6144' if name != 'dn1' else '4096',
            'DFS Volumes': '1', 'YARN VCPUs': '2',
            'YARN Total Memory(MB)': '4096' if name != 'dn1' else '2048',
            'ZooKeeper': 'x', 'JournalNode': 'x', 'DataNode': 'x', 'NodeManager': 'x'})
        if name != 'dn1':
            row.update(NameNode='x', ResourceManager='x')
        if name == 'nn1':
            for role in ['Ganglia', 'TimelineService', 'MapReduce HistoryServer', 'HBase Master',
                         'HBase RegionServer', 'Pig', 'Client', 'Spark', 'Spark HistoryServer']:
                row[role] = 'x'
            if security:
                row['KDC Master'] = 'x'
        rows.append(row)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=header, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def enter_inventory_inputs(session, controls, index, text):
    if text.startswith('!diff -ur ') and 'hosts-old.csv' in text:
        session.edit_file('hosts.csv', host_table(session.read_file('hosts.csv'),
                                                os.environ['HADOOP_SECURITY_MODE'] == 'kerberos'))
    if text.startswith('!diff -ur ') and 'inventory-old' in text:
        outputs = controls.state(controls.find('%run scripts/inventory-hadoop.py'))['outputs']
        generated = ''.join(output['text'] for output in outputs if output['output_type'] == 'stream')
        generated = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', generated).replace('\r\n', '\n')
        session.edit_file('inventory', session.read_file('inventory') + '\n' + generated)
    if text.startswith('archive_url ='):
        controls.edit(index, 'archive_url = ' + repr(MIRROR), 'Enter the archive server')
    if text.strip() == '!ls -la group_vars/':
        path = 'group_vars/hadoop_all_testcluster'
        values = yaml.safe_load(session.read_file(path))
        manifest = json.loads((session.results / 'package-manifest.json').read_text())
        values.update({item['package'] + '_release_url': MIRROR + '/' + item['filename'] for item in manifest})
        values.update(resourcemanager_heap_size='256', nodemanager_heap_size='256',
                      job_historyserver_heapsize='256', timelineserver_heap_size='256',
                      namenode_total_java_heap='512m', namenode_heap_size='512',
                      datanode_heap_size='256', journalnode_heap_size='128', zkfc_heap_size='128',
                      zookeeper_heap_size='128')
        if os.environ['HADOOP_SECURITY_MODE'] == 'kerberos':
            password = os.environ['KERBEROS_TEST_PASSWORD']
            values.update(kerberos_master_key_password=password, https_keystore_pass=password,
                          https_truststore_pass=password, https_privkey_pass=password, datanode_https_port='50475')
        session.edit_file(path, yaml.safe_dump(values, sort_keys=False))


def run(session):
    mode = os.environ['HADOOP_SECURITY_MODE']
    assert mode in ('simple', 'kerberos'), mode
    session.api('contents/inventory', 'PUT', dict(type='file', format='text',
                content='[seed]\n' + '\n'.join(ADDRESSES.values()) + '\n'))
    session.api('contents/ansible.cfg', 'PUT', dict(type='file', format='text', content='''[defaults]
inventory = /home/jovyan/work/inventory
remote_user = ansible
private_key_file = /home/jovyan/.ssh/id_rsa
interpreter_python = /usr/bin/python3
host_key_checking = True
log_path = /home/jovyan/work/ansible.log
[ssh_connection]
pipelining = True
'''))
    session.api('contents/group_vars', 'PUT', dict(type='directory'))

    run_notebook = session.run_notebook
    run_notebook('D00_Prerequisites for Literate Computing via Notebooks.ipynb')
    run_notebook('D10_Hadoop - Set! Inventory.ipynb', before_cell=enter_inventory_inputs)
    run_notebook('D12_Hadoop - Ready! on CentOS6 - ZK,HDFS,YARN,HBase,Hive,Spark.ipynb')
    run_notebook('T12a_Hadoop - Confirm the services are alive - ZK,HDFS,YARN,HBase,Spark.ipynb')
    run_notebook('T12d_Hadoop - Simple Spark script for Test.ipynb')
