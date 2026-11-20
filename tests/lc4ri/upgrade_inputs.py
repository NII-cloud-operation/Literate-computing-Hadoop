"""Operator input and inspection of the complete-system upgrade notebooks."""
import ast
import json
import os
import re
import time
import urllib.request

import yaml
from scenario import ADDRESSES, MIRROR


def stream_output(observed):
    return ''.join(''.join(o.get('text', [])) for o in observed.get('outputs', []) if o['output_type'] == 'stream')


def notebook_output(session):
    book = session.page.evaluate('window.jupyterapp.shell.currentWidget.context.model.toJSON()')
    return ''.join(stream_output(c) for c in book['cells'])


def enter_upgrade_inputs(session, controls, index, text):
    if text.startswith('active_namenode_host ='):
        output = notebook_output(session)
        roles = dict(re.findall(r'(nn[12]):\d+\s+(active|standby)', output))
        assert sorted(roles.values()) == ['active', 'standby'], output
        active = next(n for n, state in roles.items() if state == 'active')
        standby = next(n for n, state in roles.items() if state == 'standby')
        controls.edit(index, f'active_namenode_host = {ADDRESSES[active]!r}\nstandby_namenode_host = {ADDRESSES[standby]!r}\n'
                      f'active_namenode_id = {active!r}\nstandby_namenode_id = {standby!r}\n'
                      '(active_namenode_host, standby_namenode_host, active_namenode_id, standby_namenode_id)\n',
                      'Enter observed NameNode roles and inventory addresses')
    if re.match(r'\w+_version =', text):
        values = {n.targets[0].id: ast.literal_eval(n.value) for n in ast.parse(text).body if isinstance(n, ast.Assign)}
        component = next(k.removesuffix('_version') for k in values if k.endswith('_version'))
        if component == 'hadoop':
            assert values['hadoop_version'] == os.environ['HADOOP_UPGRADE_TO_VERSION'], values
        session.upgrade[component + '_version'] = values[component + '_version']
        url = values[component + '_release_url']
        controls.edit(index, text.replace(url, MIRROR + '/' + url.rsplit('/', 1)[-1]),
                      'Use the checksum-verified local archive mirror')
    if text.startswith('! ! diff -u'):
        path = 'group_vars/hadoop_all_testcluster'
        original = session.read_file(path)
        snippet = stream_output(controls.state(controls.find('print(f"""hadoop_package_filename:')))
        values = yaml.safe_load(original)
        values.update(yaml.safe_load(snippet))
        updated = yaml.safe_dump(values, sort_keys=False)
        assert updated != original
        session.edit_file(path, updated)
    if text.startswith('zookeeper_host ='):
        states = {}
        for name, address in ADDRESSES.items():
            with urllib.request.urlopen(f'http://{address}:8080/commands/mntr', timeout=15) as response:
                states[name] = json.load(response)
        assert sorted(s.get('server_state', '') for s in states.values()) == ['follower', 'follower', 'leader'], states
        remaining = set(ADDRESSES) - session.upgrade_zookeepers
        followers = [n for n in sorted(remaining) if states[n].get('server_state') == 'follower']
        name = followers[0] if followers else sorted(remaining)[0]
        session.upgrade_zookeepers.add(name)
        controls.edit(index, f'zookeeper_host = {ADDRESSES[name]!r}\nzookeeper_host\n',
                      'Select an unupgraded follower, leaving the current leader until last')
    if text.startswith('upgrade_host ='):
        name = session.upgrade_host
        if session.current_notebook.startswith('O12h'):
            source = f'upgrade_host = {ADDRESSES[name]!r}\ndatanode_ipc_port = 9867\n(upgrade_host, datanode_ipc_port)\n'
        else:
            source = f'upgrade_host = {ADDRESSES[name]!r}\nupgrade_host\n'
            session.upgrade['platform_updates'] = True
        controls.edit(index, source, 'Select the next host from inventory')
    if text.startswith('platform_active_id ='):
        output = notebook_output(session)
        roles = dict(re.findall(r'(nn[12]):\d+\s+(active|standby)', output))
        active = next(n for n, state in roles.items() if state == 'active')
        standby = next(n for n, state in roles.items() if state == 'standby')
        controls.edit(index, f'platform_active_id = {active!r}\nplatform_standby_id = {standby!r}\n'
                      f'platform_failover = {session.upgrade_host == active!r}\n'
                      '(platform_active_id, platform_standby_id, platform_failover)\n',
                      'Move the Active NameNode away from the host being serviced')
    if text.startswith('namenode_https_port ='):
        if os.environ['HADOOP_SECURITY_MODE'] == 'kerberos':
            controls.edit(index, text.replace('/etc/ssl/certs/ca-certificates.crt', '/etc/hadoop/conf/ca-certificates.pem'),
                          'Select the test cluster CA bundle')


def wait_for_upgrade_state(session, controls, index, text, observed):
    """Repeat readiness queries before the next notebook operation."""
    def wait_until(predicate, timeout=180):
        nonlocal observed
        deadline = time.monotonic() + timeout
        while True:
            output = stream_output(observed)
            session.records.append(dict(notebook=session.current_notebook, cell=index, action='inspect output', output=output))
            if predicate(output):
                return output
            assert time.monotonic() < deadline, output
            time.sleep(2)
            observed = controls.run(index)

    if 'hdfs dfsadmin -rollingUpgrade prepare' in text:
        session.upgrade['prepared'] = True
    if 'hdfs dfsadmin -rollingUpgrade finalize' in text:
        session.upgrade['prepared'] = False
    if 'hdfs dfsadmin -rollingUpgrade query' in text:
        expected = 'Proceed with rolling upgrade' if session.upgrade['prepared'] else 'no rolling upgrade in progress'
        wait_until(lambda value: expected.lower() in value.lower())
    if 'hdfs dfsadmin -report' in text:
        wait_until(lambda value: 'Live datanodes (3):' in value and all(re.search(r'^\s*' + label + r': 0\s*$', value, re.M)
                   for label in ('Missing blocks', 'Blocks with corrupt replicas', 'Under replicated blocks')))
    if 'hdfs haadmin -getServiceState ' in text:
        wait_until(lambda value: re.search(r'^standby\s*$', value, re.M))
    if 'NameNodeInfo' in text and session.current_notebook.startswith('O12j'):
        wait_until(lambda value: len(re.findall(r'"RollingUpgradeStatus"\s*:\s*null', value)) == 2)
