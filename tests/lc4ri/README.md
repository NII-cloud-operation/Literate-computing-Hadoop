# Notebook integration tests

The `basic` and `security` jobs operate the scenario in [scenario.py](scenario.py)
on disposable QEMU VMs. The scenario lists the notebooks in execution order and
supplies operator inputs. Each notebook runs all nonempty code cells. Cell errors
fail the job, and service validation follows the notebook procedures.
T12c creates an HBase table, writes the Iris dataset, reads it back, and deletes
the table. The security variant performs these operations as the HBase administrator.

The controller uses `niicloudoperation/notebook:feature-lab` and each notebook's declared
kernel. Its image digest and installed package versions are saved with the
results. Software archives and checksums come from the repository's deployment
defaults and are served through a local mirror backed by Apache Archive.
Archived packages use parallel range downloads followed by SHA-512 verification.
The [guest image](guests/guest-image.env) supplies the cgroups v1 environment
expected by the deployment roles. The security fixture supplies test TLS files;
Kerberos service and client prerequisites remain part of the deployment procedure.

Run on a disposable x86-64 Linux host with Docker, QEMU, cloud-image-utils,
SSH, sudo, FFmpeg, DejaVu and Noto CJK fonts, using the prerequisites in
[the workflow](../../.github/workflows/notebook-integration.yml):

```bash
python3 -m pip install -r tests/lc4ri/requirements.txt
python3 -m playwright install --with-deps chromium
install -Dm644 tests/lc4ri/fonts.conf ~/.config/fontconfig/fonts.conf
HADOOP_SECURITY_MODE=simple bash tests/lc4ri/run.sh
HADOOP_SECURITY_MODE=kerberos bash tests/lc4ri/run.sh
```

Results in `test-results/notebook-integration` are uploaded separately for each
variant:

| Artifact | Contents |
| --- | --- |
| `notebook-results-*` | Executed notebooks, JSON reports, screenshots and the video manifest |
| `notebook-logs-*` | Service logs, runtime diagnostics, inventory and group variables |
| `notebook-trace-*` | Browser trace |
| `notebook-video-*-D00` (and other notebook IDs) | Notebook chapter MP4 and its source page recordings |
| `notebook-video-*-combined` | Combined MP4 in notebook execution order |

Each chapter starts with a two-second notebook title. File-editor operations
appear where they occurred in the notebook procedure; background page recordings
are not played simultaneously or appended out of order. Playback is at normal
speed. Original page recordings remain available in the per-notebook artifacts.

On failure, each guest's `/var/log/hadoop-yarn/userlogs` directory is archived
before cleanup and included as `*-yarn-userlogs.tar.gz` in the logs artifact.
Video rendering also runs after a notebook failure, preserving the attempted
procedure for review.

Browser and QEMU helpers are adapted from
[CoursewareHub-LC_deploy](https://github.com/yacchin1205/CoursewareHub-LC_deploy/pull/1).


The `upgrade-3.2.2-3.3.6-basic` and `upgrade-3.2.2-3.3.6-security` matrices explicitly
select the initial Hadoop version and checksum, deploy it with D12,
then execute the O12e–O12k procedures: prepare and pause application use, upgrade
ZooKeeper one peer at a time, roll the NameNodes, switch each host's shared Hadoop
release, upgrade HBase/Spark, verify data and finalize, then update OS-provided
Java/cgroups/Kerberos packages and restart their consumers one host at a time. jsvc is rebuilt and switched
with each Hadoop host. OS packages whose candidate equals the installed version
remain unchanged; this does not test an OS distribution migration.

`HADOOP_UPGRADE_FROM_VERSION` and `HADOOP_UPGRADE_FROM_CHECKSUM` select the initial
Hadoop release independently of the playbook defaults. `HADOOP_UPGRADE_TO_VERSION`
must match the target version in O12e. The matrix names and artifact names identify
both versions.

Each repeated host procedure has its own working notebook and coverage. The test
enters operator inputs and edits group_vars through the notebook UI. Every nonempty
code cell runs. Existing service definitions and shared release pointers are retained.
New playbooks stage packages and switch the existing release pointers.

The scenario checks HDFS writes and reads with the old-version client before the
upgrade and after each notebook execution. Each check must succeed before the
next notebook runs. Readiness queries may be repeated while following the notebook
procedure. Output assertions run after notebook completion and require the matching
code cells to exist.
HBase is tested for pre-upgrade data retention and new writes. MapReduce and Spark
run real YARN jobs after the shared Hadoop release changes; T12a and T12d run again
after platform service restarts. Full outputs, working notebooks and source hashes are saved.
