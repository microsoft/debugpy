#!/usr/bin/env python

# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

import sys
from setuptools import setup

setup(name='ptvsd',
      version='4.0.0a1',
      description='Visual Studio remote debugging server for Python',
      license='MIT',
      author='Microsoft Corporation',
      author_email='ptvshelp@microsoft.com',
      url='https://aka.ms/ptvs',
      classifiers=[
        'Development Status :: 3 - Alpha',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License'],
      packages=['ptvsd'],
      install_requires=['untangle', 'pydevd>=1.1.1']
     )
