# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import pytest
from ptvsd.common import compat
from tests import code, debug, log, net, test_data
from tests.debug import start_methods
from tests.patterns import some

pytestmark = pytest.mark.timeout(60)

django = net.WebServer(net.get_test_server_port(8000, 8100))


class paths:
    django1 = test_data / "django1"
    app_py = django1 / "app.py"
    hello_html = django1 / "templates" / "hello.html"
    bad_html = django1 / "templates" / "bad.html"


class lines:
    app_py = code.get_marked_line_numbers(paths.app_py)


def _initialize_session(session, multiprocess=False, exit_code=0):
    args = ["runserver"]
    if not multiprocess:
        args += ["--noreload"]
    args += ["--", str(django.port)]

    session.expected_exit_code = exit_code
    session.configure(
        "program", paths.app_py,
        cwd=paths.django1,
        multiprocess=multiprocess,
        args=args,
        django=True
    )


@pytest.mark.parametrize("start_method", [start_methods.Launch, start_methods.AttachSocketCmdLine])
@pytest.mark.parametrize("bp_target", ["code", "template"])
def test_django_breakpoint_no_multiproc(start_method, bp_target):
    bp_file, bp_line, bp_name = {
        "code": (paths.app_py, lines.app_py["bphome"], "home"),
        "template": (paths.hello_html, 8, "Django Template"),
    }[bp_target]
    bp_var_content = compat.force_str("Django-Django-Test")

    with debug.Session(start_method) as session:
        _initialize_session(session, exit_code=some.int)
        session.set_breakpoints(bp_file, [bp_line])
        session.start_debugging()

        with django:
            home_request = django.get("/home")
            session.wait_for_stop(
                "breakpoint",
                expected_frames=[
                    some.dap.frame(
                        some.dap.source(bp_file),
                        line=bp_line,
                        name=bp_name,
                    ),
                ],
            )

            var_content = session.get_variable("content")
            assert var_content == some.dict.containing(
                {
                    "name": "content",
                    "type": "str",
                    "value": compat.unicode_repr(bp_var_content),
                    "presentationHint": {"attributes": ["rawString"]},
                    "evaluateName": "content",
                    "variablesReference": 0,
                }
            )

            session.request_continue()
            assert bp_var_content in home_request.response_text()


@pytest.mark.parametrize("start_method", [start_methods.Launch, start_methods.AttachSocketCmdLine])
def test_django_template_exception_no_multiproc(start_method):
    with debug.Session(start_method) as session:
        _initialize_session(session, exit_code=some.int)
        session.request("setExceptionBreakpoints", {"filters": ["raised", "uncaught"]})
        session.start_debugging()

        with django:
            django.get("/badtemplate", log_errors=False)
            stop = session.wait_for_stop(
                "exception",
                expected_frames=[
                    some.dap.frame(
                        some.dap.source(paths.bad_html),
                        line=8,
                        name="Django TemplateSyntaxError",
                    )
                ],
            )

            # Will stop once in the plugin
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


@pytest.mark.parametrize("start_method", [start_methods.Launch, start_methods.AttachSocketCmdLine])
@pytest.mark.parametrize("exc_type", ["handled", "unhandled"])
def test_django_exception_no_multiproc(start_method, exc_type):
    exc_line = lines.app_py["exc_" + exc_type]

    with debug.Session(start_method) as session:
        _initialize_session(session, exit_code=some.int)
        session.request("setExceptionBreakpoints", {"filters": ["raised", "uncaught"]})
        session.start_debugging()

        with django:
            django.get("/" + exc_type)
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


@pytest.mark.parametrize("start_method", [start_methods.Launch])
def test_django_breakpoint_multiproc(start_method):
    bp_line = lines.app_py["bphome"]
    bp_var_content = compat.force_str("Django-Django-Test")

    with debug.Session(start_method) as parent_session:
        _initialize_session(parent_session, multiprocess=True, exit_code=some.int)
        parent_session.set_breakpoints(paths.app_py, [bp_line])
        parent_session.start_debugging()

        with parent_session.attach_to_next_subprocess() as child_session:
            child_session.set_breakpoints(paths.app_py, [bp_line])
            child_session.start_debugging()

            with django:
                home_request = django.get("/home")
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
                        "value": compat.unicode_repr(bp_var_content),
                        "presentationHint": {"attributes": ["rawString"]},
                        "evaluateName": "content",
                    }
                )

                child_session.request_continue()
                assert bp_var_content in home_request.response_text()
