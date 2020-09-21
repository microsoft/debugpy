import debuggee

debuggee.setup()

import os
import signal
import sys

from django.conf import settings
from django.core.management import execute_from_command_line
from django.http import HttpResponse
from django.template import loader


def sigint_handler(signal, frame):
    import django.dispatch

    djshutdown = django.dispatch.Signal()
    djshutdown.send("system")
    sys.exit(0)


signal.signal(signal.SIGINT, sigint_handler)

settings.configure(
    MIDDLEWARE=[],
    DEBUG=True,
    SECRET_KEY="CD8FF4C1-7E6C-4E45-922D-C796271F2345",
    ROOT_URLCONF=sys.modules[__name__],
    SETTINGS_MODULE="",  # Added to avoid a KeyError during shutdown on the bad template test.
    TEMPLATES=[
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "APP_DIRS": True,
            "DIRS": [os.path.join(os.path.dirname(__file__), "templates")],
        }
    ],
)


def home(request):
    title = "hello"
    content = "Django-Django-Test"
    template = loader.get_template("hello.html")  # @bphome
    context = {"title": title, "content": content}
    return HttpResponse(template.render(context, request))


def bad_route_handled(request):
    try:
        raise ArithmeticError("Hello")  # @exc_handled
    except Exception:
        pass
    title = "hello"
    content = "Django-Django-Test"
    template = loader.get_template("hello.html")
    context = {"title": title, "content": content}
    return HttpResponse(template.render(context, request))


def bad_route_unhandled(request):
    raise ArithmeticError("Hello")  # @exc_unhandled
    title = "hello"
    content = "Django-Django-Test"
    template = loader.get_template("hello.html")
    context = {"title": title, "content": content}
    return HttpResponse(template.render(context, request))


def bad_template(request):
    title = "hello"
    content = "Django-Django-Test"
    context = {"title": title, "content": content}
    template = loader.get_template("bad.html")
    return HttpResponse(template.render(context, request))


def exit_app(request):
    if hasattr(signal, "SIGBREAK"):
        os.kill(os.getpid(), signal.SIGBREAK)
    else:
        os.kill(os.getpid(), signal.SIGTERM)
    return HttpResponse("Done")


if sys.version_info < (3, 0):
    from django.conf.urls import url

    urlpatterns = [
        url(r"home", home, name="home"),
        url(r"^handled$", bad_route_handled, name="bad_route_handled"),
        url(r"^unhandled$", bad_route_unhandled, name="bad_route_unhandled"),
        url(r"badtemplate", bad_template, name="bad_template"),
        url(r"exit", exit_app, name="exit_app"),
    ]
else:
    from django.urls import path

    urlpatterns = [
        path("home", home, name="home"),
        path("handled", bad_route_handled, name="bad_route_handled"),
        path("unhandled", bad_route_unhandled, name="bad_route_unhandled"),
        path("badtemplate", bad_template, name="bad_template"),
        path("exit", exit_app, name="exit_app"),
    ]

if __name__ == "__main__":
    execute_from_command_line(sys.argv)
