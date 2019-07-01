# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import os.path
import pytest

from tests import debug, test_data
from tests.patterns import some


@pytest.mark.parametrize("scenario", ["exclude_by_name", "exclude_by_dir"])
@pytest.mark.parametrize("exception_type", ["RuntimeError", "SysExit"])
def test_exceptions_and_exclude_rules(
    pyfile, start_method, run_as, scenario, exception_type
):

    if exception_type == "RuntimeError":

        @pyfile
        def code_to_debug():
            import debug_me  # noqa

            raise RuntimeError("unhandled error")  # @raise_line

    elif exception_type == "SysExit":

        @pyfile
        def code_to_debug():
            import debug_me  # noqa
            import sys

            sys.exit(1)  # @raise_line

    else:
        raise AssertionError("Unexpected exception_type: %s" % (exception_type,))

    if scenario == "exclude_by_name":
        rules = [{"path": "**/" + os.path.basename(code_to_debug), "include": False}]
    elif scenario == "exclude_by_dir":
        rules = [{"path": os.path.dirname(code_to_debug), "include": False}]
    else:
        raise AssertionError("Unexpected scenario: %s" % (scenario,))

    with debug.Session() as session:
        session.initialize(
            target=(run_as, code_to_debug), start_method=start_method, rules=rules
        )
        # TODO: The process returncode doesn't match the one returned from the DAP.
        # See: https://github.com/Microsoft/ptvsd/issues/1278
        session.expected_returncode = some.int
        filters = ["raised", "uncaught"]

        session.send_request(
            "setExceptionBreakpoints", {"filters": filters}
        ).wait_for_response()
        session.start_debugging()

        # No exceptions should be seen.
        session.wait_for_exit()


@pytest.mark.parametrize("scenario", ["exclude_code_to_debug", "exclude_callback_dir"])
def test_exceptions_and_partial_exclude_rules(pyfile, start_method, run_as, scenario):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa
        from debug_me import backchannel
        import sys

        json = backchannel.read_json()
        call_me_back_dir = json["call_me_back_dir"]
        sys.path.append(call_me_back_dir)

        import call_me_back

        def call_func():
            raise RuntimeError("unhandled error")  # @raise_line

        call_me_back.call_me_back(call_func)  # @call_me_back_line
        print("done")

    line_numbers = code_to_debug.lines
    call_me_back_dir = test_data / "call_me_back"

    if scenario == "exclude_code_to_debug":
        rules = [{"path": "**/" + os.path.basename(code_to_debug), "include": False}]
    elif scenario == "exclude_callback_dir":
        rules = [{"path": call_me_back_dir, "include": False}]
    else:
        raise AssertionError("Unexpected scenario: %s" % (scenario,))

    with debug.Session() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            use_backchannel=True,
            rules=rules,
        )
        # TODO: The process returncode doesn't match the one returned from the DAP.
        # See: https://github.com/Microsoft/ptvsd/issues/1278
        session.expected_returncode = some.int
        filters = ["raised", "uncaught"]

        session.send_request(
            "setExceptionBreakpoints", {"filters": filters}
        ).wait_for_response()
        session.start_debugging()
        session.write_json({"call_me_back_dir": call_me_back_dir})

        if scenario == "exclude_code_to_debug":
            # Stop at handled
            hit = session.wait_for_stop(reason="exception")
            # We don't stop at the raise line but rather at the callback module which is
            # not excluded.
            assert len(hit.frames) == 1
            assert hit.frames[0] == some.dict.containing(
                {
                    "line": 2,
                    "source": some.dict.containing(
                        {
                            "path": some.path(
                                os.path.join(call_me_back_dir, "call_me_back.py")
                            )
                        }
                    ),
                }
            )
            # assert hit.frames[1] == some.dict.containing({ -- filtered out
            #     'line': line_numbers['call_me_back_line'],
            #     'source': some.dict.containing({
            #         'path': some.path(code_to_debug)
            #     })
            # })
            # 'continue' should terminate the debuggee
            session.send_continue()

            # Note: does not stop at unhandled exception because raise was in excluded file.

        elif scenario == "exclude_callback_dir":
            # Stop at handled raise_line
            hit = session.wait_for_stop(reason="exception")
            assert [
                (frame["name"], os.path.basename(frame["source"]["path"]))
                for frame in hit.frames
            ] == [
                ("call_func", "code_to_debug.py"),
                # ('call_me_back', 'call_me_back.py'), -- filtered out
                ("<module>", "code_to_debug.py"),
            ]
            assert hit.frames[0] == some.dict.containing(
                {
                    "line": line_numbers["raise_line"],
                    "source": some.dict.containing({"path": some.path(code_to_debug)}),
                }
            )
            session.send_request("continue").wait_for_response()

            # Stop at handled call_me_back_line
            hit = session.wait_for_stop(reason="exception")
            assert [
                (frame["name"], os.path.basename(frame["source"]["path"]))
                for frame in hit.frames
            ] == [("<module>", "code_to_debug.py")]
            assert hit.frames[0] == some.dict.containing(
                {
                    "line": line_numbers["call_me_back_line"],
                    "source": some.dict.containing({"path": some.path(code_to_debug)}),
                }
            )
            session.send_request("continue").wait_for_response()

            # Stop at unhandled
            hit = session.wait_for_stop(reason="exception")
            assert [
                (frame["name"], os.path.basename(frame["source"]["path"]))
                for frame in hit.frames
            ] == [
                ("call_func", "code_to_debug.py"),
                # ('call_me_back', 'call_me_back.py'), -- filtered out
                ("<module>", "code_to_debug.py"),
            ]

            assert hit.frames[0] == some.dict.containing(
                {
                    "line": line_numbers["raise_line"],
                    "source": some.dict.containing({"path": some.path(code_to_debug)}),
                }
            )
            session.send_continue()
        else:
            raise AssertionError("Unexpected scenario: %s" % (scenario,))

        session.wait_for_exit()
