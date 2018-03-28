#!/usr/bin/env python

# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import os
import os.path
import subprocess
import sys

from setuptools import setup


if not os.getenv('SKIP_CYTHON_BUILD'):
    print('Compiling extension modules (set SKIP_CYTHON_BUILD=1 to omit)')
    subprocess.call(
        [sys.executable, 'ptvsd/pydevd/setup_cython.py', 'build_ext', '-i'])

ROOT = os.path.dirname(os.path.abspath(__file__))


# Add pydevd files as data files for this package. They are not treated
# as a package of their own, because we don't actually want to provide
# pydevd - just use our own copy internally.
def get_pydevd_package_data():
    ptvsd_prefix = os.path.join(ROOT, 'ptvsd')
    pydevd_prefix = os.path.join(ptvsd_prefix, 'pydevd')
    for root, dirs, files in os.walk(pydevd_prefix):
        # From the root of pydevd repo, we want only scripts and
        # subdirectories that constitute the package itself (not helper
        # scripts, tests etc). But when walking down into those
        # subdirectories, we want everything below.
        if os.path.normcase(root) == os.path.normcase(pydevd_prefix):
            dirs[:] = [d
                       for d in dirs
                       if d.startswith('pydev') or d.startswith('_pydev')]
            files[:] = [f
                        for f in files
                        if f.endswith('.py') and (f in ['setup_cython.py'] or 'pydev' in f)]  # noqa
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for f in files:
            yield os.path.join(root[len(ptvsd_prefix) + 1:], f)


PACKAGE_DATA = {
    'ptvsd': (list(get_pydevd_package_data()) +
        ['ThirdPartyNotices.txt'] +
        ['dummy.txt'] if sys.version_info < (3,) else []
    )
}

setup(
    name='ptvsd',
    version='4.0.0a5',
    description='Remote debugging server for Python support in Visual Studio and Visual Studio Code', # noqa
    long_description=open('DESCRIPTION.md').read(),
    long_description_content_type='text/markdown',
    license='MIT',
    author='Microsoft Corporation',
    author_email='ptvshelp@microsoft.com',
    url='https://aka.ms/ptvs',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
    ],
    packages=['ptvsd'],
    package_data=PACKAGE_DATA,
)
