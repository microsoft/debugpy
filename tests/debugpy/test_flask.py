# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import pytest
import sys

from tests import code, debug, log, net, test_data
from tests.debug import runners, targets
from tests.patterns import some

pytestmark = pytest.mark.timeout(60)

flask_server = net.WebServer(net.get_test_server_port(7000, 7100))


class paths:
    flask1 = test_data / "flask1"
    app_py = flask1 / "app.py"
    main_py = flask1 / "main.py"
    hello_html = flask1 / "templates" / "hello.html"
    bad_html = flask1 / "templates" / "bad.html"


class lines:
    app_py = code.get_marked_line_numbers(paths.app_py)


@pytest.fixture
@pytest.mark.parametrize("run", [runners.launch, runners.attach_connect["cli"]])
def start_flask(run):
    def start(session, multiprocess=False):
        # No clean way to kill Flask server, expect non-zero exit code
        session.expected_exit_code = some.int

        session.config.env.update(
            {
                "FLASK_APP": paths.app_py,
                "FLASK_ENV": "development",
                "FLASK_DEBUG": "1" if multiprocess else "0",
            }
        )
        if sys.platform != "win32":
            locale = "en_US.utf8" if sys.platform.startswith("linux") else "en_US.UTF-8"
            session.config.env.update({"LC_ALL": locale, "LANG": locale})

        session.config.update({"jinja": True, "subProcess": multiprocess})

        args = ["run", "--no-debugger", "--with-threads"]
        if multiprocess:
            args += ["--reload"]
        else:
            args += ["--no-reload"]
        args += ["--port", str(flask_server.port)]

        if multiprocess and run.request == "attach":
            # For multiproc attach, we need to use a helper stub to import debuggee
            # before running Flask; otherwise, we will get the connection only from
            # the subprocess, not from the Flask server process.
            target = targets.Program(paths.main_py, args=args)
        else:
            target = targets.Module(name="flask", args=args)

        return run(session, target, cwd=paths.flask1)

    return start


@pytest.mark.parametrize("bp_target", ["code", "template"])
def test_flask_breakpoint_no_multiproc(start_flask, bp_target):
    bp_file, bp_line, bp_name = {
        "code": (paths.app_py, lines.app_py["bphome"], "home"),
        "template": (paths.hello_html, 8, "template"),
    }[bp_target]
    bp_var_content = "Flask-Jinja-Test"

    with debug.Session() as session:
        with start_flask(session):
            breakpoints = session.set_breakpoints(bp_file, [bp_line])
            for bp in breakpoints:
                # They'll be verified later on for templates.
                assert bp["verified"] == (bp_target == "code")

        with flask_server:
            home_request = flask_server.get("/")

            if bp_target == "template":
                breakpoint_body = session.wait_for_next_event("breakpoint")
                assert breakpoint_body["reason"] == "changed"
                assert breakpoint_body["breakpoint"]["verified"]

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


def test_flask_template_exception_no_multiproc(start_flask):
    with debug.Session() as session:
        with start_flask(session):
            session.request(
                "setExceptionBreakpoints", {"filters": ["raised", "uncaught"]}
            )

        with flask_server:
            flask_server.get("/badtemplate")
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

            # Exception gets reported again as it is re-raised in every frame between
            # the template and app.py. The number of frames is a Flask implementation
            # detail, and varies between versions, so we keep iterating until we see
            # it reported in app.py.
            while True:
                log.info("Exception propagating to next frame...")
                session.request_continue()
                stop = session.wait_for_stop("exception")
                if stop.frames[0] == some.dap.frame(paths.app_py, line=some.int):
                    break

            # Let the request finish processing and respond with HTTP 500.
            session.request_continue()


@pytest.mark.parametrize("exc_type", ["handled", "unhandled"])
def test_flask_exception_no_multiproc(start_flask, exc_type):
    exc_line = lines.app_py["exc_" + exc_type]

    with debug.Session() as session:
        with start_flask(session):
            session.request(
                "setExceptionBreakpoints", {"filters": ["raised", "uncaught"]}
            )

        with flask_server:
            flask_server.get("/" + exc_type)
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


def test_flask_breakpoint_multiproc(start_flask):
    bp_line = lines.app_py["bphome"]
    bp_var_content = "Flask-Jinja-Test"

    with debug.Session() as parent_session:
        with start_flask(parent_session, multiprocess=True):
            parent_session.set_breakpoints(paths.app_py, [bp_line])

        with parent_session.wait_for_next_subprocess() as child_session:
            with child_session.start():
                child_session.set_breakpoints(paths.app_py, [bp_line])

            with flask_server:
                home_request = flask_server.get("/")
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
