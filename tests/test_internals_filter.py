# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import os
import pytest
import ptvsd

from ptvsd.wrapper import InternalsFilter
from ptvsd.wrapper import dont_trace_ptvsd_files

INTERNAL_DIR = os.path.dirname(os.path.abspath(ptvsd.__file__))
@pytest.mark.parametrize('path', [
    os.path.abspath(ptvsd.__file__),
    # File used by VS/VSC to launch ptvsd
    os.path.join('somepath', 'ptvsd_launcher.py'),
    # Any file under ptvsd
    os.path.join(INTERNAL_DIR, 'somefile.py'),
])
def test_internal_paths(path):
    int_filter = InternalsFilter()
    assert int_filter.is_internal_path(path)

@pytest.mark.parametrize('path', [
    __file__,
    os.path.join('somepath', 'somefile.py'),
])
def test_user_file_paths(path):
    int_filter = InternalsFilter()
    assert not int_filter.is_internal_path(path)

@pytest.mark.parametrize('path, val', [
    (os.path.join(INTERNAL_DIR, 'wrapper.py'), True),
    (os.path.join(INTERNAL_DIR, 'abcd', 'ptvsd', 'wrapper.py'), True),
    (os.path.join(INTERNAL_DIR, 'ptvsd', 'wrapper.py'), True),
    (os.path.join(INTERNAL_DIR, 'abcd', 'wrapper.py'), True),
    (os.path.join('usr', 'abcd', 'ptvsd', 'wrapper.py'), False),
    (os.path.join('C:', 'ptvsd', 'wrapper1.py'), False),
    (os.path.join('C:', 'abcd', 'ptvsd', 'ptvsd.py'), False),
    (os.path.join('usr', 'ptvsd', 'w.py'), False),
    (os.path.join('ptvsd', 'w.py'), False),
    (os.path.join('usr', 'abcd', 'ptvsd', 'tangle.py'), False),
])
def test_ptvsd_paths(path, val):
    assert val == dont_trace_ptvsd_files(os.path.normcase(path))
