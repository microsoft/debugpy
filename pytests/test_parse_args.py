import pytest
from ptvsd.socket import Address
from ptvsd.__main__ import parse_args

EXPECTED_EXTRA = ['--']

def test_host_required():
    with pytest.raises(SystemExit):
        parse_args([
            'eggs',
            '--port', '8888',
            '-m', 'spam',
        ])

def test_module_server():
    args, extra = parse_args([
        'eggs',
        '--host', '10.0.1.1',
        '--port', '8888',
        '-m', 'spam',
    ])

    assert vars(args) == {
        'kind': 'module',
        'name': 'spam',
        'address': Address.as_server('10.0.1.1', 8888),
        'nodebug': False,
        'single_session': False,
        'wait': False,
        'multiprocess': False,
    }
    assert extra == EXPECTED_EXTRA

def test_module_nodebug():
    args, extra = parse_args([
        'eggs',
        '--nodebug',
        '--client',
        '--host', 'localhost',
        '--port', '8888',
        '-m', 'spam',
    ])

    assert vars(args) == {
        'kind': 'module',
        'name': 'spam',
        'address': Address.as_client('localhost', 8888),
        'nodebug': True,
        'single_session': False,
        'wait': False,
        'multiprocess': False,
    }
    assert extra == EXPECTED_EXTRA

def test_script():
    args, extra = parse_args([
        'eggs',
        '--host', 'localhost',
        '--port', '8888',
        'spam.py',
    ])

    assert vars(args) == {
        'kind': 'script',
        'name': 'spam.py',
        'address': Address.as_server('localhost', 8888),
        'nodebug': False,
        'single_session': False,
        'wait': False,
        'multiprocess': False,
    }
    assert extra == EXPECTED_EXTRA

def test_script_server():
    args, extra = parse_args([
        'eggs',
        '--host', '10.0.1.1',
        '--port', '8888',
        'spam.py',
    ])

    assert vars(args) == {
        'kind': 'script',
        'name': 'spam.py',
        'address': Address.as_server('10.0.1.1', 8888),
        'nodebug': False,
        'single_session': False,
        'wait': False,
        'multiprocess': False,
    }
    assert extra == EXPECTED_EXTRA

def test_script_nodebug():
    args, extra = parse_args([
        'eggs',
        '--nodebug',
        '--client',
        '--host', 'localhost',
        '--port', '8888',
        'spam.py',
    ])

    assert vars(args) == {
        'kind': 'script',
        'name': 'spam.py',
        'address': Address.as_client('localhost', 8888),
        'nodebug': True,
        'single_session': False,
        'wait': False,
        'multiprocess': False,
    }
    assert extra == EXPECTED_EXTRA

def test_remote():
    args, extra = parse_args([
        'eggs',
        '--client',
        '--host', '1.2.3.4',
        '--port', '8888',
        'spam.py',
    ])

    assert vars(args) == {
        'kind': 'script',
        'name': 'spam.py',
        'address': Address.as_client('1.2.3.4', 8888),
        'nodebug': False,
        'single_session': False,
        'wait': False,
        'multiprocess': False,
    }
    assert extra == EXPECTED_EXTRA

def test_remote_localhost():
    args, extra = parse_args([
        'eggs',
        '--client',
        '--host', 'localhost',
        '--port', '8888',
        'spam.py',
    ])

    assert vars(args) == {
        'kind': 'script',
        'name': 'spam.py',
        'address': Address.as_client('localhost', 8888),
        'nodebug': False,
        'single_session': False,
        'wait': False,
        'multiprocess': False,
    }
    assert extra == EXPECTED_EXTRA

def test_remote_nodebug():
    args, extra = parse_args([
        'eggs',
        '--nodebug',
        '--client',
        '--host', '1.2.3.4',
        '--port', '8888',
        'spam.py',
    ])

    assert vars(args) == {
        'kind': 'script',
        'name': 'spam.py',
        'address': Address.as_client('1.2.3.4', 8888),
        'nodebug': True,
        'single_session': False,
        'wait': False,
        'multiprocess': False,
    }
    assert extra == EXPECTED_EXTRA

def test_remote_single_session():
    args, extra = parse_args([
        'eggs',
        '--single-session',
        '--host', 'localhost',
        '--port', '8888',
        'spam.py',
    ])

    assert vars(args) == {
        'kind': 'script',
        'name': 'spam.py',
        'address': Address.as_server('localhost', 8888),
        'nodebug': False,
        'single_session': True,
        'wait': False,
        'multiprocess': False,
    }
    assert extra == EXPECTED_EXTRA

def test_local_single_session():
    args, extra = parse_args([
        'eggs',
        '--single-session',
        '--host', '1.2.3.4',
        '--port', '8888',
        'spam.py',
    ])

    assert vars(args) == {
        'kind': 'script',
        'name': 'spam.py',
        'address': Address.as_server('1.2.3.4', 8888),
        'nodebug': False,
        'single_session': True,
        'wait': False,
        'multiprocess': False,
    }
    assert extra == EXPECTED_EXTRA

def test_remote_wait():
    args, extra = parse_args([
        'eggs',
        '--client',
        '--host', '1.2.3.4',
        '--port', '8888',
        '--wait',
        'spam.py',
    ])

    assert vars(args) == {
        'kind': 'script',
        'name': 'spam.py',
        'address': Address.as_client('1.2.3.4', 8888),
        'nodebug': False,
        'single_session': False,
        'wait': True,
        'multiprocess': False,
    }
    assert extra == EXPECTED_EXTRA

def test_extra():
    args, extra = parse_args([
        'eggs',
        '--DEBUG',
        '--host', 'localhost',
        '--port', '8888',
        '--vm_type', '???',
        'spam.py',
        '--xyz', '123',
        'abc',
        '--cmd-line',
        '--',
        'foo',
        '--server',
        '--bar'
    ])

    assert vars(args) == {
        'kind': 'script',
        'name': 'spam.py',
        'address': Address.as_server('localhost', 8888),
        'nodebug': False,
        'single_session': False,
        'wait': False,
        'multiprocess': False,
    }
    assert extra == [
        '--DEBUG',
        '--vm_type', '???',
        '--',  # Expected pydevd defaults separator
        '--xyz', '123',
        'abc',
        '--cmd-line',
        'foo',
        '--server',
        '--bar',
    ]

def test_extra_nodebug():
    args, extra = parse_args([
        'eggs',
        '--DEBUG',
        '--nodebug',
        '--client',
        '--host', 'localhost',
        '--port', '8888',
        '--vm_type', '???',
        'spam.py',
        '--xyz', '123',
        'abc',
        '--cmd-line',
        '--',
        'foo',
        '--server',
        '--bar'
    ])

    assert vars(args) == {
        'kind': 'script',
        'name': 'spam.py',
        'address': Address.as_client('localhost', 8888),
        'nodebug': True,
        'single_session': False,
        'wait': False,
        'multiprocess': False,
    }
    assert extra == [
        '--DEBUG',
        '--vm_type', '???',
        '--',  # Expected pydevd defaults separator
        '--xyz', '123',
        'abc',
        '--cmd-line',
        'foo',
        '--server',
        '--bar',
    ]

def test_empty_host():
    args, extra = parse_args([
        'eggs',
        '--host', '',
        '--port', '8888',
        'spam.py',
    ])

    assert vars(args) == {
        'kind': 'script',
        'name': 'spam.py',
        'address': Address.as_server('', 8888),
        'nodebug': False,
        'single_session': False,
        'wait': False,
        'multiprocess': False,
    }
    assert extra == EXPECTED_EXTRA

def test_unsupported_arg():
    with pytest.raises(SystemExit):
        parse_args([
            'eggs',
            '--port', '8888',
            '--xyz', '123',
            'spam.py',
        ])

def test_pseudo_backward_compatibility():
    args, extra = parse_args([
        'eggs',
        '--host', 'localhost',
        '--port', '8888',
        '--module',
        '--file', 'spam',
    ])

    assert vars(args) == {
        'kind': 'script',
        'name': 'spam',
        'address': Address.as_server('localhost', 8888),
        'nodebug': False,
        'single_session': False,
        'wait': False,
        'multiprocess': False,
    }
    assert extra == ['--module'] + EXPECTED_EXTRA

def test_pseudo_backward_compatibility_nodebug():
    args, extra = parse_args([
        'eggs',
        '--nodebug',
        '--client',
        '--host', 'localhost',
        '--port', '8888',
        '--module',
        '--file', 'spam',
    ])

    assert vars(args) == {
        'kind': 'script',
        'name': 'spam',
        'address': Address.as_client('localhost', 8888),
        'nodebug': True,
        'single_session': False,
        'wait': False,
        'multiprocess': False,
    }
    assert extra == ['--module'] + EXPECTED_EXTRA
