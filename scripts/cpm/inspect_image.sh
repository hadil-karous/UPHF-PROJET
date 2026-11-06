#!/bin/bash
set -eu
grep -n -A30 -B8 'PerceivedObject ::=' /artery/extern/vanetza/asn1/release2/TS102894-2v221-CDD.asn | head -80
grep -n -A45 -B8 'CartesianPosition3dWithConfidence ::=' /artery/extern/vanetza/asn1/release2/TS102894-2v221-CDD.asn | head -85
find /artery/build/src/artery -maxdepth 4 -name flags.make -print
cat /artery/build/src/artery/application/CMakeFiles/application.dir/flags.make 2>/dev/null || true
ls /artery/build/src/artery/application
g++ -std=c++14 -I/artery/extern/vanetza -I/artery/extern/vanetza/vanetza/asn1/support /repo/scripts/cpm/decode_cpm.cpp -L/artery/build/extern/vanetza/lib -Wl,-rpath,/artery/build/extern/vanetza/lib -lvanetza_asn1 -lvanetza_asn1_its_r2 -lvanetza_asn1_its -lvanetza_asn1_support -o /evidence/decode_cpm
/evidence/decode_cpm r2 /evidence/cpm-first-application.uper /evidence/decode-before-full.txt > /evidence/decode-before-r2.json
/evidence/decode_cpm legacy /evidence/cpm-first-application.uper > /evidence/decode-before-legacy.json || test "$?" = 1
cat /evidence/decode-before-r2.json /evidence/decode-before-legacy.json
