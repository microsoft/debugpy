import os
import signal
import sys
from django.conf import settings
from django.urls import path
from django.core.management import execute_from_command_line
from django.http import HttpResponse
from django.template import loader
import ptvsd


ptvsd_host = os.getenv('PTVSD_HOST', 'localhost')
ptvsd_port = os.getenv('PTVSD_PORT', '9879')
ptvsd.enable_attach((ptvsd_host, ptvsd_port))
ptvsd.wait_for_attach()


def sigint_handler(signal, frame):
    import django.dispatch
    djshutdown = django.dispatch.Signal()
    djshutdown.send('system')
    sys.exit(0)


signal.signal(signal.SIGINT, sigint_handler)


settings.configure(
    DEBUG=True,
    SECRET_KEY='B21034EB-A1A8-4DDD-90B4-C13B67BE2AE7',
    ROOT_URLCONF=sys.modules[__name__],
    TEMPLATES=[
        {
            'BACKEND': 'django.template.backends.django.DjangoTemplates',
            'APP_DIRS': True,
            'DIRS': [
                'templates/'
            ]
        },
    ]
)


def home(request):
    title = 'hello'
    content = 'Django-Django-Test'
    template = loader.get_template('hello.html')
    context = {
        'title': title,
        'content': content,
    }
    return HttpResponse(template.render(context, request))


def bad_route_handled(request):
    try:
        raise ArithmeticError('Hello')
    except Exception:
        pass
    title = 'hello'
    content = 'Django-Django-Test'
    template = loader.get_template('hello.html')
    context = {
        'title': title,
        'content': content,
    }
    return HttpResponse(template.render(context, request))


def bad_route_unhandled(request):
    raise ArithmeticError('Hello')
    title = 'hello'
    content = 'Django-Django-Test'
    template = loader.get_template('hello.html')
    context = {
        'title': title,
        'content': content,
    }
    return HttpResponse(template.render(context, request))


def exit_app(request):
    os.kill(os.getpid(), signal.SIGTERM)
    return HttpResponse('Done')


urlpatterns = [
    path('', home, name='home'),
    path('handled', bad_route_handled, name='bad_route_handled'),
    path('unhandled', bad_route_unhandled, name='bad_route_unhandled'),
    path('exit', exit_app, name='exit_app'),
]

if __name__ == '__main__':
    execute_from_command_line(sys.argv)
