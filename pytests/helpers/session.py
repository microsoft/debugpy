# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import contextlib
import os
import socket
import subprocess
import sys
import threading
import time

import ptvsd
from ptvsd.messaging import JsonIOStream, JsonMessageChannel, MessageHandlers, RequestFailure
from . import print
from .messaging import LoggingJsonStream
from .timeline import Timeline, Request, Response, Event


# ptvsd.__file__ will be <dir>/ptvsd/__main__.py - we want <dir>.
PTVSD_SYS_PATH = os.path.basename(os.path.basename(ptvsd.__file__))


class DebugSession(object):
    WAIT_FOR_EXIT_TIMEOUT = 5

    def __init__(self, method='launch', ptvsd_port=None):
        assert method in ('launch', 'attach_pid', 'attach_socket')
        assert ptvsd_port is None or method == 'attach_socket'

        print('New debug session with method %r' % method)

        self.method = method
        self.ptvsd_port = ptvsd_port
        self.process = None
        self.socket = None
        self.server_socket = None
        self.connected = threading.Event()
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

    def prepare_to_run(self, perform_handshake=True, filename=None, module=None):
        """Spawns ptvsd using the configured method, telling it to execute the
        provided Python file or module, and establishes a message channel to it.

        If perform_handshake is True, calls self.handshake() before returning.
        """

        argv = [sys.executable]
        if self.method != 'attach_pid':
            argv += ['-m', 'ptvsd']

        if self.method == 'attach_socket':
            if self.ptvsd_port is None:
                self.ptvsd_port = 5678
            argv += ['--port', str(self.ptvsd_port)]
        else:
            port = self._listen()
            argv += ['--host', 'localhost', '--port', str(port)]

        if filename:
            assert not module
            argv += [filename]
        elif module:
            assert not filename
            argv += ['-m', module]

        env = os.environ.copy()
        env.update({'PYTHONPATH': PTVSD_SYS_PATH})

        print('Spawning %r' % argv)
        self.process = subprocess.Popen(argv, env=env, stdin=subprocess.PIPE)
        if self.ptvsd_port:
            # ptvsd will take some time to spawn and start listening on the port,
            # so just hammer at it until it responds (or we time out).
            while not self.socket:
                try:
                    self._connect()
                except socket.error:
                    pass
                time.sleep(0.1)
        else:
            self.connected.wait()
            assert self.socket

        self.stream = LoggingJsonStream(JsonIOStream.from_socket(self.socket))

        handlers = MessageHandlers(request=self._process_request, event=self._process_event)
        self.channel = JsonMessageChannel(self.stream, handlers)
        self.channel.start()

        if perform_handshake:
            self.handshake()

    def wait_for_exit(self, expected_returncode=0):
        """Waits for the spawned ptvsd process to exit. If it doesn't exit within
        WAIT_FOR_EXIT_TIMEOUT seconds, forcibly kills the process. After the process
        exits, validates its return code to match expected_returncode.
        """

        process = self.process
        if not process:
            return

        def kill():
            time.sleep(self.WAIT_FOR_EXIT_TIMEOUT)
            print('ptvsd process timed out, killing it')
            p = process
            if p:
                p.kill()
        kill_thread = threading.Thread(target=kill)
        kill_thread.daemon = True
        kill_thread.start()

        process.wait()
        assert process.returncode == expected_returncode

    def _listen(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind(('localhost', 0))
        _, port = self.server_socket.getsockname()
        self.server_socket.listen(0)

        def accept_worker():
            print('Listening for incoming connection from ptvsd on port %d' % port)
            self.socket, _ = self.server_socket.accept()
            print('Incoming ptvsd connection accepted')
            self.connected.set()

        accept_thread = threading.Thread(target=accept_worker)
        accept_thread.daemon = True
        accept_thread.start()

        return port

    def _connect(self):
        print('Trying to connect to ptvsd on port %d' % self.ptvsd_port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(('localhost', self.ptvsd_port))
        print('Successfully connected to ptvsd')
        self.socket = sock

    def send_request(self, command, arguments=None):
        request = self.timeline.record_request(command, arguments)
        request.sent = self.channel.send_request(command, arguments)
        request.sent.on_response(lambda response: self._process_response(request, response))
        assert Request(command, arguments) in self.timeline
        return request

    def mark(self, id):
        return self.timeline.mark(id)

    @contextlib.contextmanager
    def causing(self, expectation):
        assert expectation not in self.timeline
        promised_occurrence = ['ONLY VALID AFTER END OF BLOCK!']
        yield promised_occurrence
        occ = self.wait_until(expectation)
        promised_occurrence[:] = (occ,)

    def handshake(self):
        """Performs the handshake that establishes the debug session.

        After this method returns, ptvsd is not running any code yet, but it is
        ready to accept any configuration requests (e.g. for initial breakpoints).
        Once initial configuration is complete, start_debugging() should be called
        to finalize the configuration stage, and start running code.
        """

        with self.causing(Event('initialized', {})):
            self.send_request('initialize', {'adapterID': 'test'}).wait_for_response()

    def start_debugging(self, arguments=None, force_threads=True):
        """Finalizes the configuration stage, and issues a 'launch' or an 'attach' request
        to start running code under debugger, passing arguments through.

        After this method returns, ptvsd is running the code in the script file or module
        that was specified in run().
        """

        request = 'launch' if self.method == 'launch' else 'attach'
        self.send_request(request, arguments).wait_for_response()
        if force_threads:
            self.send_request('threads').wait_for_response()
        self.send_request('configurationDone').wait_for_response()

    def _process_event(self, channel, event, body):
        self.timeline.record_event(event, body)
        if event == 'terminated':
            self.channel.close()

    def _process_response(self, request, response):
        body = response.body if response.success else RequestFailure(response.error_message)
        self.timeline.record_response(request, body)
        assert Response(request, body) in self.timeline

    def _process_request(self, channel, command, arguments):
        assert False, 'ptvsd should not be sending requests.'

    def wait_until(self, expectation):
        return self.timeline.wait_until(expectation)

    def history(self):
        return self.timeline.history