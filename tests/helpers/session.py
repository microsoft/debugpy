# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

from collections import namedtuple
import os
import platform
import psutil
import pytest
import socket
import subprocess
import sys
import threading
import time
import traceback

import ptvsd
import ptvsd.__main__
from ptvsd.messaging import JsonIOStream, JsonMessageChannel, MessageHandlers

import tests.helpers
from . import colors, debuggee, print
from .messaging import LoggingJsonStream
from .pattern import ANY
from .printer import wait_for_output
from .timeline import Timeline, Event, Response

PTVSD_PORT = tests.helpers.get_unique_port(5678)
PTVSD_ENABLE_KEY = 'PTVSD_ENABLE_ATTACH'
PTVSD_HOST_KEY = 'PTVSD_TEST_HOST'
PTVSD_PORT_KEY = 'PTVSD_TEST_PORT'


class DebugSession(object):
    WAIT_FOR_EXIT_TIMEOUT = 10
    BACKCHANNEL_TIMEOUT = 20

    StopInfo = namedtuple('StopInfo', 'thread_stopped, stacktrace, thread_id, frame_id')

    def __init__(self, start_method='launch', ptvsd_port=None, pid=None):
        assert start_method in ('launch', 'attach_pid', 'attach_socket_cmdline', 'attach_socket_import')
        assert ptvsd_port is None or start_method.startswith('attach_socket_')

        print('New debug session with method %r' % str(start_method))

        self.target = ('code', 'print("OK")')
        self.start_method = start_method
        self.start_method_args = {}
        self.no_debug = False
        self.ptvsd_port = ptvsd_port or PTVSD_PORT
        self.multiprocess = False
        self.multiprocess_port_range = None
        self.debug_options = ['RedirectOutput']
        self.path_mappings = []
        self.success_exitcodes = None
        self.rules = []
        self.env = os.environ.copy()
        self.env['PYTHONPATH'] = os.path.dirname(debuggee.__file__)
        self.cwd = None
        self.expected_returncode = 0
        self.program_args = []
        self.log_dir = None

        self.is_running = False
        self.process = None
        self.pid = pid
        self.psutil_process = psutil.Process(self.pid) if self.pid else None
        self.kill_ptvsd = True
        self.skip_capture = False
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
        self.perform_handshake = True
        self.use_backchannel = False

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
        self.observe_all = self.timeline.observe_all

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        was_final = self.timeline.is_final
        self.close()
        assert exc_type is not None or was_final, (
            'Session timeline must be finalized before session goes out of scope at the end of the '
            'with-statement. Use wait_for_exit(), wait_for_termination(), or wait_for_disconnect() '
            'as appropriate.'
        )

    def __contains__(self, expectation):
        return expectation in self.timeline

    @property
    def ignore_unobserved(self):
        return self.timeline.ignore_unobserved

    @ignore_unobserved.setter
    def ignore_unobserved(self, value):
        self.timeline.ignore_unobserved = value

    def close(self):
        if self.socket:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
                print('Closed socket to ptvsd#%d' % self.ptvsd_port)
            except socket.error as ex:
                print('Error while closing socket to ptvsd#%d: %s' % (self.ptvsd_port, str(ex)))
                self.socket = None

        if self.server_socket:
            try:
                self.server_socket.shutdown(socket.SHUT_RDWR)
                print('Closed server socket to ptvsd#%d' % self.ptvsd_port)
            except socket.error as ex:
                print('Error while closing server socket to ptvsd#%d: %s' % (self.ptvsd_port, str(ex)))
                self.server_socket = None

        if self.backchannel_socket:
            try:
                self.backchannel_socket.shutdown(socket.SHUT_RDWR)
                print('Closed backchannel to ptvsd#%d' % self.backchannel_port)
            except socket.error as ex:
                print('Error while closing backchannel socket to ptvsd#%d: %s' % (self.ptvsd_port, str(ex)))
                self.backchannel_socket = None

        if self.process:
            if self.kill_ptvsd:
                try:
                    self._kill_process_tree()
                    print('Killed ptvsd process tree %d' % self.pid)
                except:
                    print('Error killing ptvsd process tree %d' % self.pid)
                    traceback.print_exc()
                    pass

            # Clean up pipes to avoid leaking OS handles.
            try:
                self.process.stdin.close()
            except:
                pass
            try:
                self.process.stdout.close()
            except:
                pass
            try:
                self.process.stderr.close()
            except:
                pass

        self._wait_for_remaining_output()

    def _get_argv_for_attach_using_import(self):
        argv = [sys.executable]
        return argv

    def _get_argv_for_launch(self):
        argv = [sys.executable]
        argv += [os.path.dirname(ptvsd.__file__)]
        argv += ['--client']
        argv += ['--host', 'localhost', '--port', str(self.ptvsd_port)]
        return argv

    def _get_argv_for_attach_using_cmdline(self):
        argv = [sys.executable]
        argv += [os.path.dirname(ptvsd.__file__)]
        argv += ['--wait']
        argv += ['--host', 'localhost', '--port', str(self.ptvsd_port)]
        return argv

    def _get_argv_for_attach_using_pid(self):
        argv = [sys.executable]
        argv += [os.path.dirname(ptvsd.__file__)]
        argv += ['--client', '--host', 'localhost', '--port', str(self.ptvsd_port)]
        # argv += ['--pid', '<pid>']  # pid value to be appended later
        return argv

    def _get_target(self):
        argv = []
        run_as, path_or_code = self.target
        if run_as == 'file':
            assert os.path.isfile(path_or_code)
            argv += [path_or_code]
        elif run_as == 'module':
            if os.path.isfile(path_or_code) or os.path.isdir(path_or_code):
                self.env['PYTHONPATH'] += os.pathsep + os.path.dirname(path_or_code)
                try:
                    module = path_or_code[len(os.path.dirname(path_or_code)) + 1:-3]
                except Exception:
                    module = 'code_to_debug'
                argv += ['-m', module]
            else:
                argv += ['-m', path_or_code]
        elif run_as == 'code':
            if os.path.isfile(path_or_code):
                with open(path_or_code, 'r') as f:
                    code = f.read()
                argv += ['-c', code]
            else:
                argv += ['-c', path_or_code]
        else:
            pytest.fail()
        return argv

    def _setup_session(self, **kwargs):
        self.ignore_unobserved += [
            Event('thread', ANY.dict_with({'reason': 'started'})),
            Event('module')
        ] + kwargs.pop('ignore_unobserved', [])

        self.env.update(kwargs.pop('env', {}))
        self.start_method_args.update(kwargs.pop('args', {}))

        self.path_mappings += kwargs.pop('path_mappings', [])
        self.debug_options += kwargs.pop('debug_options', [])
        self.program_args += kwargs.pop('program_args', [])
        self.rules += kwargs.pop('rules', [])

        for k, v in kwargs.items():
            setattr(self, k, v)

        assert self.start_method in ('launch', 'attach_pid', 'attach_socket_cmdline', 'attach_socket_import')
        assert len(self.target) == 2
        assert self.target[0] in ('file', 'module', 'code')

    def initialize(self, **kwargs):
        """Spawns ptvsd using the configured method, telling it to execute the
        provided Python file, module, or code, and establishes a message channel
        to it.

        If use_backchannel is True, calls self.setup_backchannel() before returning.

        If perform_handshake is True, calls self.handshake() before returning.
        """
        self._setup_session(**kwargs)
        print('Initializing debug session for ptvsd#%d' % self.ptvsd_port)
        dbg_argv = []
        usr_argv = []
        if self.start_method == 'launch':
            self._listen()
            dbg_argv += self._get_argv_for_launch()
        elif self.start_method == 'attach_socket_cmdline':
            dbg_argv += self._get_argv_for_attach_using_cmdline()
        elif self.start_method == 'attach_socket_import':
            dbg_argv += self._get_argv_for_attach_using_import()
            # TODO: Remove adding to python path after enabling TOX
            ptvsd_path = os.path.dirname(os.path.dirname(ptvsd.__main__.__file__))
            self.env['PYTHONPATH'] = ptvsd_path + os.pathsep + self.env['PYTHONPATH']
            self.env[PTVSD_ENABLE_KEY] = '1'
            self.env[PTVSD_HOST_KEY] = 'localhost'
            self.env[PTVSD_PORT_KEY] = str(self.ptvsd_port)
        elif self.start_method == 'attach_pid':
            self._listen()
            dbg_argv += self._get_argv_for_attach_using_pid()
        else:
            pytest.fail()

        if self.log_dir:
            dbg_argv += ['--log-dir', self.log_dir]

        if self.no_debug:
            dbg_argv += ['--nodebug']

        if self.start_method == 'attach_pid':
            usr_argv += [sys.executable]
            usr_argv += self._get_target()
        else:
            dbg_argv += self._get_target()

        if self.program_args:
            if self.start_method == 'attach_pid':
                usr_argv += list(self.program_args)
            else:
                dbg_argv += list(self.program_args)

        if self.multiprocess and 'Multiprocess' not in self.debug_options:
            self.debug_options += ['Multiprocess']

        if self.use_backchannel:
            self.setup_backchannel()
        if self.backchannel_port:
            self.env['PTVSD_BACKCHANNEL_PORT'] = str(self.backchannel_port)

        print('ptvsd: %s' % ptvsd.__file__)
        print('Start method: %s' % self.start_method)
        print('Target: (%s) %s' % self.target)
        print('Current directory: %s' % self.cwd)
        print('PYTHONPATH: %s' % self.env['PYTHONPATH'])
        if self.start_method == 'attach_pid':
            print('Spawning %r' % usr_argv)
        else:
            print('Spawning %r' % dbg_argv)

        spawn_args = usr_argv if self.start_method == 'attach_pid' else dbg_argv

        # ensure env is all string, this is needed for python 2.7 on windows
        temp_env = {}
        for k, v in self.env.items():
            temp_env[str(k)] = str(v)

        self.process = subprocess.Popen(spawn_args, env=temp_env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=self.cwd)
        self.pid = self.process.pid
        self.psutil_process = psutil.Process(self.pid)
        self.is_running = True
        # watchdog.create(self.pid)

        if not self.skip_capture:
            self._capture_output(self.process.stdout, 'OUT')
            self._capture_output(self.process.stderr, 'ERR')

        if self.start_method == 'attach_pid':
            # This is a temp process spawned to inject debugger into the
            # running process
            dbg_argv += ['--pid', str(self.pid)]
            print('Spawning %r' % dbg_argv)
            temp_process = subprocess.Popen(dbg_argv)
            print('temp process has pid=%d' % temp_process.pid)

        if self.start_method not in ('launch', 'attach_pid'):
            self.connect()
        self.connected.wait()
        assert self.ptvsd_port
        assert self.socket
        print('ptvsd#%d has pid=%d' % (self.ptvsd_port, self.pid))

        telemetry = self.timeline.wait_for_next(Event('output'))
        assert telemetry == Event('output', {
            'category': 'telemetry',
            'output': 'ptvsd',
            'data': {'version': ptvsd.__version__},
        })

        if self.perform_handshake:
            return self.handshake()

    def wait_for_disconnect(self, close=True):
        """Waits for the connected ptvsd process to disconnect.
        """

        print(colors.LIGHT_MAGENTA + 'Waiting for ptvsd#%d to disconnect' % self.ptvsd_port + colors.RESET)

        # self.channel.wait()
        self.channel.close()

        self.timeline.finalize()
        if close:
            self.timeline.close()

        wait_for_output()

    def wait_for_termination(self):
        print(colors.LIGHT_MAGENTA + 'Waiting for ptvsd#%d to terminate' % self.ptvsd_port + colors.RESET)

        # BUG: ptvsd sometimes exits without sending 'terminate' or 'exited', likely due to
        # https://github.com/Microsoft/ptvsd/issues/530. So rather than wait for them, wait until
        # we disconnect, then check those events for proper body only if they're actually present.

        self.wait_for_disconnect(close=False)

        if Event('exited') in self:
            expected_returncode = self.expected_returncode

            # Due to https://github.com/Microsoft/ptvsd/issues/1278, exit code is not recorded
            # in the "exited" event correctly in attach scenarios on Windows.
            if self.start_method == 'attach_socket_import' and platform.system() == 'Windows':
                expected_returncode = ANY.int

            self.expect_realized(Event('exited', {'exitCode': expected_returncode}))

        if Event('terminated') in self:
            self.expect_realized(Event('exited') >> Event('terminated', {}))

        self.timeline.close()
        wait_for_output()

    def wait_for_exit(self):
        """Waits for the spawned ptvsd process to exit. If it doesn't exit within
        WAIT_FOR_EXIT_TIMEOUT seconds, forcibly kills the process. After the process
        exits, validates its return code to match expected_returncode.
        """

        if not self.is_running:
            return

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
        returncode = self.psutil_process.wait()

        assert returncode == self.expected_returncode

        self.is_running = False
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
            except socket.error as ex:
                print('Error connecting to ptvsd#%d: %s' % (self.ptvsd_port, str(ex)))
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

        request = 'launch' if self.start_method == 'launch' else 'attach'
        self.start_method_args.update({
            'debugOptions': self.debug_options,
            'pathMappings': self.path_mappings,
            'rules': self.rules,
        })
        if self.success_exitcodes is not None:
            self.start_method_args['successExitCodes'] = self.success_exitcodes
        launch_or_attach_request = self.send_request(request, self.start_method_args)

        if self.no_debug:
            launch_or_attach_request.wait_for_response()
        else:
            self.wait_for_next(Event('process') & Response(launch_or_attach_request))

            # 'process' is expected right after 'launch' or 'attach'.
            self.expect_new(Event('process', {
                'name': ANY.str,
                'isLocalProcess': True,
                'startMethod': 'launch' if self.start_method == 'launch' else 'attach',
                'systemProcessId': self.pid if self.pid is not None else ANY.int,
            }))

            # Issue 'threads' so that we get the 'thread' event for the main thread now,
            # rather than at some random time later during the test.
            # Note: it's actually possible that the 'thread' event was sent before the 'threads'
            # request (although the 'threads' will force 'thread' to be sent if it still wasn't).
            self.send_request('threads').wait_for_response()
            self.expect_realized(Event('thread'))

    def start_debugging(self, freeze=True):
        """Finalizes the configuration stage, and issues a 'configurationDone' request
        to start running code under debugger.

        After this method returns, ptvsd is running the code in the script file or module
        that was specified via self.target.
        """

        configurationDone_request = self.send_request('configurationDone')

        start = self.wait_for_next(Response(configurationDone_request))

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

        backchannel_thread = threading.Thread(target=self._backchannel_worker, name='bchan#%d listener' % self.ptvsd_port)
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

    def set_breakpoints(self, path, lines=()):
        return self.send_request('setBreakpoints', arguments={
                'source': {'path': path},
                'breakpoints': [{'line': bp_line} for bp_line in lines],
            }).wait_for_response().body.get('breakpoints', None)

    def wait_for_thread_stopped(self, reason=ANY, text=None, description=None):
        thread_stopped = self.wait_for_next(Event('stopped', ANY.dict_with({'reason': reason})))

        if text is not None:
            assert text == thread_stopped.body['text']

        if description is not None:
            assert description == thread_stopped.body['description']

        tid = thread_stopped.body['threadId']

        assert thread_stopped.body['allThreadsStopped']
        assert thread_stopped.body['preserveFocusHint'] == \
            (thread_stopped.body['reason'] not in ['step', 'exception', 'breakpoint', 'entry'])

        assert tid is not None

        resp_stacktrace = self.send_request('stackTrace', arguments={
            'threadId': tid,
        }).wait_for_response()
        assert resp_stacktrace.body['totalFrames'] > 0
        frames = resp_stacktrace.body['stackFrames']

        fid = frames[0]['id']

        return self.StopInfo(thread_stopped, resp_stacktrace, tid, fid)

    def connect_to_child_session(self, ptvsd_subprocess):
        child_port = ptvsd_subprocess.body['port']
        assert child_port != 0

        child_session = DebugSession(start_method='attach_socket_cmdline', ptvsd_port=child_port)
        try:
            child_session.ignore_unobserved = self.ignore_unobserved
            child_session.debug_options = self.debug_options
            child_session.rules = self.rules
            child_session.connect()
            child_session.handshake()
        except:
            child_session.close()
            raise
        else:
            return child_session

    def connect_to_next_child_session(self):
        ptvsd_subprocess = self.wait_for_next(Event('ptvsd_subprocess'))
        return self.connect_to_child_session(ptvsd_subprocess)

    def get_stdout_as_string(self):
        return b''.join(self.output_data['OUT'])

    def get_stderr_as_string(self):
        return b''.join(self.output_data['ERR'])

    def connect_with_new_session(self, **kwargs):
        ns = DebugSession(start_method='attach_socket_import', ptvsd_port=self.ptvsd_port)
        try:
            ns._setup_session(**kwargs)
            ns.ignore_unobserved = self.ignore_unobserved
            ns.debug_options = self.debug_options
            ns.rules = self.rules

            ns.pid = self.pid
            ns.process = self.process
            ns.psutil_process = psutil.Process(ns.pid)
            ns.is_running = True

            ns.connect()
            ns.connected.wait()
            ns.handshake()
        except:
            ns.close()
        else:
            return ns
