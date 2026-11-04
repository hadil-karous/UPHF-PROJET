#!/bin/bash
set -e
source /opt/ros/humble/setup.bash
export PYTHONPATH=/tmp/exfmd-python:$PYTHONPATH
if ! python3 -c 'import carla' >/dev/null 2>&1; then
 python3 -m pip install --no-cache-dir --target /tmp/exfmd-python /repo/results/runtime-audit/carla-0.9.16-cp310-cp310-manylinux_2_31_x86_64.whl
fi
