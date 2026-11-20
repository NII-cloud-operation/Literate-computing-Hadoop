"""Serve the repository's Apache packages from the runner-local mirror."""
import argparse
import ast
import os
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.parse import urlparse

import yaml


PACKAGES = {
    'hadoop': ('hadoop', 'hadoop/'),
    'zookeeper': ('zookeeper_server', 'zookeeper/'),
    'spark': ('spark', 'spark/'),
    'jsvc': ('hadoop', 'commons/daemon/'),
    'hbase': ('hbase', 'hbase/'),
}


def download(cache, results):
    cache.mkdir(parents=True, exist_ok=True)
    marker = cache / '.verified'
    if marker.exists():
        marker.unlink()
    manifest = []
    packages = dict(PACKAGES)
    if os.environ.get('HADOOP_TEST_SCENARIO') == 'upgrade':
        packages.update({name + '_upgrade': value for name, value in PACKAGES.items()})
    for package, (defaults, project) in packages.items():
        values = yaml.safe_load(Path('playbooks/group_vars/all', defaults).read_text())
        if package == 'hadoop' and os.environ.get('HADOOP_TEST_SCENARIO') == 'upgrade':
            version = os.environ['HADOOP_UPGRADE_FROM_VERSION']
            values = {'hadoop_release_url': f'https://archive.apache.org/dist/hadoop/common/hadoop-{version}/hadoop-{version}.tar.gz',
                      'hadoop_release_checksum': os.environ['HADOOP_UPGRADE_FROM_CHECKSUM']}
        if package.endswith('_upgrade'):
            component = package.removesuffix('_upgrade')
            notebook = json.loads(Path('O12e_Hadoop - Plan and prepare upgrade.ipynb').read_text())
            text = next(''.join(c['source']) for c in notebook['cells'] if c['cell_type'] == 'code'
                        and ''.join(c['source']).startswith(component + '_version ='))
            inputs = {n.targets[0].id: ast.literal_eval(n.value) for n in ast.parse(text).body
                      if isinstance(n, ast.Assign)}
            values = {package + '_release_url': inputs[component + '_release_url'],
                      package + '_release_checksum': inputs[component + '_release_checksum']}
        path = urlparse(values[package + '_release_url']).path
        _, separator, relative = path.partition('/' + project)
        assert separator, f'Expected an Apache {project} path in {path}'
        url = 'https://archive.apache.org/dist/' + project + relative
        filename = Path(path).name
        algorithm, checksum = values[package + '_release_checksum'].split(':', 1)
        assert algorithm.lower() == 'sha512', algorithm
        expected = ''.join(checksum.split()).lower()
        target = cache / filename
        if not target.is_file():
            partial = target.with_suffix(target.suffix + '.part')
            subprocess.run(['aria2c', '--allow-overwrite=true', '--auto-file-renaming=false',
                            '--max-connection-per-server=16', '--split=16', '--min-split-size=1M',
                            '--connect-timeout=20', '--timeout=60', '--max-tries=3',
                            '--summary-interval=30', '--dir=' + str(cache),
                            '--out=' + partial.name, url], check=True, timeout=1800)
            partial.replace(target)
        with target.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha512').hexdigest()
        assert actual == expected, f'{filename}: expected {expected}, got {actual}'
        manifest.append(dict(package=package, url=url, filename=filename, sha512=actual))
    (results / 'package-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    marker.write_text('Archive verification passed\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('cache', type=Path)
    parser.add_argument('results', type=Path)
    args = parser.parse_args()
    download(args.cache, args.results)
