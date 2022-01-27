import sys
from _pydevd_bundle.pydevd_constants import IS_PY38_OR_GREATER
import pytest

SOME_LST = ["foo", "bar"]
BAR = "bar"
FOO = "foo"
global_frame = sys._getframe()


def obtain_frame():
    yield sys._getframe()


@pytest.fixture
def disable_critical_log():
    # We want to hide the logging related to _evaluate_with_timeouts not receiving the py_db.
    from _pydev_bundle.pydev_log import log_context
    import io
    stream = io.StringIO()
    with log_context(0, stream):
        yield


def test_evaluate_expression_basic(disable_critical_log):
    from _pydevd_bundle.pydevd_vars import evaluate_expression

    def check(frame):
        evaluate_expression(None, frame, 'some_var = 1', is_exec=True)

        assert frame.f_locals['some_var'] == 1

    check(next(iter(obtain_frame())))
    assert 'some_var' not in sys._getframe().f_globals

    # as locals == globals, this will also change the current globals
    check(global_frame)
    assert 'some_var' in sys._getframe().f_globals
    del sys._getframe().f_globals['some_var']
    assert 'some_var' not in sys._getframe().f_globals


def test_evaluate_expression_1(disable_critical_log):
    from _pydevd_bundle.pydevd_vars import evaluate_expression

    def check(frame):
        eval_txt = '''
container = ["abc","efg"]
results = []
for s in container:
    result = [s[i] for i in range(3)]
    results.append(result)
'''
        evaluate_expression(None, frame, eval_txt, is_exec=True)
        assert frame.f_locals['results'] == [['a', 'b', 'c'], ['e', 'f', 'g']]
        assert frame.f_locals['s'] == "efg"

    check(next(iter(obtain_frame())))

    for varname in ['container', 'results', 's']:
        assert varname not in sys._getframe().f_globals

    check(global_frame)
    for varname in ['container', 'results', 's']:
        assert varname in sys._getframe().f_globals

    for varname in ['container', 'results', 's']:
        del sys._getframe().f_globals[varname]


def test_evaluate_expression_2(disable_critical_log):
    from _pydevd_bundle.pydevd_vars import evaluate_expression

    def check(frame):
        eval_txt = 'all((x in (BAR, FOO) for x in SOME_LST))'
        assert evaluate_expression(None, frame, eval_txt, is_exec=False)

    check(next(iter(obtain_frame())))
    check(global_frame)


def test_evaluate_expression_3(disable_critical_log):
    if not IS_PY38_OR_GREATER:
        return

    from _pydevd_bundle.pydevd_vars import evaluate_expression

    def check(frame):
        eval_txt = '''11 if (some_var := 22) else 33'''
        assert evaluate_expression(None, frame, eval_txt, is_exec=False) == 11

    check(next(iter(obtain_frame())))
    assert 'some_var' not in sys._getframe().f_globals

    # as locals == globals, this will also change the current globals
    check(global_frame)
    assert 'some_var' in sys._getframe().f_globals
    del sys._getframe().f_globals['some_var']
    assert 'some_var' not in sys._getframe().f_globals


def test_evaluate_expression_4(disable_critical_log):
    from _pydevd_bundle.pydevd_vars import evaluate_expression

    def check(frame):
        eval_txt = '''import email;email.foo_value'''
        with pytest.raises(AttributeError):
            evaluate_expression(None, frame, eval_txt, is_exec=True)
        assert 'email' in frame.f_locals

    check(next(iter(obtain_frame())))
    assert 'email' not in sys._getframe().f_globals

    # as locals == globals, this will also change the current globals
    check(global_frame)
    assert 'email' in sys._getframe().f_globals
    del sys._getframe().f_globals['email']
    assert 'email' not in sys._getframe().f_globals
