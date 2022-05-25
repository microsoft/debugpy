import debuggee

debuggee.setup()

import os
import sys

from django.conf import settings
from django.core.management import execute_from_command_line
from django.core.signals import request_finished
from django.dispatch import receiver
from django.http import HttpResponse
from django.template import loader


exiting = False


@receiver(request_finished)
def on_request_finished(sender, **kwargs):
    if exiting:
        os._exit(0)


settings.configure(
    MIDDLEWARE=[],
    DEBUG=True,
    SECRET_KEY="Placeholder_CD8FF4C1-7E6C-4E45-922D-C796271F2345",
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
    global exiting
    exiting = True
    return HttpResponse("Done")


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
