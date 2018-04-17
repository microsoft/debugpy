import contextlib
import os
import sys
import unittest

import ptvsd
from ptvsd.wrapper import INITIALIZE_RESPONSE # noqa
from tests.helpers.pydevd._live import LivePyDevd
from tests.helpers.workspace import PathEntry

from . import (
    VSCFixture,
    VSCTest,
)


class Fixture(VSCFixture):

    def __init__(self, source, new_fake=None):
        self._pydevd = LivePyDevd(source)
        super(Fixture, self).__init__(
            new_fake=new_fake,
            start_adapter=self._pydevd.start,
        )

    @property
    def _proc(self):
        return self._pydevd.binder.ptvsd.proc

    @property
    def binder(self):
        return self._pydevd.binder

    def install_sig_handler(self):
        self._pydevd._ptvsd.install_sig_handler()


class TestBase(VSCTest):

    FIXTURE = Fixture

    FILENAME = None
    SOURCE = ''

    def setUp(self):
        super(TestBase, self).setUp()
        self._workspace = PathEntry()

        self._filename = None
        if self.FILENAME is not None:
            self.set_source_file(self.FILENAME, self.SOURCE)

    def tearDown(self):
        super(TestBase, self).tearDown()
        self._workspace.cleanup()

    @property
    def workspace(self):
        return self._workspace

    @property
    def filename(self):
        return None if self._filename is None else self._filePath

    def _new_fixture(self, new_daemon):
        self.assertIsNotNone(self._filename)
        return self.FIXTURE(self._filename, new_daemon)

    def set_source_file(self, filename, content=None):
        self.assertIsNone(self._fix)
        if content is not None:
            filename = self.workspace.write(filename, content=content)
        self.workspace.install()
        self._filePath = filename
        self._filename = 'file:' + filename

    def set_module(self, name, content=None):
        self.assertIsNone(self._fix)
        if content is not None:
            self.write_module(name, content)
        self.workspace.install()
        self._filename = 'module:' + name


##################################
# lifecycle tests

class LifecycleTests(TestBase, unittest.TestCase):

    FILENAME = 'spam.py'
    SOURCE = ''

    @contextlib.contextmanager
    def running(self):
        addr = (None, 8888)
        with self.fake.start(addr):
            #with self.fix.install_sig_handler():
                yield

    def test_launch(self):
        addr = (None, 8888)
        with self.fake.start(addr):
            # TODO: There's a race with the initial "output" event.
            with self.vsc.wait_for_event('output'):
                pass

            with self.vsc.wait_for_event('initialized'):
                # initialize
                req_initialize = self.send_request('initialize', {
                    'adapterID': 'spam',
                })

                # attach
                req_attach = self.send_request('attach')

            # configuration
            req_config = self.send_request('configurationDone')

            # Normal ops would go here.

            # end
            with self.wait_for_events(['exited', 'terminated']):
                self.fix.binder.done()
            # TODO: Send a "disconnect" request?
            self.fix.binder.wait_until_done()
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.new_event(
                'output',
                category='telemetry',
                output='ptvsd',
                data={'version': ptvsd.__version__}),
            self.new_response(req_initialize, **INITIALIZE_RESPONSE),
            self.new_event('initialized'),
            self.new_response(req_attach),
            self.new_response(req_config),
            self.new_event('process', **dict(
                name=sys.argv[0],
                systemProcessId=os.getpid(),
                isLocalProcess=True,
                startMethod='attach',
            )),
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
        ])


##################################
# "normal operation" tests

class VSCFlowTest(TestBase):

    @contextlib.contextmanager
    def launched(self, port=8888, **kwargs):
        kwargs.setdefault('process', False)
        with self.lifecycle.launched(port=port, hide=True, **kwargs):
            yield
            self.fix.binder.done()
        self.fix.binder.wait_until_done()


class BreakpointTests(VSCFlowTest, unittest.TestCase):

    FILENAME = 'spam.py'
    SOURCE = """
        from __future__ import print_function

        #class Counter(object):
        #    def __init__(self, start=0):
        #        self._next = start
        #    def __repr__(self):
        #        return '{}(start={})'.format(type(self).__name__, self._next)
        #    def __int__(self):
        #        return self._next - 1
        #    __index__ = __int__
        #    def __iter__(self):
        #        return self
        #    def __next__(self):
        #        value = self._next
        #        self._next += 1
        #    def peek(self):
        #        return self._next
        #    def inc(self, diff=1):
        #        self._next += diff

        def inc(value, count=1):
            return value + count

        x = 1
        x = inc(x)
        y = inc(x, 2)
        z = inc(3)
        print(x, y, z)
        """

    def test_no_breakpoints(self):
        with self.launched():
            # Allow the script to run to completion.
            received = self.vsc.received

        self.assert_received(self.vsc, [])
        self.assert_vsc_received(received, [])


class LogpointTests(TestBase, unittest.TestCase):
    FILENAME = 'spam.py'
    SOURCE = """
        a = 1
        b = 2
        c = 3
        d = 4
        """

    @contextlib.contextmanager
    def running(self):
        addr = (None, 8888)
        with self.fake.start(addr):
                yield

    def test_basic(self):
        addr = (None, 8888)
        with self.fake.start(addr):
            with self.vsc.wait_for_event('output'):
                pass

            with self.vsc.wait_for_event('initialized'):
                req_initialize = self.send_request('initialize', {
                    'adapterID': 'spam',
                })
                req_attach = self.send_request('attach', {
                    'debugOptions': ['RedirectOutput']
                })
                req_breakpoints = self.send_request('setBreakpoints', {
                    'source': {'path': self.filename},
                    'breakpoints': [
                        {
                            'line': '4',
                            'logMessage': '{a}+{b}=3'
                        },
                    ],
                })

            req_config = self.send_request('configurationDone')

            with self.wait_for_events(['exited', 'terminated']):
                self.fix.binder.done()
            self.fix.binder.wait_until_done()
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.new_event(
                'output',
                category='telemetry',
                output='ptvsd',
                data={'version': ptvsd.__version__}),
            self.new_response(req_initialize, **INITIALIZE_RESPONSE),
            self.new_event('initialized'),
            self.new_response(req_attach),
            self.new_response(req_breakpoints, **dict(
                breakpoints=[{'id': 1, 'verified': True, 'line': '4'}]
            )),
            self.new_response(req_config),
            self.new_event('process', **dict(
                name=sys.argv[0],
                systemProcessId=os.getpid(),
                isLocalProcess=True,
                startMethod='attach',
            )),
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
            self.new_event('output', **dict(category='stdout', output='1+2=3' + os.linesep)), # noqa
        ])
