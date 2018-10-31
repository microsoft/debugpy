# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import os
import psutil
import socket
import subprocess
import sys
import threading
import time
import traceback

import ptvsd
import ptvsd.__main__
from ptvsd.messaging import JsonIOStream, JsonMessageChannel, MessageHandlers

from . import colors, debuggee, print, watchdog
from .messaging import LoggingJsonStream
from .pattern import ANY
from .timeline import Timeline, Event, Response


class DebugSession(object):
    WAIT_FOR_EXIT_TIMEOUT = 5
    BACKCHANNEL_TIMEOUT = 15

    def __init__(self, method='launch', ptvsd_port=None, pid=None):
        assert method in ('launch', 'attach_pid', 'attach_socket')
        assert ptvsd_port is None or method == 'attach_socket'

        print('New debug session with method %r' % method)

        self.method = method
        self.ptvsd_port = ptvsd_port or 5678
        self.multiprocess = False
        self.multiprocess_port_range = None
        self.debug_options = ['RedirectOutput']
        self.env = os.environ.copy()
        self.env['PYTHONPATH'] = os.path.dirname(debuggee.__file__)
        self.cwd = None
        self.expected_returncode = 0
        self.program_args = []

        self.is_running = False
        self.process = None
        self.pid = pid
        self.psutil_process = psutil.Process(self.pid) if self.pid else None
        self.socket = None
        self.server_socket = None
        self.connected = threading.Event()
        self.backchannel_socket = None
        self.backchannel_port = None
        self.backchannel_established = threading.Event()
        self._output_capture_threads = []
        self.output_data = {'OUT': [], 'ERR': []}

        self.timeline = Timeline(ignore_unobserved=[
            Event('output'),
            Event('thread', ANY.dict_with({'reason': 'exited'}))
        ])
        self.timeline.freeze()

        # Expose some common members of timeline directly - these should be the ones
        # that are the most straightforward to use, and are difficult to use incorrectly.
        # Conversely, most tests should restrict themselves to this subset of the API,
        # and avoid calling members of timeline directly unless there is a good reason.
        self.new = self.timeline.new
        self.observe = self.timeline.observe
        self.wait_for_next = self.timeline.wait_for_next
        self.proceed = self.timeline.proceed
        self.expect_new = self.timeline.expect_new
        self.expect_realized = self.timeline.expect_realized
        self.all_occurrences_of = self.timeline.all_occurrences_of

    def add_file_to_pythonpath(self, filename):
        self.env['PYTHONPATH'] += os.pathsep + os.path.dirname(filename)

    def __contains__(self, expectation):
        return expectation in self.timeline

    @property
    def ignore_unobserved(self):
        return self.timeline.ignore_unobserved

    @ignore_unobserved.setter
    def ignore_unobserved(self, value):
        self.timeline.ignore_unobserved = value

    def stop(self):
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

        if self.process:
            try:
                self._kill_process_tree()
            except:
                traceback.print_exc()
                pass

        self._wait_for_remaining_output()

    def prepare_to_run(self, perform_handshake=True, filename=None, module=None, code=None, backchannel=False):
        """Spawns ptvsd using the configured method, telling it to execute the
        provided Python file, module, or code, and establishes a message channel
        to it.

        If backchannel is True, calls self.setup_backchannel() before returning.

        If perform_handshake is True, calls self.handshake() before returning.
        """

        argv = [sys.executable]
        if self.method != 'attach_pid':
            argv += [ptvsd.__main__.__file__]

        if self.method == 'attach_socket':
            argv += ['--wait']
        else:
            self._listen()
            argv += ['--client']
        argv += ['--host', 'localhost', '--port', str(self.ptvsd_port)]

        if self.multiprocess and 'Multiprocess' not in self.debug_options:
            self.debug_options += ['Multiprocess']

        if self.multiprocess_port_range:
            argv += ['--multiprocess-port-range', '%d-%d' % self.multiprocess_port_range]

        if filename:
            assert not module and not code
            argv += [filename]
        elif module:
            assert not filename and not code
            argv += ['-m', module]
        elif code:
            assert not filename and not module
            argv += ['-c', code]

        if self.program_args:
            argv += list(self.program_args)

        if backchannel:
            self.setup_backchannel()
        if self.backchannel_port:
            self.env['PTVSD_BACKCHANNEL_PORT'] = str(self.backchannel_port)

        print('Current directory: %s' % os.getcwd())
        print('PYTHONPATH: %s' % self.env['PYTHONPATH'])
        print('Spawning %r' % argv)
        self.process = subprocess.Popen(argv, env=self.env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=self.cwd)
        self.pid = self.process.pid
        self.psutil_process =  psutil.Process(self.pid)
        self.is_running = True
        watchdog.create(self.pid)

        self._capture_output(self.process.stdout, 'OUT')
        self._capture_output(self.process.stderr, 'ERR')

        if self.method == 'attach_socket':
            self.connect()
        self.connected.wait()
        assert self.ptvsd_port
        assert self.socket
        print('ptvsd#%d has pid=%d' % (self.ptvsd_port, self.pid))

        telemetry = self.timeline.wait_for_next(Event('output'))
        assert telemetry == Event('output', {
            'category': 'telemetry',
            'output': 'ptvsd',
            'data': {'version': ptvsd.__version__}
        })

        if perform_handshake:
            return self.handshake()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.wait_for_exit()

    def wait_for_disconnect(self, close=True):
        """Waits for the connected ptvsd process to disconnect.
        """

        print(colors.LIGHT_MAGENTA + 'Waiting for ptvsd#%d to disconnect' % self.ptvsd_port + colors.RESET)

        self.channel.wait()
        self.channel.close()

        self.timeline.finalize()
        if close:
            self.timeline.close()

    def wait_for_termination(self):
        print(colors.LIGHT_MAGENTA + 'Waiting for ptvsd#%d to terminate' % self.ptvsd_port + colors.RESET)

        # BUG: ptvsd sometimes exits without sending 'terminate' or 'exited', likely due to
        # https://github.com/Microsoft/ptvsd/issues/530. So rather than wait for them, wait until
        # we disconnect, then check those events for proper body only if they're actually present.

        self.wait_for_disconnect(close=False)

        if sys.version_info < (3,) or Event('exited') in self:
            self.expect_realized(Event('exited', {'exitCode': self.expected_returncode}))

        if sys.version_info < (3,) or Event('terminated') in self:
            self.expect_realized(Event('exited') >> Event('terminated', {}))

        self.timeline.close()

    def wait_for_exit(self):
        """Waits for the spawned ptvsd process to exit. If it doesn't exit within
        WAIT_FOR_EXIT_TIMEOUT seconds, forcibly kills the process. After the process
        exits, validates its return code to match expected_returncode.
        """

        assert self.psutil_process is not None

        def kill():
            time.sleep(self.WAIT_FOR_EXIT_TIMEOUT)
            if self.is_running:
                print('ptvsd#%r (pid=%d) timed out, killing it' % (self.ptvsd_port, self.pid))
                self._kill_process_tree()

        kill_thread = threading.Thread(target=kill, name='ptvsd#%r watchdog (pid=%d)' % (self.ptvsd_port, self.pid))
        kill_thread.daemon = True
        kill_thread.start()

        print(colors.LIGHT_MAGENTA + 'Waiting for ptvsd#%d (pid=%d) to terminate' % (self.ptvsd_port, self.pid) + colors.RESET)
        self.psutil_process.wait()

        self.is_running = False

        if self.process is not None:
            self.process.wait()
            assert self.process.returncode == self.expected_returncode

        self.wait_for_termination()

    def _kill_process_tree(self):
        assert self.psutil_process is not None
        procs = [self.psutil_process]
        try:
            procs += self.psutil_process.children(recursive=True)
        except:
            pass
        for p in procs:
            try:
                p.kill()
            except:
                pass

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

    def send_request(self, command, arguments=None, proceed=True):
        if self.timeline.is_frozen and proceed:
            self.proceed()

        request = self.timeline.record_request(command, arguments)
        request.sent = self.channel.send_request(command, arguments)
        request.sent.on_response(lambda response: self._process_response(request, response))

        def causing(*expectations):
            for exp in expectations:
                (request >> exp).wait()
            return request
        request.causing = causing

        return request

    def handshake(self):
        """Performs the handshake that establishes the debug session ('initialized'
        and 'launch' or 'attach').

        After this method returns, ptvsd is not running any code yet, but it is
        ready to accept any configuration requests (e.g. for initial breakpoints).
        Once initial configuration is complete, start_debugging() should be called
        to finalize the configuration stage, and start running code.
        """

        self.send_request('initialize', {'adapterID': 'test'}).wait_for_response()
        self.wait_for_next(Event('initialized', {}))

        request = 'launch' if self.method == 'launch' else 'attach'
        self.send_request(request, {'debugOptions': self.debug_options}).wait_for_response()

        # Issue 'threads' so that we get the 'thread' event for the main thread now,
        # rather than at some random time later during the test.
        (self.send_request('threads')
            .causing(Event('thread'))
            .wait_for_response())

    def start_debugging(self, freeze=True):
        """Finalizes the configuration stage, and issues a 'configurationDone' request
        to start running code under debugger.

        After this method returns, ptvsd is running the code in the script file or module
        that was specified in prepare_to_run().
        """

        configurationDone_request = self.send_request('configurationDone')

        # The relative ordering of 'process' and 'configurationDone' is not deterministic.
        # (implementation varies depending on whether it's launch or attach, but in any
        # case, it is an implementation detail).
        start = self.wait_for_next(Event('process') & Response(configurationDone_request))

        self.expect_new(Event('process', {
            'name': ANY.str,
            'isLocalProcess': True,
            'startMethod': 'launch' if self.method == 'launch' else 'attach',
            'systemProcessId': self.pid if self.pid is not None else ANY.int,
        }))

        if not freeze:
            self.proceed()

        return start

    def _process_event(self, event):
        self.timeline.record_event(event.event, event.body, block=False)

    def _process_response(self, request_occ, response):
        self.timeline.record_response(request_occ, response.body, block=False)

    def _process_request(self, request):
        assert False, 'ptvsd should not be sending requests.'

    def setup_backchannel(self):
        self.backchannel_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.backchannel_socket.settimeout(self.BACKCHANNEL_TIMEOUT)
        self.backchannel_socket.bind(('localhost', 0))
        _, self.backchannel_port = self.backchannel_socket.getsockname()
        self.backchannel_socket.listen(0)

        backchannel_thread = threading.Thread(target=self._backchannel_worker, name='bchan#%d listener'  % self.ptvsd_port)
        backchannel_thread.daemon = True
        backchannel_thread.start()

    def _backchannel_worker(self):
        print('Listening for incoming backchannel connection for bchan#%d' % self.ptvsd_port)
        sock = None

        try:
            sock, _ = self.backchannel_socket.accept()
        except socket.timeout:
            assert sock is not None, 'bchan#%r timed out!' % self.ptvsd_port

        print('Incoming bchan#%d backchannel connection accepted' % self.ptvsd_port)
        sock.settimeout(None)
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
        self.timeline.unfreeze()
        t = self.timeline.mark(('sending', value))
        self.backchannel.write_json(value)
        return t

    def _capture_output(self, pipe, name):
        def _output_worker():
            while True:
                try:
                    line = pipe.readline()
                    if not line:
                        break
                    self.output_data[name].append(line)
                except Exception:
                    break
                else:
                    prefix = 'ptvsd#%d %s ' % (self.ptvsd_port, name)
                    line = colors.LIGHT_BLUE + prefix + colors.RESET + line.decode('utf-8')
                    print(line, end='')

        thread = threading.Thread(target=_output_worker, name='ptvsd#%r %s' % (self.ptvsd_port, name))
        thread.daemon = True
        thread.start()
        self._output_capture_threads.append(thread)

    def _wait_for_remaining_output(self):
        for thread in self._output_capture_threads:
            thread.join()
