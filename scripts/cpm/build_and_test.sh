#!/bin/bash
set -eu
mkdir -p /evidence/corrections
v=/artery/extern/vanetza
lib=/artery/build/extern/vanetza/lib
g++ -std=c++17 -O0 -g -I/repo -I"$v" -I"$v/vanetza/asn1/support" \
    /repo/tests/cpm/test_cpm.cpp -L"$lib" -Wl,-rpath,"$lib" \
    -lvanetza_asn1 -lvanetza_asn1_its_r2 -lvanetza_asn1_its -lvanetza_asn1_support \
    -o /evidence/corrections/test_cpm
/evidence/corrections/test_cpm /evidence/corrections
/evidence/decode_cpm r2 /evidence/corrections/corrected.uper /evidence/corrections/decode-after-full.txt > /evidence/corrections/decode-after-r2.json
cat /evidence/corrections/decode-after-r2.json
