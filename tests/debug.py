# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import collections
import itertools
import os
import platform
import psutil
import py.path
import pytest
import socket
import subprocess
import sys
import threading
import time

import ptvsd
from ptvsd.common import compat, fmt, log, messaging
import tests
from tests import code, net
from tests.patterns import some
from tests.timeline import Timeline, Event, Request, Response

PTVSD_DIR = py.path.local(ptvsd.__file__) / ".."
PTVSD_PORT = net.get_test_server_port(5678, 5800)

# Added to the environment variables of every new debug.Session - after copying
# os.environ(), but before setting any session-specific variables.
PTVSD_ENV = {
}

# Code that is injected into the debuggee process when it does `import debug_me`,
# and start_method is attach_socket_*
PTVSD_DEBUG_ME = """
import ptvsd
ptvsd.enable_attach(("localhost", {ptvsd_port}))
ptvsd.wait_for_attach()
"""


StopInfo = collections.namedtuple('StopInfo', [
    'body',
    'frames',
    'thread_id',
    'frame_id',
])


class Session(object):
    WAIT_FOR_EXIT_TIMEOUT = 10
    """Timeout used by wait_for_exit() before it kills the ptvsd process.
    """

    START_METHODS = {
        'launch',  # ptvsd --client ... foo.py
        'attach_socket_cmdline',  #  ptvsd ... foo.py
        'attach_socket_import',  #  python foo.py (foo.py must import debug_me)
        'attach_pid',  # python foo.py && ptvsd ... --pid
        'custom_client',  # python foo.py (foo.py has to manually call ptvsd.attach)
        'custom_server',  # python foo.py (foo.py has to manually call ptvsd.enable_attach)
    }

    DEBUG_ME_START_METHODS = {"attach_socket_import"}
    """Start methods that require import debug_me."""

    _counter = itertools.count(1)

    def __init__(self, start_method='launch', ptvsd_port=None, pid=None):
        assert start_method in self.START_METHODS
        assert ptvsd_port is None or start_method.startswith('attach_socket_')

        self.id = next(self._counter)
        log.info('Starting debug session {0} via {1!r}', self.id, start_method)

        self.lock = threading.RLock()
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
        self.cwd = None
        self.expected_returncode = 0
        self.program_args = []
        self.log_dir = None
        self._before_connect = lambda: None

        self.env = os.environ.copy()
        self.env.update(PTVSD_ENV)
        self.env['PYTHONPATH'] = (tests.root / "DEBUGGEE_PYTHONPATH").strpath
        self.env['PTVSD_SESSION_ID'] = str(self.id)

        self.is_running = False
        self.process = None
        self.pid = pid
        self.psutil_process = psutil.Process(self.pid) if self.pid else None
        self.kill_ptvsd = True
        self.socket = None
        self.server_socket = None
        self.connected = threading.Event()
        self.backchannel = None

        self.capture_output = True
        self.captured_output = CapturedOutput(self)

        self.timeline = Timeline(ignore_unobserved=[
            Event('output'),
            Event('thread', some.dict.containing({'reason': 'exited'}))
        ])
        self.timeline.freeze()
        self.perform_handshake = True

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

    def __str__(self):
        return fmt("ptvsd-{0}", self.id)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # If we're exiting a failed test, make sure that all output from the debuggee
        # process has been received and logged, before we close the sockets and kill
        # the debuggee process. In success case, wait_for_exit() takes care of that.
        if exc_type is not None:
            # If it failed in the middle of the test, the debuggee process might still
            # be alive, and waiting for the test to tell it to continue. In this case,
            # it will never close its stdout/stderr, so use a reasonable timeout here.
            self.captured_output.wait(timeout=1)

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
        with self.lock:
            if self.socket:
                try:
                    self.socket.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                try:
                    self.socket.close()
                except Exception:
                    pass
                self.socket = None
                log.debug('Closed socket to {0}', self)

            if self.server_socket:
                try:
                    self.server_socket.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                try:
                    self.server_socket.close()
                except Exception:
                    pass
                self.server_socket = None
                log.debug('Closed server socket for {0}', self)

        if self.backchannel:
            self.backchannel.close()
            self.backchannel = None

        if self.process:
            if self.kill_ptvsd:
                try:
                    self._kill_process_tree()
                except Exception:
                    log.exception('Error killing {0} (pid={1}) process tree', self, self.pid)
                log.info('Killed {0} (pid={1}) process tree', self, self.pid)

            # Clean up pipes to avoid leaking OS handles.
            try:
                self.process.stdin.close()
            except Exception:
                pass
            try:
                self.process.stdout.close()
            except Exception:
                pass
            try:
                self.process.stderr.close()
            except Exception:
                pass

        self.captured_output.wait()

    def _get_argv_for_attach_using_import(self):
        argv = [sys.executable]
        return argv

    def _get_argv_for_launch(self):
        argv = [sys.executable]
        argv += [PTVSD_DIR.strpath]
        argv += ['--client']
        argv += ['--host', 'localhost', '--port', str(self.ptvsd_port)]
        return argv

    def _get_argv_for_attach_using_cmdline(self):
        argv = [sys.executable]
        argv += [PTVSD_DIR.strpath]
        argv += ['--wait']
        argv += ['--host', 'localhost', '--port', str(self.ptvsd_port)]
        return argv

    def _get_argv_for_attach_using_pid(self):
        argv = [sys.executable]
        argv += [PTVSD_DIR.strpath]
        argv += ['--client', '--host', 'localhost', '--port', str(self.ptvsd_port)]
        # argv += ['--pid', '<pid>']  # pid value to be appended later
        return argv

    def _get_argv_for_custom_server(self):
        return [sys.executable]

    def _get_argv_for_custom_client(self):
        return [sys.executable]

    def _validate_pyfile(self, filename):
        assert os.path.isfile(filename)
        with open(filename, "rb") as f:
            code = f.read()
            if self.start_method in self.DEBUG_ME_START_METHODS:
                assert b"debug_me" in code, fmt(
                    "{0} is started via {1}, but it doesn't import debug_me.",
                    filename,
                    self.start_method,
                )

            return code

    def _get_target(self):
        argv = []
        run_as, path_or_code = self.target
        if isinstance(path_or_code, py.path.local):
            path_or_code = path_or_code.strpath
        if run_as == 'file':
            self._validate_pyfile(path_or_code)
            argv += [path_or_code]
        elif run_as == 'module':
            if os.path.isfile(path_or_code):
                self._validate_pyfile(path_or_code)
            if os.path.isfile(path_or_code) or os.path.isdir(path_or_code):
                self.env['PYTHONPATH'] += os.pathsep + os.path.dirname(path_or_code)
                try:
                    module = path_or_code[(len(os.path.dirname(path_or_code)) + 1) : -3]
                except Exception:
                    module = 'code_to_debug'
                argv += ['-m', module]
            else:
                argv += ['-m', path_or_code]
        elif run_as == 'code':
            if os.path.isfile(path_or_code):
                path_or_code = self._validate_pyfile(path_or_code)
            argv += ['-c', path_or_code]
        else:
            pytest.fail()
        return argv

    def _setup_session(self, **kwargs):
        self.ignore_unobserved += [
            Event('thread', some.dict.containing({'reason': 'started'})),
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

        assert self.start_method in self.START_METHODS
        assert len(self.target) == 2
        assert self.target[0] in ('file', 'module', 'code')

    def setup_backchannel(self):
        """Creates a BackChannel object associated with this Session, and returns it.

        The debuggee must import backchannel to establish the connection.
        """
        assert self.process is None, (
            "setup_backchannel() must be called before initialize()"
        )
        self.backchannel = BackChannel(self)
        return self.backchannel

    def before_connect(self, func):
        """Registers a function to be invoked by initialize() before connecting to
        the debuggee, or before waiting for an incoming connection, but after all
        the session parameters (port number etc) are determined."""
        self._before_connect = func

    def initialize(self, **kwargs):
        """Spawns ptvsd using the configured method, telling it to execute the
        provided Python file, module, or code, and establishes a message channel
        to it.

        If perform_handshake is True, calls self.handshake() before returning.
        """

        self._setup_session(**kwargs)
        start_method = self.start_method

        log.info('Initializing debug session for {0}', self)
        dbg_argv = []
        usr_argv = []

        if start_method == 'launch':
            self._listen()
            dbg_argv += self._get_argv_for_launch()
        elif start_method == 'attach_socket_cmdline':
            dbg_argv += self._get_argv_for_attach_using_cmdline()
        elif start_method == 'attach_socket_import':
            dbg_argv += self._get_argv_for_attach_using_import()
            # TODO: Remove adding to python path after enabling Tox
            self.env['PYTHONPATH'] = (PTVSD_DIR / "..").strpath + os.pathsep + self.env['PYTHONPATH']
            self.env['PTVSD_DEBUG_ME'] = fmt(PTVSD_DEBUG_ME, ptvsd_port=self.ptvsd_port)
        elif start_method == 'attach_pid':
            self._listen()
            dbg_argv += self._get_argv_for_attach_using_pid()
        elif start_method == 'custom_client':
            self._listen()
            dbg_argv += self._get_argv_for_custom_client()
        elif start_method == 'custom_server':
            dbg_argv += self._get_argv_for_custom_server()
        else:
            pytest.fail()

        if self.log_dir:
            dbg_argv += ['--log-dir', self.log_dir]

        if self.no_debug:
            dbg_argv += ['--nodebug']

        if start_method == 'attach_pid':
            usr_argv += [sys.executable]
            usr_argv += self._get_target()
        else:
            dbg_argv += self._get_target()

        if self.program_args:
            if start_method == 'attach_pid':
                usr_argv += list(self.program_args)
            else:
                dbg_argv += list(self.program_args)

        if self.multiprocess and 'Multiprocess' not in self.debug_options:
            self.debug_options += ['Multiprocess']

        if self.backchannel:
            self.backchannel.listen()
            self.env['PTVSD_BACKCHANNEL_PORT'] = str(self.backchannel.port)

        # Normalize args to either bytes or unicode, depending on Python version.
        # Assume that values are filenames - it's usually either that, or numbers.
        make_filename = compat.filename_bytes if sys.version_info < (3,) else compat.filename
        env = {
            compat.force_str(k): make_filename(v)
            for k, v in self.env.items()
        }

        env_str = "\n".join((
            fmt("{0}={1}", env_name, env[env_name])
            for env_name in sorted(env.keys())
        ))

        cwd = self.cwd
        if isinstance(cwd, py.path.local):
            cwd = cwd.strpath

        log.info(
            '{0} will have:\n\n'
            'ptvsd: {1}\n'
            'port: {2}\n'
            'start method: {3}\n'
            'target: ({4}) {5}\n'
            'current directory: {6}\n'
            'environment variables:\n\n{7}',
            self,
            py.path.local(ptvsd.__file__).dirpath(),
            self.ptvsd_port,
            start_method,
            self.target[0],
            self.target[1],
            self.cwd,
            env_str,
        )

        spawn_args = usr_argv if start_method == 'attach_pid' else dbg_argv

        # Normalize args to either bytes or unicode, depending on Python version.
        spawn_args = [make_filename(s) for s in spawn_args]

        log.info('Spawning {0}:\n\n{1}', self, "\n".join((repr(s) for s in spawn_args)))
        self.process = subprocess.Popen(
            spawn_args,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
        )
        self.pid = self.process.pid
        self.psutil_process = psutil.Process(self.pid)
        self.is_running = True
        # watchdog.create(self.pid)

        if self.capture_output:
            self.captured_output.capture(self.process)

        if start_method == 'attach_pid':
            # This is a temp process spawned to inject debugger into the debuggee.
            dbg_argv += ['--pid', str(self.pid)]
            log.info('Spawning {0} attach helper: {1!r}', self, dbg_argv)
            attach_helper = subprocess.Popen(dbg_argv)
            log.info('Spawned {0} attach helper with pid={1}', self, attach_helper.pid)

        self._before_connect()

        if start_method.startswith("attach_socket_") or start_method == "custom_server":
            self.connect()
        self.connected.wait()

        assert self.ptvsd_port
        assert self.socket
        log.info('Spawned {0} with pid={1}', self, self.pid)

        telemetry = self.wait_for_next_event('output')
        assert telemetry == {
            'category': 'telemetry',
            'output': 'ptvsd',
            'data': {'version': some.str},
            #'data': {'version': ptvsd.__version__},
        }

        if self.perform_handshake:
            return self.handshake()

    def wait_for_disconnect(self, close=True):
        """Waits for the connected ptvsd process to disconnect.
        """

        log.info('Waiting for {0} to disconnect', self)

        self.captured_output.wait()
        self.channel.close()
        self.timeline.finalize()
        if close:
            self.timeline.close()

    def wait_for_termination(self, close=False):
        log.info('Waiting for {0} to terminate', self)

        # BUG: ptvsd sometimes exits without sending 'terminate' or 'exited', likely due to
        # https://github.com/Microsoft/ptvsd/issues/530. So rather than wait for them, wait until
        # we disconnect, then check those events for proper body only if they're actually present.

        self.wait_for_disconnect(close=False)

        if Event('exited') in self:
            expected_returncode = self.expected_returncode

            # Due to https://github.com/Microsoft/ptvsd/issues/1278, exit code is not recorded
            # in the "exited" event correctly in attach scenarios on Windows.
            if self.start_method == 'attach_socket_import' and platform.system() == 'Windows':
                expected_returncode = some.int

            self.expect_realized(Event('exited', {'exitCode': expected_returncode}))

        if Event('terminated') in self:
            self.expect_realized(Event('exited') >> Event('terminated', {}))

        if close:
            self.timeline.close()

    def wait_for_exit(self):
        """Waits for the spawned ptvsd process to exit. If it doesn't exit within
        WAIT_FOR_EXIT_TIMEOUT seconds, forcibly kills the process. After the process
        exits, validates its return code to match expected_returncode.
        """

        if not self.is_running:
            return

        assert self.psutil_process is not None

        killed = []
        def kill():
            time.sleep(self.WAIT_FOR_EXIT_TIMEOUT)
            if self.is_running:
                log.warning('{0!r} (pid={1}) timed out, killing it', self, self.pid)
                killed[:] = [True]
                self._kill_process_tree()

        kill_thread = threading.Thread(target=kill, name=fmt('{0} watchdog (pid={1})', self, self.pid))
        kill_thread.daemon = True
        kill_thread.start()

        log.info('Waiting for {0} (pid={1}) to terminate', self, self.pid)
        returncode = self.psutil_process.wait()

        assert not killed, "wait_for_exit() timed out"
        assert returncode == self.expected_returncode

        self.is_running = False
        self.wait_for_termination(close=not killed)

    def _kill_process_tree(self):
        assert self.psutil_process is not None
        procs = [self.psutil_process]
        try:
            procs += self.psutil_process.children(recursive=True)
        except Exception:
            pass
        for p in procs:
            try:
                p.kill()
            except Exception:
                pass

    def _listen(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind(('localhost', 0))
        _, self.ptvsd_port = self.server_socket.getsockname()
        self.server_socket.listen(0)

        def accept_worker():
            with self.lock:
                server_socket = self.server_socket
                if server_socket is None:
                    return

            log.info('Listening for incoming connection from {0} on port {1}...', self, self.ptvsd_port)
            try:
                sock, _ = server_socket.accept()
            except Exception:
                log.exception()
                return
            log.info('Incoming connection from {0} accepted.', self)

            try:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                with self.lock:
                    if self.server_socket is not None:
                        self.socket = sock
                        sock = None
                        self._setup_channel()
                    else:
                        # self.close() has been called concurrently.
                        pass
            finally:
                if sock is not None:
                    try:
                        sock.close()
                    except Exception:
                        pass

        accept_thread = threading.Thread(target=accept_worker, name=fmt('{0} listener', self))
        accept_thread.daemon = True
        accept_thread.start()

    def connect(self):
        # ptvsd will take some time to spawn and start listening on the port,
        # so just hammer at it until it responds (or we time out).
        while not self.socket:
            try:
                self._try_connect()
            except Exception:
                log.exception('Error connecting to {0}; retrying ...', self, category="warning")
            time.sleep(0.1)
        self._setup_channel()

    def _try_connect(self):
        log.info('Trying to connect to {0} on port {1}...', self, self.ptvsd_port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(('localhost', self.ptvsd_port))
        log.info('Connected to {0}.', self)
        self.socket = sock

    def _setup_channel(self):
        self.stream = messaging.JsonIOStream.from_socket(self.socket, name=str(self))
        handlers = messaging.MessageHandlers(request=self._process_request, event=self._process_event)
        self.channel = messaging.JsonMessageChannel(self.stream, handlers)
        self.channel.start()
        self.connected.set()

    def send_request(self, command, arguments=None, proceed=True):
        if self.timeline.is_frozen and proceed:
            self.proceed()

        def causing(*expectations):
            for exp in expectations:
                (request >> exp).wait()
            return request

        request = self.timeline.record_request(command, arguments)
        request.sent = self.channel.send_request(command, arguments)
        request.sent.on_response(lambda response: self._process_response(request, response))
        request.causing = causing
        return request

    def request(self, *args, **kwargs):
        return self.send_request(*args, **kwargs).wait_for_response().body

    def handshake(self):
        """Performs the handshake that establishes the debug session ('initialized'
        and 'launch' or 'attach').

        After this method returns, ptvsd is not running any code yet, but it is
        ready to accept any configuration requests (e.g. for initial breakpoints).
        Once initial configuration is complete, start_debugging() should be called
        to finalize the configuration stage, and start running code.
        """

        self.request('initialize', {'adapterID': 'test'})
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
                'name': some.str,
                'isLocalProcess': True,
                'startMethod': 'launch' if self.start_method == 'launch' else 'attach',
                'systemProcessId': self.pid if self.pid is not None else some.int,
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
        if event.event == "terminated":
            # Stop the message loop, since the ptvsd is going to close the connection
            # from its end shortly after sending this event, and no further messages
            # are expected.
            log.info(
                'Received "terminated" event from {0}; stopping message processing.',
                self,
            )
            raise EOFError(fmt("{0} terminated", self))

    def _process_response(self, request_occ, response):
        self.timeline.record_response(request_occ, response.body, block=False)

    def _process_request(self, request):
        assert False, 'ptvsd should not be sending requests.'

    def wait_for_next_event(self, event, body=some.object):
        return self.timeline.wait_for_next(Event(event, body)).body

    def output(self, category):
        """Returns all output of a given category as a single string, assembled from
        all the "output" events received for that category so far.
        """
        events = self.all_occurrences_of(
            Event("output", some.dict.containing({"category": category}))
        )
        return "".join(event.body["output"] for event in events)

    def captured_stdout(self, encoding=None):
        return self.captured_output.stdout(encoding)

    def captured_stderr(self, encoding=None):
        return self.captured_output.stderr(encoding)

    # Helpers for specific DAP patterns.

    def wait_for_stop(self, reason=some.str, expected_frames=None, expected_text=None, expected_description=None):
        stopped_event = self.wait_for_next(Event('stopped', some.dict.containing({'reason': reason})))
        stopped = stopped_event.body

        if expected_text is not None:
            assert expected_text == stopped['text']

        if expected_description is not None:
            assert expected_description == stopped['description']

        tid = stopped['threadId']
        assert tid == some.int

        assert stopped['allThreadsStopped']
        if stopped['reason'] not in ['step', 'exception', 'breakpoint', 'entry']:
            assert stopped['preserveFocusHint']

        stack_trace = self.request('stackTrace', arguments={'threadId': tid})
        frames = stack_trace['stackFrames'] or []
        assert len(frames) == stack_trace['totalFrames']

        if expected_frames:
            assert len(expected_frames) <= len(frames)
            assert expected_frames == frames[0:len(expected_frames)]

        fid = frames[0]['id']
        assert fid == some.int

        return StopInfo(stopped, frames, tid, fid)

    def request_continue(self):
        self.send_request('continue').wait_for_response(freeze=False)

    def set_breakpoints(self, path, lines):
        """Sets breakpoints in the specified file, and returns the list of all the
        corresponding DAP Breakpoint objects in the same order.

        If lines are specified, it should be an iterable in which every element is
        either a line number or a string. If it is a string, then it is translated
        to the corresponding line number via get_marked_line_numbers(path).

        If lines=all, breakpoints will be set on all the marked lines in the file.
        """

        # Don't fetch line markers unless needed - in some cases, the breakpoints
        # might be set in a file that does not exist on disk (e.g. remote attach).
        def get_marked_line_numbers():
            try:
                return get_marked_line_numbers.cached
            except AttributeError:
                get_marked_line_numbers.cached = code.get_marked_line_numbers(path)
                return get_marked_line_numbers()

        if lines is all:
            lines = get_marked_line_numbers().keys()

        def make_breakpoint(line):
            if isinstance(line, int):
                descr = str(line)
            else:
                marker = line
                line = get_marked_line_numbers()[marker]
                descr = fmt("{0} (@{1})", line, marker)
            bp_log.append((line, descr))
            return {'line': line}

        bp_log = []
        breakpoints = self.request(
            'setBreakpoints',
            {
                'source': {'path': path},
                'breakpoints': [make_breakpoint(line) for line in lines],
            },
        ).get('breakpoints', [])

        bp_log = sorted(bp_log, key=lambda pair: pair[0])
        bp_log = ", ".join((descr for _, descr in bp_log))
        log.info("Breakpoints set in {0}: {1}", path, bp_log)

        return breakpoints

    def get_variables(self, *varnames, **kwargs):
        """Fetches the specified variables from the frame specified by frame_id, or
        from the topmost frame in the last "stackTrace" response if frame_id is not
        specified.

        If varnames is empty, then all variables in the frame are returned. The result
        is an OrderedDict, in which every entry has variable name as the key, and a
        DAP Variable object as the value. The original order of variables as reported
        by the debugger is preserved.

        If varnames is not empty, then only the specified variables are returned.
        The result is a tuple, in which every entry is a DAP Variable object; those
        entries are in the same order as varnames.
        """

        assert self.timeline.is_frozen

        frame_id = kwargs.pop("frame_id", None)
        if frame_id is None:
            stackTrace_responses = self.all_occurrences_of(
                Response(Request("stackTrace"))
            )
            assert stackTrace_responses, (
                'get_variables() without frame_id requires at least one response '
                'to a "stackTrace" request in the timeline.'
            )
            stack_trace = stackTrace_responses[-1].body
            frame_id = stack_trace["stackFrames"][0]["id"]

        scopes = self.request("scopes", {"frameId": frame_id})["scopes"]
        assert len(scopes) > 0

        variables = self.request(
            "variables", {"variablesReference": scopes[0]["variablesReference"]}
        )["variables"]

        variables = collections.OrderedDict(((v["name"], v) for v in variables))
        if varnames:
            assert set(varnames) <= set(variables.keys())
            return tuple((variables[name] for name in varnames))
        else:
            return variables

    def get_variable(self, varname, frame_id=None):
        """Same as get_variables(...)[0].
        """
        return self.get_variables(varname, frame_id=frame_id)[0]

    def attach_to_subprocess(self, ptvsd_subprocess):
        assert ptvsd_subprocess == Event("ptvsd_subprocess")

        child_port = ptvsd_subprocess.body['port']
        assert child_port != 0

        child_session = Session(start_method='attach_socket_cmdline', ptvsd_port=child_port)
        try:
            child_session.ignore_unobserved = self.ignore_unobserved
            child_session.debug_options = self.debug_options
            child_session.rules = self.rules
            child_session.connect()
            child_session.handshake()
        except Exception:
            child_session.close()
            raise
        else:
            return child_session

    def attach_to_next_subprocess(self):
        ptvsd_subprocess = self.wait_for_next(Event('ptvsd_subprocess'))
        return self.attach_to_subprocess(ptvsd_subprocess)

    def reattach(self, **kwargs):
        """Creates and initializes a new Session that tries to attach to the same
        process.

        Upon return, handshake() has been performed, but the caller is responsible
        for invoking start_debugging().
        """

        assert self.start_method.startswith("attach_socket_")

        ns = Session(start_method='attach_socket_import', ptvsd_port=self.ptvsd_port)
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
        except Exception:
            ns.close()
            raise
        else:
            return ns


class CapturedOutput(object):
    """Captured stdout and stderr of the debugged process.
    """

    def __init__(self, session):
        self.session = session
        self._lock = threading.Lock()
        self._lines = {}
        self._worker_threads = []

    def _worker(self, pipe, name):
        lines = self._lines[name]
        while True:
            try:
                line = pipe.readline()
            except Exception:
                line = None

            if line:
                log.info("{0} {1}> {2!r}", self.session, name, line)
                with self._lock:
                    lines.append(line)
            else:
                break

    def _capture(self, pipe, name):
        assert name not in self._lines
        self._lines[name] = []

        thread = threading.Thread(
            target=lambda: self._worker(pipe, name),
            name=fmt("{0} {1}", self, name)
        )
        thread.daemon = True
        thread.start()
        self._worker_threads.append(thread)

    def capture(self, process):
        """Start capturing stdout and stderr of the process.
        """
        assert not self._worker_threads
        self._capture(process.stdout, "stdout")
        self._capture(process.stderr, "stderr")

    def wait(self, timeout=None):
        """Wait for all remaining output to be captured.
        """
        for t in self._worker_threads:
            t.join(timeout)

    def _output(self, which, encoding, lines):
        assert self.session.timeline.is_frozen

        try:
            result = self._lines[which]
        except KeyError:
            raise AssertionError(fmt("{0} was not captured for {1}", which, self.session))

        # The list might still be appended to concurrently, so take a snapshot of it.
        with self._lock:
            result = list(result)

        if encoding is not None:
            result = [s.decode(encoding) for s in result]

        if not lines:
            sep = b'' if encoding is None else u''
            result = sep.join(result)

        return result

    def stdout(self, encoding=None):
        """Returns stdout captured from the debugged process, as a single string.

        If encoding is None, returns bytes. Otherwise, returns unicode.
        """
        return self._output("stdout", encoding, lines=False)

    def stderr(self, encoding=None):
        """Returns stderr captured from the debugged process, as a single string.

        If encoding is None, returns bytes. Otherwise, returns unicode.
        """
        return self._output("stderr", encoding, lines=False)

    def stdout_lines(self, encoding=None):
        """Returns stdout captured from the debugged process, as a list of lines.

        If encoding is None, each line is bytes. Otherwise, each line is unicode.
        """
        return self._output("stdout", encoding, lines=True)

    def stderr_lines(self, encoding=None):
        """Returns stderr captured from the debugged process, as a list of lines.

        If encoding is None, each line is bytes. Otherwise, each line is unicode.
        """
        return self._output("stderr", encoding, lines=True)


class BackChannel(object):
    TIMEOUT = 20

    def __init__(self, session):
        self.session = session
        self.port = None
        self._established = threading.Event()
        self._socket = None
        self._server_socket = None

    def __str__(self):
        return fmt("backchannel-{0}", self.session.id)

    def listen(self):
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.settimeout(self.TIMEOUT)
        self._server_socket.bind(('localhost', 0))
        _, self.port = self._server_socket.getsockname()
        self._server_socket.listen(0)

        def accept_worker():
            log.info('Listening for incoming connection from {0} on port {1}...', self, self.port)

            try:
                self._socket, _ = self._server_socket.accept()
            except socket.timeout:
                raise log.exception("Timed out waiting for {0} to connect", self)

            self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            log.info('Incoming connection from {0} accepted.', self)
            self._setup_stream()

        accept_thread = threading.Thread(
            target=accept_worker,
            name=fmt('{0} listener', self)
        )
        accept_thread.daemon = True
        accept_thread.start()

    def _setup_stream(self):
        self._stream = messaging.JsonIOStream.from_socket(self._socket, name=str(self))
        self._established.set()

    def receive(self):
        self._established.wait()
        return self._stream.read_json()

    def send(self, value):
        self._established.wait()
        self.session.timeline.unfreeze()
        t = self.session.timeline.mark(('sending', value))
        self._stream.write_json(value)
        return t

    def expect(self, expected):
        actual = self.receive()
        assert expected == actual, fmt(
            "Test expected {0!r} on backchannel, but got {1!r} from the debuggee",
            expected,
            actual,
        )

    def close(self):
        if self._socket:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            self._socket = None
            log.debug('Closed socket for {0} to {1}', self, self.session)

        if self._server_socket:
            try:
                self._server_socket.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            self._server_socket = None
            log.debug('Closed server socket for {0} to {1}', self, self.session)
