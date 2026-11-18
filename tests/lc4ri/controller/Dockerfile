FROM niicloudoperation/notebook:feature-lab
USER root
RUN python3 -m pip install --no-cache-dir netaddr pandas zk-shell \
 && command -v tree \
 && mkdir -p /home/jovyan/work /home/jovyan/.ssh \
 && chown -R 1000:100 /home/jovyan/work /home/jovyan/.ssh
USER $NB_USER
