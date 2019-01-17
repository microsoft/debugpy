# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import pytest

try:
    from importlib import reload
except ImportError:
    pass

import ptvsd.options
from ptvsd.__main__ import parse

from tests.helpers.pattern import ANY

EXPECTED_EXTRA = ['--']


@pytest.mark.parametrize('target_kind', ['file', 'module', 'code'])
@pytest.mark.parametrize('client', ['', 'client'])
@pytest.mark.parametrize('wait', ['', 'wait'])
@pytest.mark.parametrize('nodebug', ['', 'nodebug'])
@pytest.mark.parametrize('multiproc', ['', 'multiproc'])
@pytest.mark.parametrize('extra', ['', 'extra'])
def test_targets(target_kind, client, wait, nodebug, multiproc, extra):
    args = ['--host', 'localhost', '--port', '8888']

    if client:
        args += ['--client']

    if wait:
        args += ['--wait']

    if nodebug:
        args += ['--nodebug']

    if multiproc:
        args += ['--multiprocess']

    if target_kind == 'file':
        target = 'spam.py'
        args += [target]
    elif target_kind == 'module':
        target = 'spam'
        args += ['-m', target]
    elif target_kind == 'code':
        target = '123'
        args += ['-c', target]

    if extra:
        extra = ['ham', '--client', '--wait', '-y', 'spam', '--', '--nodebug', '--host', '--port', '-c', '--something', '-m']
        args += extra
    else:
        extra = []

    print(args)
    reload(ptvsd.options)
    rest = parse(args)
    assert list(rest) == extra
    assert vars(ptvsd.options) == ANY.dict_with({
        'target_kind': target_kind,
        'target': target,
        'host': 'localhost',
        'port': 8888,
        'no_debug': bool(nodebug),
        'wait': bool(wait),
        'multiprocess': bool(multiproc),
    })


def test_unsupported_arg():
    reload(ptvsd.options)
    with pytest.raises(Exception):
        parse([
            '--port', '8888',
            '--xyz', '123',
            'spam.py',
        ])


def test_host_required():
    reload(ptvsd.options)
    with pytest.raises(Exception):
        parse([
            '--port', '8888',
            '-m', 'spam',
        ])


def test_host_empty():
    reload(ptvsd.options)
    parse(['--host', '', '--port', '8888', 'spam.py'])
    assert ptvsd.options.host == ''


def test_port_default():
    reload(ptvsd.options)
    parse(['--host', 'localhost', 'spam.py'])
    assert ptvsd.options.port == 5678
