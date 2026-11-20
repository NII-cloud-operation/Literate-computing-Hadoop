"""Operator steps for the disposable Hadoop cluster."""
import csv
import io
import json
import os
import re
import shlex
import subprocess
import uuid

import yaml
from certificate_acceptance import (HTTPS_ENDPOINTS, capture_certificates, truststore_certificates,
                                    verify_previous_ca_rejected)

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
        values.update({item['package'] + '_release_url': MIRROR + '/' + item['filename'] for item in manifest if not item['package'].endswith('_upgrade')})
        if os.environ.get('HADOOP_TEST_SCENARIO') == 'upgrade':
            hadoop = next(item for item in manifest if item['package'] == 'hadoop')
            values.update(hadoop_package_filename='hadoop-' + os.environ['HADOOP_UPGRADE_FROM_VERSION'],
                          hadoop_release_checksum='sha512:' + hadoop['sha512'])
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
    if mode == 'kerberos':
        run_notebook('D11a_Hadoop - Prepare CA and HTTPS certificates.ipynb', before_cell=enter_certificate_inputs)
    run_notebook('D12_Hadoop - Ready! on CentOS6 - ZK,HDFS,YARN,HBase,Hive,Spark.ipynb')
    run_notebook('T12a_Hadoop - Confirm the services are alive - ZK,HDFS,YARN,HBase,Spark.ipynb')
    run_notebook('T12c_Hadoop - Simple HBase query for Test.ipynb')
    hbase_book = json.loads((session.results / 'T12c-working.ipynb').read_text())
    hbase_output = '\n'.join(''.join(output.get('text', []))
                             for cell in hbase_book['cells']
                             for output in cell.get('outputs', []))
    for value in ('data:class', 'value=Iris-setosa', 'data:sepal_length', 'value=5.4'):
        assert value in hbase_output, hbase_output
    run_notebook('T12d_Hadoop - Simple Spark script for Test.ipynb')
    if os.environ.get('HADOOP_TEST_SCENARIO') == 'upgrade':
        run_upgrade(session)


    if os.environ.get('HADOOP_TEST_SCENARIO') == 'ca-renewal':
        before = capture_certificates(session.results, 'before', ADDRESSES)
        book = run_notebook('O12l_Hadoop - Renew CA certificates.ipynb', before_cell=enter_certificate_inputs)
        assert cell_outputs(book, 's_client')
        dual = capture_certificates(session.results, 'dual', ADDRESSES)
        assert len(set(dual['authorities'])) == 2 and dual['connections'] == before['connections']
        for roots in truststore_certificates(session.results, ADDRESSES).values():
            assert set(roots) == set(dual['authorities'])
        session.ca_address = ADDRESSES['nn1']
        run_notebook('O12m_Hadoop - Replace one host certificate.ipynb', before_cell=enter_certificate_inputs, execution_label='nn1')
        session.ca_address = ADDRESSES['nn2']
        run_notebook('O12m_Hadoop - Replace one host certificate.ipynb', before_cell=enter_certificate_inputs, execution_label='nn2')
        session.ca_address = ADDRESSES['dn1']
        run_notebook('O12m_Hadoop - Replace one host certificate.ipynb', before_cell=enter_certificate_inputs, execution_label='dn1')
        after = capture_certificates(session.results, 'replaced', ADDRESSES)
        for endpoint, cert in after['connections'].items():
            assert cert['public_key_sha256'] != before['connections'][endpoint]['public_key_sha256'], endpoint
        book = run_notebook('O12n_Hadoop - Retire the previous CA.ipynb', before_cell=enter_certificate_inputs)
        assert cell_outputs(book, 's_client')
        final = capture_certificates(session.results, 'final', ADDRESSES)
        assert len(final['authorities']) == 1 and final['authorities'] != before['authorities']
        assert set(final['authorities'] + before['authorities']) == set(dual['authorities'])
        assert final['connections'] == after['connections']
        verify_previous_ca_rejected(before['authority_file'], ADDRESSES)
        for roots in truststore_certificates(session.results, ADDRESSES).values():
            assert roots == final['authorities']
        run_notebook('T12a_Hadoop - Confirm the services are alive - ZK,HDFS,YARN,HBase,Spark.ipynb', execution_label='ca-renewed')
        book = run_notebook('T12c_Hadoop - Simple HBase query for Test.ipynb', execution_label='ca-renewed')
        assert 'value=Iris-setosa' in str(book['cells'])
        book = run_notebook('T12d_Hadoop - Simple Spark script for Test.ipynb', before_cell=enter_ca_spark_inputs, execution_label='ca-renewed')
        assert 'Lines with a: 100, lines with b: 0' in str(book['cells'])

def enter_certificate_inputs(session, controls, index, text):
    if text.startswith('certificate_hosts ='):
        controls.edit(index, 'certificate_hosts = ' + repr({address: name for name, address in ADDRESSES.items()}) + '\ncertificate_hosts\n',
                      'Select the guest addresses and their DNS names')
    if text.startswith('address ='):
        controls.edit(index, f'address = {session.ca_address!r}\naddress', 'Select the host to renew')
    if text.startswith('pki_dir =') and 'replacement' in text:
        controls.edit(index, "pki_dir = '/tmp/lc4ri-pki-replacement'\npki_dir", 'Select the new CA directory')
    elif text.startswith('pki_dir ='):
        controls.edit(index, "pki_dir = '/tmp/lc4ri-pki-initial'\npki_dir\n", 'Select private CA storage outside notebook artifacts')
    if text.startswith('old_ca_certificate_file ='):
        controls.edit(index, "old_ca_certificate_file = '/tmp/lc4ri-pki-initial/ca.crt'\npki_dir = '/tmp/lc4ri-pki-replacement'\n(old_ca_certificate_file, pki_dir)\n",
                      'Select the current public CA certificate and new private CA storage')
    if text.startswith('https_endpoints ='):
        controls.edit(index, 'https_endpoints = ' + repr(HTTPS_ENDPOINTS) + '\nhttps_endpoints\n', 'Select all guest Hadoop HTTPS services')
    if "getpass.getpass('CA key password: ')" in text:
        controls.edit(index, text.replace("getpass.getpass('CA key password: ')", "configuration['https_keystore_pass']"),
                      'Supply the disposable CA password without recording it in the source')


def enter_ca_spark_inputs(session, controls, index, text):
    if text.startswith('hdfs_dataset_dir ='):
        controls.edit(index, "hdfs_dataset_dir = '/dataset/iris-ca-renewed'\nhadoop_client_dir = '~/iris-ca-renewed'\n(hdfs_dataset_dir, hadoop_client_dir)\n",
                      'Use a fresh upload directory and retain the existing input')
    if text.startswith('%%writefile') and 'SimpleApp.py' in text:
        controls.edit(index, text.replace('/dataset/iris/iris.data', '/dataset/iris-ca-renewed/iris.data'),
                      'Read the selected sample dataset')



def cell_outputs(notebook, fragment):
    cells = [cell for cell in notebook['cells']
             if cell['cell_type'] == 'code' and fragment in ''.join(cell['source'])]
    assert cells, f'Expected code cell not found: {fragment}'
    return [''.join(''.join(output['text']) for output in cell['outputs']
                    if output['output_type'] == 'stream') for cell in cells]


def run_upgrade(session):
    from upgrade_inputs import enter_upgrade_inputs, wait_for_upgrade_state
    session.upgrade = {'prepared': False}
    run_notebook = session.run_notebook
    ssh = ['ssh', *shlex.split(os.environ['ANSIBLE_SSH_ARGS']), 'ansible@' + ADDRESSES['nn1'], 'bash', '-seuo', 'pipefail']
    hdfs = 'sudo -n -u hdfs /opt/hadoop/hadoop-' + os.environ['HADOOP_UPGRADE_FROM_VERSION'] + '/bin/hdfs'
    client_path = '/tmp/lc4ri-upgrade-' + uuid.uuid4().hex
    with (session.results / 'upgrade-client.log').open('a') as log:
        subprocess.run(ssh, input=f'{hdfs} dfs -mkdir -p {client_path}\n', text=True,
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)

    def check_hdfs(step):
        value = f'LC4RI upgrade {step}'
        script = (f"printf '%s\\n' '{value}' | {hdfs} dfs -Ddfs.replication=2 -put - {client_path}/{step}\n"
                  f'{hdfs} dfs -cat {client_path}/{step}\n')
        result = subprocess.run(ssh, input=script, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=120)
        with (session.results / 'upgrade-client.log').open('a') as log:
            log.write(step + '\n' + script + '\n' + result.stdout)
        result.check_returncode()
        assert value in result.stdout, result.stdout

    check_hdfs('before-upgrade')
    book = run_notebook('O12e_Hadoop - Plan and prepare upgrade.ipynb', before_cell=enter_upgrade_inputs, after_cell=wait_for_upgrade_state)
    reports = cell_outputs(book, 'hdfs dfsadmin -report')
    assert len(reports) == 1, reports
    assert 'Live datanodes (3):' in reports[-1], reports[-1]
    for label in ('Missing blocks', 'Blocks with corrupt replicas', 'Under replicated blocks'):
        assert re.search(r'^\s*' + label + r': 0\s*$', reports[-1], re.M), reports[-1]
    output, = cell_outputs(book, 'hdfs dfsadmin -rollingUpgrade query')
    assert 'no rolling upgrade in progress' in output.lower(), output
    output, = cell_outputs(book, 'hdfs dfs -checksum')
    checksum_before, = re.findall(r'^\S+\s+MD5-of-\S+\s+([0-9a-f]+)\s*$', output, re.M)
    output, = cell_outputs(book, '-n /tmp/hbase-upgrade-before.rb')
    assert 'preserved' in output and 'ERROR' not in output, output
    check_hdfs('O12e')
    session.upgrade_zookeepers = set()
    book = run_notebook('O12f_Hadoop - Upgrade ZooKeeper.ipynb', before_cell=enter_upgrade_inputs, after_cell=wait_for_upgrade_state, execution_label='first')
    output, = cell_outputs(book, 'commands/srvr')
    assert session.upgrade['zookeeper_version'] in output, output
    assert any(state in output for state in ('leader', 'follower')), output
    check_hdfs('O12f-first')
    book = run_notebook('O12f_Hadoop - Upgrade ZooKeeper.ipynb', before_cell=enter_upgrade_inputs, after_cell=wait_for_upgrade_state, execution_label='second')
    output, = cell_outputs(book, 'commands/srvr')
    assert session.upgrade['zookeeper_version'] in output, output
    assert any(state in output for state in ('leader', 'follower')), output
    check_hdfs('O12f-second')
    book = run_notebook('O12f_Hadoop - Upgrade ZooKeeper.ipynb', before_cell=enter_upgrade_inputs, after_cell=wait_for_upgrade_state, execution_label='third')
    output, = cell_outputs(book, 'commands/srvr')
    assert session.upgrade['zookeeper_version'] in output, output
    assert any(state in output for state in ('leader', 'follower')), output
    check_hdfs('O12f-third')
    book = run_notebook('O12g_Hadoop - Rolling upgrade NameNodes.ipynb', before_cell=enter_upgrade_inputs, after_cell=wait_for_upgrade_state)
    reports = cell_outputs(book, 'hdfs dfsadmin -report')
    assert len(reports) == 2, reports
    assert 'Live datanodes (3):' in reports[-1], reports[-1]
    for label in ('Missing blocks', 'Blocks with corrupt replicas', 'Under replicated blocks'):
        assert re.search(r'^\s*' + label + r': 0\s*$', reports[-1], re.M), reports[-1]
    output, = cell_outputs(book, 'hdfs dfsadmin -rollingUpgrade query')
    assert 'Proceed with rolling upgrade' in output, output
    for host_id in ('standby_namenode_id', 'active_namenode_id'):
        output, = cell_outputs(book, 'hdfs haadmin -getServiceState {' + host_id + '}')
        assert re.search(r'^standby\s*$', output, re.M), output
    check_hdfs('O12g')
    session.upgrade_host = 'nn1'
    book = run_notebook('O12h_Hadoop - Upgrade Hadoop node.ipynb', before_cell=enter_upgrade_inputs, after_cell=wait_for_upgrade_state, execution_label='nn1')
    reports = cell_outputs(book, 'hdfs dfsadmin -report')
    assert len(reports) == 2, reports
    assert 'Live datanodes (3):' in reports[-1], reports[-1]
    for label in ('Missing blocks', 'Blocks with corrupt replicas', 'Under replicated blocks'):
        assert re.search(r'^\s*' + label + r': 0\s*$', reports[-1], re.M), reports[-1]
    check_hdfs('O12h-nn1')
    session.upgrade_host = 'nn2'
    book = run_notebook('O12h_Hadoop - Upgrade Hadoop node.ipynb', before_cell=enter_upgrade_inputs, after_cell=wait_for_upgrade_state, execution_label='nn2')
    reports = cell_outputs(book, 'hdfs dfsadmin -report')
    assert len(reports) == 2, reports
    assert 'Live datanodes (3):' in reports[-1], reports[-1]
    for label in ('Missing blocks', 'Blocks with corrupt replicas', 'Under replicated blocks'):
        assert re.search(r'^\s*' + label + r': 0\s*$', reports[-1], re.M), reports[-1]
    check_hdfs('O12h-nn2')
    session.upgrade_host = 'dn1'
    book = run_notebook('O12h_Hadoop - Upgrade Hadoop node.ipynb', before_cell=enter_upgrade_inputs, after_cell=wait_for_upgrade_state, execution_label='dn1')
    reports = cell_outputs(book, 'hdfs dfsadmin -report')
    assert len(reports) == 2, reports
    assert 'Live datanodes (3):' in reports[-1], reports[-1]
    for label in ('Missing blocks', 'Blocks with corrupt replicas', 'Under replicated blocks'):
        assert re.search(r'^\s*' + label + r': 0\s*$', reports[-1], re.M), reports[-1]
    check_hdfs('O12h-dn1')
    book = run_notebook('O12i_Hadoop - Upgrade HBase and Spark.ipynb', before_cell=enter_upgrade_inputs, after_cell=wait_for_upgrade_state)
    outputs = cell_outputs(book, 'org.apache.hadoop.util.VersionInfo')
    assert len(outputs) == 2, outputs
    for output in outputs:
        assert 'Hadoop ' + session.upgrade['hadoop_version'] in output, output
    output, = cell_outputs(book, '-n /tmp/hbase-upgrade-after.rb')
    assert 'preserved' in output and 'writable' in output and 'ERROR' not in output, output
    output, = cell_outputs(book, 'mapreduce-examples-*.jar pi')
    assert 'Estimated value of Pi' in output, output
    check_hdfs('O12i')
    run_notebook('T12d_Hadoop - Simple Spark script for Test.ipynb', before_cell=enter_post_upgrade_spark_inputs, execution_label='upgraded')
    check_hdfs('T12d-upgraded')
    book = run_notebook('O12j_Hadoop - Verify and finalize upgrade.ipynb', before_cell=enter_upgrade_inputs, after_cell=wait_for_upgrade_state)
    reports = cell_outputs(book, 'hdfs dfsadmin -report')
    assert len(reports) == 2, reports
    assert 'Live datanodes (3):' in reports[-1], reports[-1]
    for label in ('Missing blocks', 'Blocks with corrupt replicas', 'Under replicated blocks'):
        assert re.search(r'^\s*' + label + r': 0\s*$', reports[-1], re.M), reports[-1]
    output, = cell_outputs(book, 'hdfs fsck /')
    assert 'Status: HEALTHY' in output, output
    queries = cell_outputs(book, 'hdfs dfsadmin -rollingUpgrade query')
    assert len(queries) == 2, queries
    assert 'no rolling upgrade in progress' in queries[-1].lower(), queries[-1]
    output, = cell_outputs(book, 'hdfs dfs -checksum')
    checksum_after, = re.findall(r'^\S+\s+MD5-of-\S+\s+([0-9a-f]+)\s*$', output, re.M)
    assert checksum_after == checksum_before, (checksum_before, checksum_after)
    output, = cell_outputs(book, 'NameNodeInfo')
    assert len(re.findall(r'"RollingUpgradeStatus"\s*:\s*null', output)) == 2, output
    versions = cell_outputs(book, 'hdfs namenode -metadataVersion')
    assert len(versions) == 2, versions
    for output in versions:
        image, = re.findall(r'HDFS Image Version:\s*(-?\d+)', output)
        software, = re.findall(r'Software format version:\s*(-?\d+)', output)
        assert image == software, output
    for host_id in ('standby_namenode_id', 'active_namenode_id'):
        output, = cell_outputs(book, 'hdfs haadmin -getServiceState {' + host_id + '}')
        assert re.search(r'^standby\s*$', output, re.M), output
    check_hdfs('O12j')
    session.upgrade_host = 'nn1'
    book = run_notebook('O12k_Hadoop - Update platform packages.ipynb', before_cell=enter_upgrade_inputs, after_cell=wait_for_upgrade_state, execution_label='nn1')
    reports = cell_outputs(book, 'hdfs dfsadmin -report')
    assert len(reports) == 2, reports
    assert 'Live datanodes (3):' in reports[-1], reports[-1]
    for label in ('Missing blocks', 'Blocks with corrupt replicas', 'Under replicated blocks'):
        assert re.search(r'^\s*' + label + r': 0\s*$', reports[-1], re.M), reports[-1]
    output, = cell_outputs(book, '-n /tmp/hbase-upgrade-after.rb')
    assert 'preserved' in output and 'writable' in output and 'ERROR' not in output, output
    output, = cell_outputs(book, 'mapreduce-examples-*.jar pi')
    assert 'Estimated value of Pi' in output, output
    check_hdfs('O12k-nn1')
    session.upgrade_host = 'nn2'
    book = run_notebook('O12k_Hadoop - Update platform packages.ipynb', before_cell=enter_upgrade_inputs, after_cell=wait_for_upgrade_state, execution_label='nn2')
    reports = cell_outputs(book, 'hdfs dfsadmin -report')
    assert len(reports) == 2, reports
    assert 'Live datanodes (3):' in reports[-1], reports[-1]
    for label in ('Missing blocks', 'Blocks with corrupt replicas', 'Under replicated blocks'):
        assert re.search(r'^\s*' + label + r': 0\s*$', reports[-1], re.M), reports[-1]
    output, = cell_outputs(book, '-n /tmp/hbase-upgrade-after.rb')
    assert 'preserved' in output and 'writable' in output and 'ERROR' not in output, output
    output, = cell_outputs(book, 'mapreduce-examples-*.jar pi')
    assert 'Estimated value of Pi' in output, output
    check_hdfs('O12k-nn2')
    session.upgrade_host = 'dn1'
    book = run_notebook('O12k_Hadoop - Update platform packages.ipynb', before_cell=enter_upgrade_inputs, after_cell=wait_for_upgrade_state, execution_label='dn1')
    reports = cell_outputs(book, 'hdfs dfsadmin -report')
    assert len(reports) == 2, reports
    assert 'Live datanodes (3):' in reports[-1], reports[-1]
    for label in ('Missing blocks', 'Blocks with corrupt replicas', 'Under replicated blocks'):
        assert re.search(r'^\s*' + label + r': 0\s*$', reports[-1], re.M), reports[-1]
    output, = cell_outputs(book, '-n /tmp/hbase-upgrade-after.rb')
    assert 'preserved' in output and 'writable' in output and 'ERROR' not in output, output
    output, = cell_outputs(book, 'mapreduce-examples-*.jar pi')
    assert 'Estimated value of Pi' in output, output
    check_hdfs('O12k-dn1')
    run_notebook('T12a_Hadoop - Confirm the services are alive - ZK,HDFS,YARN,HBase,Spark.ipynb', execution_label='upgraded')
    check_hdfs('T12a-upgraded')
    run_notebook('T12d_Hadoop - Simple Spark script for Test.ipynb', before_cell=enter_post_upgrade_spark_inputs, execution_label='platform-updated')
    check_hdfs('T12d-platform-updated')


def enter_post_upgrade_spark_inputs(session, controls, index, text):
    if text.startswith("hdfs_dataset_dir ="):
        suffix = 'platform-updated' if session.upgrade.get('platform_updates') else 'upgraded'
        controls.edit(index, f"hdfs_dataset_dir = '/dataset/iris-{suffix}'\nhadoop_client_dir = '~/iris-{suffix}'\n(hdfs_dataset_dir, hadoop_client_dir)\n",
                      'Select a fresh upload directory and retain the pre-upgrade input')
    if text.startswith('%%writefile') and 'SimpleApp.py' in text:
        suffix = 'platform-updated' if session.upgrade.get('platform_updates') else 'upgraded'
        controls.edit(index, text.replace('/dataset/iris/iris.data', f'/dataset/iris-{suffix}/iris.data'),
                      'Use the selected input directory in the sample application')
