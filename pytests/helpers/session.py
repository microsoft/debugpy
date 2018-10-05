# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import os
import socket
import subprocess
import sys
import threading
import time

import ptvsd
from ptvsd.messaging import JsonIOStream, JsonMessageChannel, MessageHandlers, RequestFailure
from . import print, watchdog
from .messaging import LoggingJsonStream
from .pattern import Pattern
from .timeline import Timeline, Request, Event


# ptvsd.__file__ will be <dir>/ptvsd/__main__.py - we want <dir>.
PTVSD_SYS_PATH = os.path.basename(os.path.basename(ptvsd.__file__))


class DebugSession(object):
    WAIT_FOR_EXIT_TIMEOUT = 5

    def __init__(self, method='launch', ptvsd_port=None):
        assert method in ('launch', 'attach_pid', 'attach_socket')
        assert ptvsd_port is None or method == 'attach_socket'

        print('New debug session with method %r' % method)

        self.method = method
        self.ptvsd_port = ptvsd_port or 5678
        self.multiprocess = False
        self.multiprocess_port_range = None

        self.is_running = False
        self.process = None
        self.socket = None
        self.server_socket = None
        self.connected = threading.Event()
        self.backchannel_socket = None
        self.backchannel_port = None
        self.backchannel_established = threading.Event()
        self.debug_options = ['RedirectOutput']
        self.timeline = Timeline()

    def stop(self):
        if self.process:
            try:
                self.process.kill()
            except:
                pass
        if self.socket:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
            except:
                self.socket = None
        if self.server_socket:
            try:
                self.server_socket.shutdown(socket.SHUT_RDWR)
            except:
                self.server_socket = None
        if self.backchannel_socket:
            try:
                self.backchannel_socket.shutdown(socket.SHUT_RDWR)
            except:
                self.backchannel_socket = None

    def prepare_to_run(self, perform_handshake=True, filename=None, module=None, backchannel=False):
        """Spawns ptvsd using the configured method, telling it to execute the
        provided Python file or module, and establishes a message channel to it.

        If backchannel is True, calls self.setup_backchannel() before returning.

        If perform_handshake is True, calls self.handshake() before returning.
        """

        argv = [sys.executable]
        if self.method != 'attach_pid':
            argv += ['-m', 'ptvsd']

        if self.method == 'attach_socket':
            argv += ['--port', str(self.ptvsd_port), '--wait']
        else:
            self._listen()
            argv += ['--host', 'localhost', '--port', str(self.ptvsd_port)]

        if self.multiprocess:
            argv += ['--multiprocess']

        if self.multiprocess_port_range:
            argv += ['--multiprocess-port-range', '%d-%d' % self.multiprocess_port_range]

        if filename:
            assert not module
            argv += [filename]
        elif module:
            assert not filename
            argv += ['-m', module]

        env = os.environ.copy()
        env.update({'PYTHONPATH': PTVSD_SYS_PATH})

        if backchannel:
            self.setup_backchannel()
        if self.backchannel_port:
            env['PTVSD_BACKCHANNEL_PORT'] = str(self.backchannel_port)

        print('Spawning %r' % argv)
        self.process = subprocess.Popen(argv, env=env, stdin=subprocess.PIPE)
        self.is_running = True
        watchdog.create(self.process.pid)

        if self.method == 'attach_socket':
            self.connect()
        self.connected.wait()
        assert self.ptvsd_port
        assert self.socket
        print('ptvsd#%d has pid=%d' % (self.ptvsd_port, self.process.pid))

        self.timeline.beginning.await_following(Event('output', Pattern({
            'category': 'telemetry',
            'output': 'ptvsd',
            'data': {'version': ptvsd.__version__}
        })))

        if perform_handshake:
            return self.handshake()

    def wait_for_exit(self, expected_returncode=0):
        """Waits for the spawned ptvsd process to exit. If it doesn't exit within
        WAIT_FOR_EXIT_TIMEOUT seconds, forcibly kills the process. After the process
        exits, validates its return code to match expected_returncode.
        """

        def kill():
            time.sleep(self.WAIT_FOR_EXIT_TIMEOUT)
            print('ptvsd#%r (pid=%d) timed out, killing it' % (self.ptvsd_port, self.process.pid))
            if self.is_running:
                self.process.kill()
        kill_thread = threading.Thread(target=kill, name='ptvsd#%r watchdog (pid=%d)' % (self.ptvsd_port, self.process.pid))
        kill_thread.daemon = True
        kill_thread.start()

        self.process.wait()
        self.is_running = False
        assert self.process.returncode == expected_returncode

    def wait_for_disconnect(self):
        """Waits for the connected ptvsd process to disconnect.
        """
        return self.channel.wait()

    def _listen(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind(('localhost', 0))
        _, self.ptvsd_port = self.server_socket.getsockname()
        self.server_socket.listen(0)

        def accept_worker():
            print('Listening for incoming connection from ptvsd#%d' % self.ptvsd_port)
            self.socket, _ = self.server_socket.accept()
            print('Incoming ptvsd#%d connection accepted' % self.ptvsd_port)
            self._setup_channel()

        accept_thread = threading.Thread(target=accept_worker, name='ptvsd#%d listener' % self.ptvsd_port)
        accept_thread.daemon = True
        accept_thread.start()

    def connect(self):
        # ptvsd will take some time to spawn and start listening on the port,
        # so just hammer at it until it responds (or we time out).
        while not self.socket:
            try:
                self._try_connect()
            except socket.error:
                pass
            time.sleep(0.1)

    def _try_connect(self):
        print('Trying to connect to ptvsd#%d' % self.ptvsd_port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(('localhost', self.ptvsd_port))
        print('Successfully connected to ptvsd#%d' % self.ptvsd_port)
        self.socket = sock
        self._setup_channel()

    def _setup_channel(self):
        self.stream = LoggingJsonStream(JsonIOStream.from_socket(self.socket), 'ptvsd#%d' % self.ptvsd_port)
        handlers = MessageHandlers(request=self._process_request, event=self._process_event)
        self.channel = JsonMessageChannel(self.stream, handlers)
        self.channel.start()
        self.connected.set()

    def send_request(self, command, arguments=None):
        request = self.timeline.record_request(command, arguments)
        request.sent = self.channel.send_request(command, arguments)
        request.sent.on_response(lambda response: self._process_response(request, response))
        request.causing = lambda expectation: request.await_following(expectation) and request
        assert Request(command, arguments).is_realized_by(request)
        return request

    def mark(self, id):
        return self.timeline.mark(id)

    def handshake(self):
        """Performs the handshake that establishes the debug session ('initialized'
        and 'launch' or 'attach').

        After this method returns, ptvsd is not running any code yet, but it is
        ready to accept any configuration requests (e.g. for initial breakpoints).
        Once initial configuration is complete, start_debugging() should be called
        to finalize the configuration stage, and start running code.
        """

        (self.send_request('initialize', {'adapterID': 'test'})
            .causing(Event('initialized', {}))
            .wait_for_response())

        request = 'launch' if self.method == 'launch' else 'attach'
        self.send_request(request, {'debugOptions': self.debug_options}).wait_for_response()

    def start_debugging(self):
        """Finalizes the configuration stage, and issues a 'configurationDone' request
        to start running code under debugger.

        After this method returns, ptvsd is running the code in the script file or module
        that was specified in prepare_to_run().
        """
        return self.send_request('configurationDone').wait_for_response()

    def _process_event(self, channel, event, body):
        self.timeline.record_event(event, body)
        if event == 'terminated':
            self.channel.close()

    def _process_response(self, request, response):
        body = response.body if response.success else RequestFailure(response.error_message)
        self.timeline.record_response(request, body)

    def _process_request(self, channel, command, arguments):
        assert False, 'ptvsd should not be sending requests.'

    def setup_backchannel(self):
        self.backchannel_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.backchannel_socket.bind(('localhost', 0))
        _, self.backchannel_port = self.backchannel_socket.getsockname()
        self.backchannel_socket.listen(0)
        backchannel_thread = threading.Thread(target=self._backchannel_worker, name='ptvsd#%d backchannel'  % self.ptvsd_port)
        backchannel_thread.daemon = True
        backchannel_thread.start()

    def _backchannel_worker(self):
        print('Listening for incoming backchannel connection for bchan#%d' % self.ptvsd_port)
        sock, _ = self.backchannel_socket.accept()
        print('Incoming bchan#%d backchannel connection accepted' % self.ptvsd_port)
        self._backchannel_stream = LoggingJsonStream(JsonIOStream.from_socket(sock), 'bchan#%d' % self.ptvsd_port)
        self.backchannel_established.set()

    @property
    def backchannel(self):
        assert self.backchannel_port, 'backchannel() must be called after setup_backchannel()'
        self.backchannel_established.wait()
        return self._backchannel_stream

    def read_json(self):
        return self.backchannel.read_json()

    def write_json(self, value):
        t = self.timeline.mark(('sending', value))
        self.backchannel.write_json(value)
        return t
