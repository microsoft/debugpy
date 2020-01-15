#!/bin/bash
set -ev

source activate build_env

pypy3 -m ensurepip

pypy3 -m pip install pytest
pypy3 -m pip install pytest-xdist
pypy3 -m pip install pytest-timeout
pypy3 -m pip install colorama
pypy3 -m pip install psutil
pypy3 -m pip install numpy
pypy3 -m pip install ipython
pypy3 -m pip install untangle
