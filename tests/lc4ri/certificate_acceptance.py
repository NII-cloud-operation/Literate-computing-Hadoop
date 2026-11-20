"""Check real TLS connections and truststores independently of certificate operations."""
import hashlib
import json
import os
import re
import shlex
import socket
import ssl
import subprocess


HTTPS_ENDPOINTS = [
    ('nn1', 8481), ('nn2', 8481), ('dn1', 8481),
    ('nn1', 50470), ('nn2', 50470),
    ('nn1', 50475), ('nn2', 50475), ('dn1', 50475),
    ('nn1', 8088), ('nn2', 8088),
    ('nn1', 8044), ('nn2', 8044), ('dn1', 8044),
    ('nn1', 19890), ('nn1', 8190),
]


def remote_read(results, address, command, input_text=None):
    result = subprocess.run(['ssh', *shlex.split(os.environ['ANSIBLE_SSH_ARGS']),
                             'ansible@' + address, command], input=input_text, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    with (results / 'certificate-observations.log').open('a') as stream:
        stream.write(address + ': ' + command + '\n' + result.stdout + result.stderr + '\n')
    result.check_returncode()
    return result.stdout


def peer_certificate(context, address, hostname, port):
    with socket.create_connection((address, port), timeout=30) as connection:
        with context.wrap_socket(connection, server_hostname=hostname) as tls:
            return tls.getpeercert(binary_form=True)


def capture_certificates(results, stage, addresses):
    pem = remote_read(results, addresses['nn1'], 'cat /etc/hadoop/conf/ca-certificates.pem')
    authority_file = results / ('ca-' + stage + '.pem')
    authority_file.write_text(pem)
    context = ssl.create_default_context(cafile=str(authority_file))
    authorities = [hashlib.sha256(value).hexdigest() for value in context.get_ca_certs(binary_form=True)]
    connections = {}
    for hostname, port in HTTPS_ENDPOINTS:
        certificate = peer_certificate(context, addresses[hostname], hostname, port)
        public_key = subprocess.run(['openssl', 'x509', '-pubkey', '-noout'],
                                    input=ssl.DER_cert_to_PEM_cert(certificate), text=True,
                                    stdout=subprocess.PIPE, check=True).stdout
        connections[hostname + ':' + str(port)] = dict(
            certificate_sha256=hashlib.sha256(certificate).hexdigest(),
            public_key_sha256=hashlib.sha256(public_key.encode()).hexdigest())
    snapshot = dict(authorities=authorities, authority_file=str(authority_file), connections=connections)
    (results / ('certificate-' + stage + '.json')).write_text(json.dumps(snapshot, indent=2) + '\n')
    return snapshot


def truststore_certificates(results, addresses):
    stores = {}
    for hostname, address in addresses.items():
        output = remote_read(results, address,
                             'keytool -list -rfc -keystore /etc/hadoop/conf/truststore.jks',
                             os.environ['KERBEROS_TEST_PASSWORD'] + '\n')
        certificates = re.findall(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', output, re.S)
        stores[hostname] = [hashlib.sha256(ssl.PEM_cert_to_DER_cert(value)).hexdigest() for value in certificates]
    return stores

def verify_previous_ca_rejected(authority_file, addresses):
    context = ssl.create_default_context(cafile=authority_file)
    for hostname, port in HTTPS_ENDPOINTS:
        try:
            peer_certificate(context, addresses[hostname], hostname, port)
        except ssl.SSLCertVerificationError as error:
            assert error.verify_code in (19, 20, 21), error
        else:
            raise AssertionError(f'{hostname}:{port} accepted the previous CA')
