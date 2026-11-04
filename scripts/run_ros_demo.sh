#!/bin/bash
set -e
source /opt/ros/humble/setup.bash
export PYTHONPATH=/tmp/exfmd-python:/repo/results/runtime-audit/deps:/repo/results/runtime-audit/deps/sumo/tools:/repo/cosimulation:$PYTHONPATH
export SUMO_HOME=/repo/results/runtime-audit/deps/sumo
export PATH=$SUMO_HOME/bin:$PATH
exec python3 /repo/scripts/run_integrated_demo.py
