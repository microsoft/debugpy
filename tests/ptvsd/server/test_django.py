# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import pytest
from ptvsd.common import compat
from tests import code, debug, log, net, test_data
from tests.debug import runners, targets
from tests.patterns import some

pytestmark = pytest.mark.timeout(60)

django_server = net.WebServer(net.get_test_server_port(8000, 8100))


class paths:
    django1 = test_data / "django1"
    app_py = django1 / "app.py"
    hello_html = django1 / "templates" / "hello.html"
    bad_html = django1 / "templates" / "bad.html"


class lines:
    app_py = code.get_marked_line_numbers(paths.app_py)


@pytest.fixture
@pytest.mark.parametrize("run", [runners.launch, runners.attach_by_socket["cli"]])
def start_django(run):
    def start(session, multiprocess=False):
        if multiprocess:
            pytest.skip("https://github.com/microsoft/ptvsd/issues/1706")

        # No clean way to kill Django server, expect non-zero exit code
        session.expected_exit_code = some.int

        session.config.update({"django": True, "subProcess": bool(multiprocess)})

        args = ["runserver"]
        if not multiprocess:
            args += ["--noreload"]
        args += ["--", str(django_server.port)]

        return run(session, targets.Program(paths.app_py, args), cwd=paths.django1)

    return start


@pytest.mark.parametrize("bp_target", ["code", "template"])
def test_django_breakpoint_no_multiproc(start_django, bp_target):
    bp_file, bp_line, bp_name = {
        "code": (paths.app_py, lines.app_py["bphome"], "home"),
        "template": (paths.hello_html, 8, "Django Template"),
    }[bp_target]
    bp_var_content = compat.force_str("Django-Django-Test")

    with debug.Session() as session:
        with start_django(session):
            session.set_breakpoints(bp_file, [bp_line])

        with django_server:
            home_request = django_server.get("/home")
            session.wait_for_stop(
                "breakpoint",
                expected_frames=[
                    some.dap.frame(some.dap.source(bp_file), line=bp_line, name=bp_name)
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


def test_django_template_exception_no_multiproc(start_django):
    with debug.Session() as session:
        with start_django(session):
            session.request("setExceptionBreakpoints", {"filters": ["raised", "uncaught"]})

        with django_server:
            django_server.get("/badtemplate", log_errors=False)
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


@pytest.mark.parametrize("exc_type", ["handled", "unhandled"])
def test_django_exception_no_multiproc(start_django, exc_type):
    exc_line = lines.app_py["exc_" + exc_type]

    with debug.Session() as session:
        with start_django(session):
            session.request("setExceptionBreakpoints", {"filters": ["raised", "uncaught"]})

        with django_server:
            django_server.get("/" + exc_type)
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


def test_django_breakpoint_multiproc(start_django):
    bp_line = lines.app_py["bphome"]
    bp_var_content = compat.force_str("Django-Django-Test")

    with debug.Session() as parent_session:
        with start_django(parent_session, multiprocess=True):
            parent_session.set_breakpoints(paths.app_py, [bp_line])

        child_pid = parent_session.wait_for_next_subprocess()
        with debug.Session() as child_session:
            # TODO: this is wrong, but we don't have multiproc attach
            # yet, so update this when that is done
            # https://github.com/microsoft/ptvsd/issues/1776
            with child_session.attach_by_pid(child_pid):
                child_session.set_breakpoints(paths.app_py, [bp_line])

            with django_server:
                home_request = django_server.get("/home")
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
