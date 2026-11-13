#!/usr/bin/env bash
set -Eeuo pipefail
result_dir="${GITHUB_WORKSPACE:-$PWD}/test-results/notebook-integration"
mkdir -p "$result_dir"
exec > >(tee "$result_dir/run.log") 2>&1
export HADOOP_SECURITY_MODE="${HADOOP_SECURITY_MODE:-simple}"
source tests/lc4ri/guests/qemu-guests.sh
bridge=hdfs-e2e-br0
subnet=172.29.88.0/24
gateway=172.29.88.1
controller=hdfs-lc4ri-controller
mirror_pid=''
cleanup() {
  result=$?
  trap - EXIT
  set +e
  docker logs "$controller" > "$result_dir/controller.log" 2>&1
  docker cp "$controller:/home/jovyan/work/.log" "$result_dir/lc-logs"
  docker cp "$controller:/home/jovyan/work/ansible.log" "$result_dir/ansible.log"
  docker cp "$controller:/home/jovyan/work/inventory" "$result_dir/"
  docker cp "$controller:/home/jovyan/work/group_vars" "$result_dir/"
  for address in "${qemu_addresses[@]}"; do
    timeout 20s ssh -F "$private_dir/ssh_config" "ansible@$address" \
      'sudo journalctl --no-pager; sudo cat /var/log/hadoop-hdfs/*.log /var/log/zookeeper/* /var/log/hadoop-yarn/*.log /var/log/hadoop-mapreduce/*.log /var/log/hbase/* /var/log/spark/*; sudo systemctl --no-pager --full status hadoop-yarn-resourcemanager hadoop-yarn-nodemanager hbase-master hbase-regionserver spark-history-server; free -m' \
      > "$result_dir/$address-services.log" 2>&1
    if (( result != 0 )); then
      cat "$result_dir/$address-services.log"
    fi
  done
  docker rm -f "$controller"
  [[ -z "$mirror_pid" ]] || kill "$mirror_pid"
  qemu_host_diagnostics
  qemu_cleanup
  sudo chown -R "$(id -u):$(id -g)" "$result_dir"
  exit "$result"
}
trap cleanup EXIT
qemu_boot_guests 'nn1:172.29.88.10:6144:20G' 'nn2:172.29.88.11:6144:20G' 'dn1:172.29.88.12:4096:20G'
if [[ "${HADOOP_SECURITY_MODE:-simple}" == kerberos ]]; then
  export KERBEROS_TEST_PASSWORD
  KERBEROS_TEST_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
  source tests/lc4ri/security-prerequisites.sh
fi
# Supply D12's documented OS/network/storage prerequisites, never install Hadoop here.
for address in "${qemu_addresses[@]}"; do
  ssh -F "$private_dir/ssh_config" "ansible@$address" \
    'set -e; sudo apt-get update && sudo apt-get install -y python3 acl rsyslog tree lsb-release wget; sudo mkdir -p /hadoop/data /hadoop/data01; sudo chmod 0755 /hadoop /hadoop/data /hadoop/data01; timedatectl status; cat /etc/hosts'
done
# A byte-identical local download mirror avoids fetching the 377 MiB tarball per VM.
package_cache="${HDFS_E2E_PACKAGE_CACHE:-$private_dir/packages}"
mkdir -p "$package_cache"
python3 tests/lc4ri/packages.py "$package_cache" "$result_dir"
python3 -m http.server 18555 --bind "$gateway" --directory "$package_cache" > "$result_dir/mirror.log" 2>&1 &
mirror_pid=$!
# The D12 clone cell will clone this checked-out revision.
git clone --no-hardlinks --bare "$PWD" "$private_dir/source.git"
chmod -R a+rX "$private_dir/source.git"
docker buildx build --pull --load --metadata-file "$result_dir/controller-image.json" -t hdfs-lc4ri-controller tests/lc4ri/controller
export LC4RI_TEST_TOKEN
LC4RI_TEST_TOKEN=$(python3 -c 'import secrets; print(secrets.token_hex(24))')
git rev-parse HEAD > "$result_dir/tested-revision.txt"
docker run -d --name "$controller" --network host \
  -v "$private_dir/source.git:/opt/test-source.git:ro" \
  -e ANSIBLE_CONFIG=/home/jovyan/work/ansible.cfg \
  -e ANSIBLE_NOCOLOR=1 \
  hdfs-lc4ri-controller start-notebook.sh \
  --ServerApp.ip=0.0.0.0 --ServerApp.port=18888 --ServerApp.token="$LC4RI_TEST_TOKEN" \
  --ServerApp.root_dir=/home/jovyan/work --ServerApp.default_url=/lab --LabApp.expose_app_in_browser=True
docker cp "$private_dir/id_ed25519" "$controller:/home/jovyan/.ssh/id_rsa"
docker cp "$private_dir/id_ed25519.pub" "$controller:/home/jovyan/.ssh/id_rsa.pub"
docker cp "$private_dir/known_hosts" "$controller:/home/jovyan/.ssh/known_hosts"
docker cp scripts "$controller:/home/jovyan/work/scripts"
docker cp hosts.csv "$controller:/home/jovyan/work/hosts.csv"
docker exec "$controller" git config --global \
  url.file:///opt/test-source.git.insteadOf https://github.com/NII-cloud-operation/Literate-computing-Hadoop.git
docker exec -u root "$controller" sh -c 'chmod 0600 /home/jovyan/.ssh/*; chmod 0644 /home/jovyan/.ssh/*.pub; chown -R 1000:100 /home/jovyan/work /home/jovyan/.ssh; printf "Host *\n  BatchMode yes\n  StrictHostKeyChecking yes\n  IdentitiesOnly yes\n  IdentityFile ~/.ssh/id_rsa\n" > /home/jovyan/.ssh/config; chown 1000:100 /home/jovyan/.ssh/config; chmod 0600 /home/jovyan/.ssh/config'
docker exec "$controller" python3 -m pip list --format=json > "$result_dir/controller-packages.json"
python3 -m pip list --format=json > "$result_dir/runner-packages.json"
curl --fail --retry 60 --retry-connrefused --retry-delay 1 --retry-max-time 120 --max-time 5 \
  -H "Authorization: token $LC4RI_TEST_TOKEN" http://127.0.0.1:18888/api/status > "$result_dir/controller-status.json"
python3 tests/lc4ri/notebook_ui.py --result-dir "$result_dir"
