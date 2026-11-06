#!/bin/bash
set -e
source /opt/ros/humble/setup.bash
set -u
export PYTHONPATH=/tmp/exfmd-python:/repo/results/runtime-audit/deps:/repo/results/runtime-audit/deps/sumo/tools:/repo/cosimulation:${PYTHONPATH:-}
export SUMO_HOME=/repo/results/runtime-audit/deps/sumo
export PATH="$SUMO_HOME/bin:$PATH"
exec python3 "$@"
