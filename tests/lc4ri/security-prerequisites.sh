#!/usr/bin/env bash
# Supply external test certificates, not KDC/Hadoop installation or credentials.
set -Eeuo pipefail
for name in nn1 nn2 dn1; do
  keytool -genkeypair -alias server -keyalg RSA -keysize 2048 -validity 2 \
    -dname "CN=$name" -ext "SAN=dns:$name" -storetype JKS \
    -keystore "$private_dir/$name-keystore.jks" \
    -storepass "$KERBEROS_TEST_PASSWORD" -keypass "$KERBEROS_TEST_PASSWORD"
  keytool -exportcert -alias server -keystore "$private_dir/$name-keystore.jks" \
    -storepass "$KERBEROS_TEST_PASSWORD" -file "$private_dir/$name.crt"
done
for name in nn1 nn2 dn1; do
  keytool -importcert -noprompt -alias "$name" -file "$private_dir/$name.crt" \
    -keystore "$private_dir/truststore.jks" -storetype JKS -storepass "$KERBEROS_TEST_PASSWORD"
done
for index in "${!qemu_names[@]}"; do
  name="${qemu_names[$index]}"
  address="${qemu_addresses[$index]}"
  scp -F "$private_dir/ssh_config" "$private_dir/$name-keystore.jks" "ansible@$address:/tmp/ci-keystore.jks"
  scp -F "$private_dir/ssh_config" "$private_dir/truststore.jks" "ansible@$address:/tmp/ci-truststore.jks"
  ssh -F "$private_dir/ssh_config" "ansible@$address" \
    'sudo mkdir -p /etc/hadoop/conf; sudo install -m 0600 /tmp/ci-keystore.jks /etc/hadoop/conf/keystore.jks; sudo install -m 0644 /tmp/ci-truststore.jks /etc/hadoop/conf/truststore.jks; rm /tmp/ci-keystore.jks /tmp/ci-truststore.jks'
done
