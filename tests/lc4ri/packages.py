"""Serve the repository's Apache packages from the runner-local mirror."""
import argparse
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
    for package, (defaults, project) in PACKAGES.items():
        values = yaml.safe_load(Path('playbooks/group_vars/all', defaults).read_text())
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
            subprocess.run(['curl', '--fail', '--location', '--retry', '3', '--connect-timeout', '20',
                            url, '-o', str(target)], check=True, timeout=900)
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
