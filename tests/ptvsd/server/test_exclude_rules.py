# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import pytest

from tests import code, debug, log, test_data
from tests.debug import targets
from tests.patterns import some


@pytest.fixture(params=targets.all_named)
def target(request):
    return request.param


@pytest.mark.parametrize("scenario", ["exclude_by_name", "exclude_by_dir"])
@pytest.mark.parametrize("exc_type", ["RuntimeError", "SystemExit"])
def test_exceptions_and_exclude_rules(pyfile, target, run, scenario, exc_type):
    if exc_type == "RuntimeError":

        @pyfile
        def code_to_debug():
            import debug_me  # noqa

            raise RuntimeError("unhandled error")  # @raise_line

    elif exc_type == "SystemExit":

        @pyfile
        def code_to_debug():
            import debug_me  # noqa
            import sys

            sys.exit(1)  # @raise_line

    else:
        pytest.fail(exc_type)

    if scenario == "exclude_by_name":
        rules = [{"path": "**/" + code_to_debug.basename, "include": False}]
    elif scenario == "exclude_by_dir":
        rules = [{"path": code_to_debug.dirname, "include": False}]
    else:
        pytest.fail(scenario)
    log.info("Rules: {0!j}", rules)

    with debug.Session() as session:
        session.expected_exit_code = some.int
        session.config["rules"] = rules

        with run(session, target(code_to_debug)):
            session.request(
                "setExceptionBreakpoints", {"filters": ["raised", "uncaught"]}
            )

        # No exceptions should be seen.


@pytest.mark.parametrize("scenario", ["exclude_code_to_debug", "exclude_callback_dir"])
def test_exceptions_and_partial_exclude_rules(pyfile, target, run, scenario):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel
        import sys

        call_me_back_dir = backchannel.receive()
        sys.path.insert(0, call_me_back_dir)

        import call_me_back

        def call_func():
            raise RuntimeError("unhandled error")  # @raise

        call_me_back.call_me_back(call_func)  # @call_me_back
        print("done")

    call_me_back_dir = test_data / "call_me_back"
    call_me_back_py = call_me_back_dir / "call_me_back.py"
    call_me_back_py.lines = code.get_marked_line_numbers(call_me_back_py)

    if scenario == "exclude_code_to_debug":
        rules = [{"path": "**/" + code_to_debug.basename, "include": False}]
    elif scenario == "exclude_callback_dir":
        rules = [{"path": call_me_back_dir, "include": False}]
    else:
        pytest.fail(scenario)
    log.info("Rules: {0!j}", rules)

    with debug.Session() as session:
        session.expected_exit_code = some.int
        session.config["rules"] = rules

        backchannel = session.open_backchannel()
        with run(session, target(code_to_debug)):
            session.request(
                "setExceptionBreakpoints", {"filters": ["raised", "uncaught"]}
            )

        backchannel.send(call_me_back_dir)

        if scenario == "exclude_code_to_debug":
            # Stop at handled exception, with code_to_debug.py excluded.
            #
            # Since the module raising the exception is excluded, it must not stop at
            # @raise, but rather at @callback (i.e. the closest non-excluded frame).

            stop = session.wait_for_stop(
                "exception",
                expected_frames=[
                    some.dap.frame(
                        some.dap.source(call_me_back_py),
                        line=call_me_back_py.lines["callback"],
                    )
                ],
            )
            assert stop.frames != some.list.containing(
                [some.dap.frame(some.dap.source(code_to_debug), line=some.int)]
            )

            # As exception unwinds the stack, we shouldn't stop at @call_me_back,
            # since that line is in the excluded file. Furthermore, although the
            # exception is unhandled, we shouldn't get a stop for that, either,
            # because the exception is last seen in an excluded file.
            session.request_continue()

        elif scenario == "exclude_callback_dir":
            # Stop at handled exception, with call_me_back.py excluded.
            #
            # Since the module raising the exception is not excluded, it must stop at
            # @raise.

            stop = session.wait_for_stop(
                "exception",
                expected_frames=[
                    some.dap.frame(
                        some.dap.source(code_to_debug),
                        name="call_func",
                        line=code_to_debug.lines["raise"],
                    ),
                    some.dap.frame(
                        some.dap.source(code_to_debug),
                        name="<module>",
                        line=code_to_debug.lines["call_me_back"],
                    ),
                ],
            )
            assert stop.frames != some.list.containing(
                [some.dap.frame(some.dap.source(call_me_back_py), line=some.int)]
            )

            session.request_continue()

            # As exception unwinds the stack, it must not stop at @callback, since that
            # line is in the excluded file. However, it must stop at @call_me_back.
            stop = session.wait_for_stop(
                "exception",
                expected_frames=[
                    some.dap.frame(
                        some.dap.source(code_to_debug),
                        name="<module>",
                        line=code_to_debug.lines["call_me_back"],
                    )
                ],
            )
            assert stop.frames != some.list.containing(
                [some.dap.frame(some.dap.source(call_me_back_py), line=some.int)]
            )

            session.request_continue()

            # Now the exception is unhandled, and should be reported as such.
            stop = session.wait_for_stop(
                "exception",
                expected_frames=[
                    some.dap.frame(
                        some.dap.source(code_to_debug),
                        name="call_func",
                        line=code_to_debug.lines["raise"],
                    ),
                    some.dap.frame(
                        some.dap.source(code_to_debug),
                        name="<module>",
                        line=code_to_debug.lines["call_me_back"],
                    ),
                ],
            )
            assert stop.frames != some.list.containing(
                [some.dap.frame(some.dap.source(call_me_back_py), line=some.int)]
            )

            # Let the process crash due to unhandled exception.
            session.request_continue()

        else:
            pytest.fail(scenario)
