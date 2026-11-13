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
