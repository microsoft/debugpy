#!/bin/bash
set -ex

SOURCE_ROOT=$1
DEST=$2
PYABI=$3

# Compile
for PYBIN in /opt/python/${PYABI}*/bin; do
    "${PYBIN}/pip" install -U cython
    "${PYBIN}/python" "${SOURCE_ROOT}/setup.py" build bdist_wheel -d "${DEST}" --abi
done
