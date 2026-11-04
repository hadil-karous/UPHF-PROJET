$ErrorActionPreference = 'Stop'
# Container data VHDX was verified on D:\DOCKER_DATA\DockerDesktopWSL\disk.
docker exec exfmd-carla /opt/python310/bin/python3.10 -m pip install --no-cache-dir --target /tmp/exfmd-deps eclipse-sumo==1.19.0 numpy==1.26.4 PyYAML==6.0.2 lxml==5.3.0
if ($LASTEXITCODE) { throw 'Dependency setup failed' }
