import threading

from _pydevd_bundle.pydevd_comm import pydevd_find_thread_by_id
from _pydevd_bundle.pydevd_utils import convert_dap_log_message_to_expression
from tests_python.debug_constants import IS_PY26, IS_PY3K


def test_is_main_thread():
    from _pydevd_bundle.pydevd_utils import is_current_thread_main_thread
    assert is_current_thread_main_thread()

    class NonMainThread(threading.Thread):

        def run(self):
            self.is_main_thread = is_current_thread_main_thread()

    non_main_thread = NonMainThread()
    non_main_thread.start()
    non_main_thread.join()
    assert not non_main_thread.is_main_thread


def test_find_thread():
    from _pydevd_bundle.pydevd_constants import get_current_thread_id
    assert pydevd_find_thread_by_id('123') is None

    assert pydevd_find_thread_by_id(
        get_current_thread_id(threading.current_thread())) is threading.current_thread()


def check_dap_log_message(log_message, expected, evaluated, eval_locals=None):
    ret = convert_dap_log_message_to_expression(log_message)
    assert ret == expected
    assert (eval(ret, eval_locals)) == evaluated
    return ret


def test_convert_dap_log_message_to_expression():
    assert check_dap_log_message(
        'a',
        "'a'",
        'a',
    )
    assert check_dap_log_message(
        'a {a}',
        "'a %s' % (a,)",
        'a value',
        {'a': 'value'}
    )
    assert check_dap_log_message(
        'a {1}',
        "'a %s' % (1,)",
        'a 1'
    )
    assert check_dap_log_message(
        'a {  }',
        "'a '",
        'a '
    )
    assert check_dap_log_message(
        'a {1} {2}',
        "'a %s %s' % (1, 2,)",
        'a 1 2',
    )
    assert check_dap_log_message(
        'a {{22:22}} {2}',
        "'a %s %s' % ({22:22}, 2,)",
        'a {22: 22} 2'
    )
    assert check_dap_log_message(
        'a {(22,33)}} {2}',
        "'a %s} %s' % ((22,33), 2,)",
        'a (22, 33)} 2'
    )

    if not IS_PY26:
        # Note: set literal not valid for Python 2.6.
        assert check_dap_log_message(
            'a {{1: {1}}}',
            "'a %s' % ({1: {1}},)",
            'a {1: {1}}' if IS_PY3K else 'a {1: set([1])}',
        )

    # Error condition.
    assert check_dap_log_message(
        'a {{22:22} {2}',
        "'Unbalanced braces in: a {{22:22} {2}'",
        'Unbalanced braces in: a {{22:22} {2}'
    )

