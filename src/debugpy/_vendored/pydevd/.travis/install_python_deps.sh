#!/bin/bash
set -ev

if [[ ("$PYDEVD_USE_CONDA" != "NO" && "$PYDEVD_PYTHON_VERSION" != "2.6") ]]; then
    source activate build_env
    conda install --yes numpy ipython pytest cython psutil
fi

if [ "$PYDEVD_PYTHON_VERSION" = "2.6" ]; then
    source activate build_env
    conda install --yes numpy ipython pytest cython psutil pyqt=4 py=1.4.30
    pip install pympler==0.5
    pip install pathlib2
    # Django 1.7 does not support Python 2.6
else
    # pytest-xdist not available for python 2.6
    pip install pytest-xdist
    pip install pympler
fi

if [ "$PYDEVD_PYTHON_VERSION" = "2.7" ]; then
    conda install --yes pyqt=4 gevent
    pip install "django>=1.7,<1.8"
    pip install pathlib2

fi

if [ "$PYDEVD_PYTHON_VERSION" = "3.5" ]; then
    conda install --yes pyqt=5
    pip install "django>=2.1,<2.2"
fi

if [ "$PYDEVD_PYTHON_VERSION" = "3.6" ]; then
    conda install --yes pyqt=5 gevent
    pip install "django>=2.2,<2.3"
    pip install trio
fi

if [ "$PYDEVD_PYTHON_VERSION" = "3.7" ]; then
    conda install --yes pyqt=5 matplotlib gevent
    # Note: track the latest web framework versions.
    pip install "django"
    pip install "cherrypy"
    pip install trio
fi

if [[ ("$PYDEVD_PYTHON_VERSION" = "3.8") ]]; then
    pip install "pytest"
    pip install "cython"
    pip install "psutil"
    pip install "numpy"
    pip install trio
    pip install gevent

    # Note: track the latest web framework versions.
    pip install "django"
    pip install "cherrypy"
fi

if [[ ("$PYDEVD_PYTHON_VERSION" = "3.9") ]]; then
    pip install "pytest"
    pip install "cython"
    pip install "psutil"
    pip install "numpy"
    pip install trio
    # pip install gevent -- not compatible with 3.9 for now.

    # Note: track the latest web framework versions.
    pip install "django"
    pip install "cherrypy"
fi

pip install untangle
pip install scapy==2.4.0