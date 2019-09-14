# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import platform
import pytest
import sys

from ptvsd.common import compat
from tests import code, debug, log, net, test_data
from tests.debug import runners
from tests.patterns import some

pytestmark = pytest.mark.timeout(60)

flask = net.WebServer(net.get_test_server_port(7000, 7100))


class paths:
    flask1 = test_data / "flask1"
    app_py = flask1 / "app.py"
    hello_html = flask1 / "templates" / "hello.html"
    bad_html = flask1 / "templates" / "bad.html"


class lines:
    app_py = code.get_marked_line_numbers(paths.app_py)


def _initialize_session(session, multiprocess=None, exit_code=0):
    if multiprocess:
        pytest.skip("https://github.com/microsoft/ptvsd/issues/1706")

    env = {
        "FLASK_APP": paths.app_py,
        "FLASK_ENV": "development",
        "FLASK_DEBUG": "1" if multiprocess else "0",
    }
    if platform.system() != "Windows":
        locale = "en_US.utf8" if platform.system() == "Linux" else "en_US.UTF-8"
        env.update({"LC_ALL": locale, "LANG": locale})

    args = ["run"]
    if not multiprocess:
        args += ["--no-debugger", "--no-reload", "--with-threads"]
    args += ["--port", str(flask.port)]

    session.expected_exit_code = exit_code
    session.configure(
        "module",
        "flask",
        cwd=paths.flask1,
        jinja=True,
        subProcess=multiprocess,
        args=args,
        env=env,
    )


@pytest.mark.parametrize(
    "start_method", [runners.launch, runners.attach_by_socket["cli"]]
)
@pytest.mark.parametrize("bp_target", ["code", "template"])
def test_flask_breakpoint_no_multiproc(start_method, bp_target):
    bp_file, bp_line, bp_name = {
        "code": (paths.app_py, lines.app_py["bphome"], "home"),
        "template": (paths.hello_html, 8, "template"),
    }[bp_target]
    bp_var_content = compat.force_str("Flask-Jinja-Test")

    with debug.Session(start_method) as session:
        _initialize_session(
            session, exit_code=some.int
        )  # No clean way to kill Flask server
        session.set_breakpoints(bp_file, [bp_line])
        session.start_debugging()

        with flask:
            home_request = flask.get("/")
            session.wait_for_stop(
                "breakpoint",
                expected_frames=[
                    some.dap.frame(some.dap.source(bp_file), name=bp_name, line=bp_line)
                ],
            )

            var_content = session.get_variable("content")
            assert var_content == some.dict.containing(
                {
                    "name": "content",
                    "type": "str",
                    "value": repr(bp_var_content),
                    "presentationHint": {"attributes": ["rawString"]},
                    "evaluateName": "content",
                    "variablesReference": 0,
                }
            )

            session.request_continue()
            assert bp_var_content in home_request.response_text()


@pytest.mark.parametrize(
    "start_method", [runners.launch, runners.attach_by_socket["cli"]]
)
def test_flask_template_exception_no_multiproc(start_method):
    with debug.Session(start_method) as session:
        _initialize_session(
            session, exit_code=some.int
        )  # No clean way to kill Flask server
        session.request("setExceptionBreakpoints", {"filters": ["raised", "uncaught"]})
        session.start_debugging()

        with flask:
            flask.get("/badtemplate")
            stop = session.wait_for_stop(
                "exception",
                expected_frames=[
                    some.dap.frame(
                        some.dap.source(paths.bad_html),
                        name=some.str,  # varies depending on Jinja version
                        line=8,
                    )
                ],
            )

            exception_info = session.request(
                "exceptionInfo", {"threadId": stop.thread_id}
            )
            assert exception_info == some.dict.containing(
                {
                    "exceptionId": some.str.ending_with("TemplateSyntaxError"),
                    "breakMode": "always",
                    "description": some.str.containing("doesnotexist"),
                    "details": some.dict.containing(
                        {
                            "message": some.str.containing("doesnotexist"),
                            "typeName": some.str.ending_with("TemplateSyntaxError"),
                        }
                    ),
                }
            )

            session.request_continue()

            log.info("Exception will be reported again in {0}", paths.app_py)
            session.wait_for_stop("exception")
            session.request_continue()

            # In Python 2, Flask reports this exception one more time, and it is
            # reported for both frames again.
            if sys.version_info < (3,):
                log.info("Exception gets double-reported in Python 2.")
                session.wait_for_stop("exception")
                session.request_continue()
                session.wait_for_stop("exception")
                session.request_continue()


@pytest.mark.parametrize(
    "start_method", [runners.launch, runners.attach_by_socket["cli"]]
)
@pytest.mark.parametrize("exc_type", ["handled", "unhandled"])
def test_flask_exception_no_multiproc(start_method, exc_type):
    exc_line = lines.app_py["exc_" + exc_type]

    with debug.Session(start_method) as session:
        _initialize_session(
            session, exit_code=some.int
        )  # No clean way to kill Flask server
        session.request("setExceptionBreakpoints", {"filters": ["raised", "uncaught"]})
        session.start_debugging()

        with flask:
            flask.get("/" + exc_type)
            stopped = session.wait_for_stop(
                "exception",
                expected_frames=[
                    some.dap.frame(
                        some.dap.source(paths.app_py),
                        line=exc_line,
                        name="bad_route_" + exc_type,
                    )
                ],
            ).body

            assert stopped == some.dict.containing(
                {
                    "reason": "exception",
                    "text": some.str.ending_with("ArithmeticError"),
                    "description": "Hello",
                }
            )

            exception_info = session.request(
                "exceptionInfo", {"threadId": stopped["threadId"]}
            )

            assert exception_info == {
                "exceptionId": some.str.ending_with("ArithmeticError"),
                "breakMode": "always",
                "description": "Hello",
                "details": {
                    "message": "Hello",
                    "typeName": some.str.ending_with("ArithmeticError"),
                    "source": some.path(paths.app_py),
                    "stackTrace": some.str,
                },
            }

            session.request_continue()


def test_flask_breakpoint_multiproc():
    bp_line = lines.app_py["bphome"]
    bp_var_content = compat.force_str("Flask-Jinja-Test")

    with debug.Session(runners.launch) as parent_session:
        # No clean way to kill Flask server
        _initialize_session(parent_session, multiprocess=True, exit_code=some.int)
        parent_session.set_breakpoints(paths.app_py, [bp_line])
        parent_session.start_debugging()

        with parent_session.attach_to_next_subprocess() as child_session:
            child_session.set_breakpoints(paths.app_py, [bp_line])
            child_session.start_debugging()

            with flask:
                home_request = flask.get("/")
                child_session.wait_for_stop(
                    "breakpoint",
                    expected_frames=[
                        some.dap.frame(
                            some.dap.source(paths.app_py), line=bp_line, name="home"
                        )
                    ],
                )

                var_content = child_session.get_variable("content")
                assert var_content == some.dict.containing(
                    {
                        "name": "content",
                        "type": "str",
                        "value": repr(bp_var_content),
                        "presentationHint": {"attributes": ["rawString"]},
                        "evaluateName": "content",
                        "variablesReference": 0,
                    }
                )

                child_session.request_continue()
                assert bp_var_content in home_request.response_text()
