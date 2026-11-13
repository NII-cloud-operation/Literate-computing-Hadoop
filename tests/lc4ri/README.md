# Notebook integration tests

The `basic` and `security` jobs operate the scenario in [scenario.py](scenario.py)
on disposable QEMU VMs. The scenario lists the notebooks in execution order and
supplies operator inputs. Each notebook runs all nonempty code cells. Cell errors
fail the job, and service validation follows the notebook procedures.

The controller uses `niicloudoperation/notebook:feature-lab` and each notebook's declared
kernel. Its image digest and installed package versions are saved with the
results. Software archives and checksums come from the repository's deployment
defaults and are served through a local mirror backed by Apache Archive.
The [guest image](guests/guest-image.env) supplies the cgroups v1 environment
expected by the deployment roles. The security fixture supplies test TLS files;
Kerberos service and client prerequisites remain part of the deployment procedure.

Run on a disposable x86-64 Linux host with Docker, QEMU, cloud-image-utils,
SSH and sudo, using the prerequisites in
[the workflow](../../.github/workflows/notebook-integration.yml):

```bash
python3 -m pip install -r tests/lc4ri/requirements.txt
python3 -m playwright install --with-deps chromium
HADOOP_SECURITY_MODE=simple bash tests/lc4ri/run.sh
HADOOP_SECURITY_MODE=kerberos bash tests/lc4ri/run.sh
```

Results in `test-results/notebook-integration` include working copies, cell
execution records, input edits, screenshots, browser traces and videos, runtime
versions and VM logs. Actions uploads full evidence and a smaller copy of the
JSON, notebooks and screenshots for each variant.

Browser and QEMU helpers are adapted from
[CoursewareHub-LC_deploy](https://github.com/yacchin1205/CoursewareHub-LC_deploy/pull/1).
