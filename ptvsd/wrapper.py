# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, absolute_import

import contextlib
import errno
import io
import os
import platform
import pydevd_file_utils
import re
import site
import socket
import sys
import threading
import traceback
try:
    import urllib
    urllib.unquote
except Exception:
    import urllib.parse as urllib
try:
    from functools import reduce
except Exception:
    pass
import warnings
from xml.sax import SAXParseException

import _pydevd_bundle.pydevd_comm as pydevd_comm  # noqa
import _pydevd_bundle.pydevd_extension_api as pydevd_extapi  # noqa
import _pydevd_bundle.pydevd_extension_utils as pydevd_extutil  # noqa
import _pydevd_bundle.pydevd_frame as pydevd_frame # noqa
#from _pydevd_bundle.pydevd_comm import pydevd_log
from _pydevd_bundle.pydevd_additional_thread_info import PyDBAdditionalThreadInfo # noqa

from ptvsd import _util
import ptvsd.ipcjson as ipcjson  # noqa
import ptvsd.futures as futures  # noqa
import ptvsd.untangle as untangle  # noqa
from ptvsd.pathutils import PathUnNormcase  # noqa
from ptvsd.safe_repr import SafeRepr  # noqa
from ptvsd.version import __version__  # noqa
from ptvsd.socket import TimeoutError  # noqa


WAIT_FOR_THREAD_FINISH_TIMEOUT = 1  # seconds


debug = _util.debug


#def ipcjson_trace(s):
#    print(s)
#ipcjson._TRACE = ipcjson_trace


def is_debugger_internal_thread(thread_name):
    # TODO: docstring
    if thread_name:
        if thread_name.startswith('pydevd.'):
            return True
        elif thread_name.startswith('ptvsd.'):
            return True
    return False


class SafeReprPresentationProvider(pydevd_extapi.StrPresentationProvider):
    """
    Computes string representation of Python values by delegating them
    to SafeRepr.
    """

    _lock = threading.Lock()

    def __init__(self):
        self.set_format({})

    def can_provide(self, type_object, type_name):
        """Implements StrPresentationProvider."""
        return True

    def get_str(self, val):
        """Implements StrPresentationProvider."""
        return self._repr(val)

    def set_format(self, fmt):
        """
        Use fmt for all future formatting operations done by this provider.
        """
        safe_repr = SafeRepr()
        safe_repr.convert_to_hex = fmt.get('hex', False)
        safe_repr.raw_value = fmt.get('rawString', False)
        self._repr = safe_repr

    @contextlib.contextmanager
    def using_format(self, fmt):
        """
        Returns a context manager that invokes set_format(fmt) on enter,
        and restores the old format on exit.
        """
        old_repr = self._repr
        self.set_format(fmt)
        yield
        self._repr = old_repr


# Do not access directly - use safe_repr_provider() instead!
SafeReprPresentationProvider._instance = SafeReprPresentationProvider()

# Register our presentation provider as the first item on the list,
# so that we're in full control of presentation.
str_handlers = pydevd_extutil.EXTENSION_MANAGER_INSTANCE.type_to_instance.setdefault(pydevd_extapi.StrPresentationProvider, [])  # noqa
str_handlers.insert(0, SafeReprPresentationProvider._instance)

PTVSD_DIR_PATH = os.path.dirname(os.path.abspath(__file__)) + os.path.sep
NORM_PTVSD_DIR_PATH = os.path.normcase(PTVSD_DIR_PATH)


def dont_trace_ptvsd_files(file_path):
    """
    Returns true if the file should not be traced.
    """
    return file_path.startswith(PTVSD_DIR_PATH)


pydevd_frame.file_tracing_filter = dont_trace_ptvsd_files


STDLIB_PATH_PREFIXES = [os.path.normcase(sys.prefix)]
if hasattr(sys, 'base_prefix'):
    STDLIB_PATH_PREFIXES.append(os.path.normcase(sys.base_prefix))
if hasattr(sys, 'real_prefix'):
    STDLIB_PATH_PREFIXES.append(os.path.normcase(sys.real_prefix))

if hasattr(site, 'getusersitepackages'):
    site_paths = site.getusersitepackages()
    if isinstance(site_paths, list):
        for site_path in site_paths:
            STDLIB_PATH_PREFIXES.append(os.path.normcase(site_path))
    else:
        STDLIB_PATH_PREFIXES.append(os.path.normcase(site_paths))

if hasattr(site, 'getsitepackages'):
    site_paths = site.getsitepackages()
    if isinstance(site_paths, list):
        for site_path in site_paths:
            STDLIB_PATH_PREFIXES.append(os.path.normcase(site_path))
    else:
        STDLIB_PATH_PREFIXES.append(os.path.normcase(site_paths))


class UnsupportedPyDevdCommandError(Exception):

    def __init__(self, cmdid):
        msg = 'unsupported pydevd command ' + str(cmdid)
        super(UnsupportedPyDevdCommandError, self).__init__(msg)
        self.cmdid = cmdid


def unquote(s):
    if s is None:
        return None
    return urllib.unquote(s)


class IDMap(object):
    """Maps VSCode entities to corresponding pydevd entities by ID.

    VSCode entity IDs are generated here when necessary.

    For VSCode, entity IDs are always integers, and uniquely identify
    the entity among all other entities of the same type - e.g. all
    frames across all threads have unique IDs.

    For pydevd, IDs can be integer or strings, and are usually specific
    to some scope - for example, a frame ID is only unique within a
    given thread. To produce a truly unique ID, the IDs of all the outer
    scopes have to be combined into a tuple. Thus, for example, a pydevd
    frame ID is (thread_id, frame_id).

    Variables (evaluation results) technically don't have IDs in pydevd,
    as it doesn't have evaluation persistence. However, for a given
    frame, any child can be identified by the path one needs to walk
    from the root of the frame to get to that child - and that path,
    represented as a sequence of its constituent components, is used by
    pydevd commands to identify the variable. So we use the tuple
    representation of the same as its pydevd ID.  For example, for
    something like foo[1].bar, its ID is:
      (thread_id, frame_id, 'FRAME', 'foo', 1, 'bar')

    For pydevd breakpoints, the ID has to be specified by the caller
    when creating, so we can just reuse the ID that was generated for
    VSC. However, when referencing the pydevd breakpoint later (e.g. to
    remove it), its ID must be specified together with path to file in
    which that breakpoint is set - i.e. pydevd treats those IDs as
    scoped to a file.  So, even though breakpoint IDs are unique across
    files, use (path, bp_id) as pydevd ID.
    """

    def __init__(self):
        self._vscode_to_pydevd = {}
        self._pydevd_to_vscode = {}
        self._next_id = 1
        self._lock = threading.Lock()

    def pairs(self):
        # TODO: docstring
        with self._lock:
            return list(self._pydevd_to_vscode.items())

    def add(self, pydevd_id):
        # TODO: docstring
        with self._lock:
            vscode_id = self._next_id
            if callable(pydevd_id):
                pydevd_id = pydevd_id(vscode_id)
            self._next_id += 1
            self._vscode_to_pydevd[vscode_id] = pydevd_id
            self._pydevd_to_vscode[pydevd_id] = vscode_id
        return vscode_id

    def remove(self, pydevd_id=None, vscode_id=None):
        # TODO: docstring
        with self._lock:
            if pydevd_id is None:
                pydevd_id = self._vscode_to_pydevd[vscode_id]
            elif vscode_id is None:
                vscode_id = self._pydevd_to_vscode[pydevd_id]
            del self._vscode_to_pydevd[vscode_id]
            del self._pydevd_to_vscode[pydevd_id]

    def to_pydevd(self, vscode_id):
        # TODO: docstring
        return self._vscode_to_pydevd[vscode_id]

    def to_vscode(self, pydevd_id, autogen):
        # TODO: docstring
        try:
            return self._pydevd_to_vscode[pydevd_id]
        except KeyError:
            if autogen:
                return self.add(pydevd_id)
            else:
                raise

    def pydevd_ids(self):
        # TODO: docstring
        with self._lock:
            ids = list(self._pydevd_to_vscode.keys())
        return ids

    def vscode_ids(self):
        # TODO: docstring
        with self._lock:
            ids = list(self._vscode_to_pydevd.keys())
        return ids


class ExceptionInfo(object):
    # TODO: docstring

    def __init__(self, name, description, stack, source):
        self.name = name
        self.description = description
        self.stack = stack
        self.source = source


class PydevdSocket(object):
    """A dummy socket-like object for communicating with pydevd.

    It parses pydevd messages and redirects them to the provided handler
    callback.  It also provides an interface to send notifications and
    requests to pydevd; for requests, the reply can be asynchronously
    awaited.
    """

    def __init__(self, handle_msg, handle_close, getpeername, getsockname):
        #self.log = open('pydevd.log', 'w')
        self._handle_msg = handle_msg
        self._handle_close = handle_close
        self._getpeername = getpeername
        self._getsockname = getsockname

        self.lock = threading.Lock()
        self.seq = 1000000000
        self.pipe_r, self.pipe_w = os.pipe()
        self.requests = {}

        self._closed = False
        self._closing = False

    def close(self):
        """Mark the socket as closed and release any resources."""
        if self._closing:
            return

        with self.lock:
            if self._closed:
                return
            self._closing = True

            if self.pipe_w is not None:
                pipe_w = self.pipe_w
                self.pipe_w = None
                try:
                    os.close(pipe_w)
                except OSError as exc:
                    if exc.errno != errno.EBADF:
                        raise
            if self.pipe_r is not None:
                pipe_r = self.pipe_r
                self.pipe_r = None
                try:
                    os.close(pipe_r)
                except OSError as exc:
                    if exc.errno != errno.EBADF:
                        raise
            self._handle_close()
            self._closed = True
            self._closing = False

    def shutdown(self, mode):
        """Called when pydevd has stopped."""
        # noop

    def getpeername(self):
        """Return the remote address to which the socket is connected."""
        return self._getpeername()

    def getsockname(self):
        """Return the socket's own address."""
        return self._getsockname()

    def recv(self, count):
        """Return the requested number of bytes.

        This is where the "socket" sends requests to pydevd.  The data
        must follow the pydevd line protocol.
        """
        pipe_r = self.pipe_r
        if pipe_r is None:
            return b''
        data = os.read(pipe_r, count)
        #self.log.write('>>>[' + data.decode('utf8') + ']\n\n')
        #self.log.flush()
        return data

    def recv_into(self, buf):
        pipe_r = self.pipe_r
        if pipe_r is None:
            return 0
        return os.readv(pipe_r, [buf])

    # In Python 2, we must unquote before we decode, because UTF-8 codepoints
    # are encoded first and then quoted as individual bytes. In Python 3,
    # however, we just get a properly UTF-8-encoded string.
    if sys.version_info < (3,):
        @staticmethod
        def _decode_and_unquote(data):
            return unquote(data).decode('utf8')
    else:
        @staticmethod
        def _decode_and_unquote(data):
            return unquote(data.decode('utf8'))

    def send(self, data):
        """Handle the given bytes.

        This is where pydevd sends responses and events.  The data will
        follow the pydevd line protocol.
        """
        result = len(data)
        data = self._decode_and_unquote(data)
        #self.log.write('<<<[' + data + ']\n\n')
        #self.log.flush()
        cmd_id, seq, args = data.split('\t', 2)
        cmd_id = int(cmd_id)
        seq = int(seq)
        with self.lock:
            loop, fut = self.requests.pop(seq, (None, None))
        if fut is None:
            self._handle_msg(cmd_id, seq, args)
        else:
            loop.call_soon_threadsafe(fut.set_result, (cmd_id, seq, args))
        return result

    def makefile(self, *args, **kwargs):
        """Return a file-like wrapper around the socket."""
        return os.fdopen(self.pipe_r)

    def make_packet(self, cmd_id, args):
        # TODO: docstring
        with self.lock:
            seq = self.seq
            self.seq += 1
        s = '{}\t{}\t{}\n'.format(cmd_id, seq, args)
        return seq, s

    def pydevd_notify(self, cmd_id, args):
        # TODO: docstring
        _, s = self.make_packet(cmd_id, args)
        os.write(self.pipe_w, s.encode('utf8'))

    def pydevd_request(self, loop, cmd_id, args):
        # TODO: docstring
        seq, s = self.make_packet(cmd_id, args)
        fut = loop.create_future()
        with self.lock:
            self.requests[seq] = loop, fut
            os.write(self.pipe_w, s.encode('utf8'))
        return fut


class ExceptionsManager(object):
    def __init__(self, proc):
        self.proc = proc
        self.exceptions = {}
        self.lock = threading.Lock()

    def remove_all_exception_breaks(self):
        with self.lock:
            for exception in self.exceptions.keys():
                self.proc.pydevd_notify(pydevd_comm.CMD_REMOVE_EXCEPTION_BREAK,
                                        'python-{}'.format(exception))
            self.exceptions = {}

    def _find_exception(self, name):
        if name in self.exceptions:
            return name

        for ex_name in self.exceptions.keys():
            # ExceptionInfo.name can be in repr form
            # here we attempt to find the exception as it
            # is saved in the dictionary
            if ex_name in name:
                return ex_name

        return 'BaseException'

    def get_break_mode(self, name):
        with self.lock:
            try:
                return self.exceptions[self._find_exception(name)]
            except KeyError:
                pass
        return 'unhandled'

    def add_exception_break(self, exception, break_raised, break_uncaught,
                            skip_stdlib=False):

        notify_on_handled_exceptions = 1 if break_raised else 0
        notify_on_unhandled_exceptions = 1 if break_uncaught else 0
        ignore_libraries = 1 if skip_stdlib else 0

        cmdargs = (
            exception,
            notify_on_handled_exceptions,
            notify_on_unhandled_exceptions,
            ignore_libraries,
        )
        break_mode = 'never'
        if break_raised:
            break_mode = 'always'
        elif break_uncaught:
            break_mode = 'unhandled'

        msg = 'python-{}\t{}\t{}\t{}'.format(*cmdargs)
        with self.lock:
            self.proc.pydevd_notify(
                pydevd_comm.CMD_ADD_EXCEPTION_BREAK, msg)
            self.exceptions[exception] = break_mode

    def apply_exception_options(self, exception_options, skip_stdlib=False):
        """
        Applies exception options after removing any existing exception
        breaks.
        """
        self.remove_all_exception_breaks()
        pyex_options = (opt
                        for opt in exception_options
                        if self._is_python_exception_category(opt))
        for option in pyex_options:
            exception_paths = option['path']
            if not exception_paths:
                continue

            mode = option['breakMode']
            break_raised = (mode == 'always')
            break_uncaught = (mode in ['unhandled', 'userUnhandled'])

            # Special case for the entire python exceptions category
            is_category = False
            if len(exception_paths) == 1:
                # TODO: isn't the first one always the category?
                if exception_paths[0]['names'][0] == 'Python Exceptions':
                    is_category = True
            if is_category:
                self.add_exception_break(
                    'BaseException', break_raised, break_uncaught, skip_stdlib)
            else:
                path_iterator = iter(exception_paths)
                # Skip the first one. It will always be the category
                # "Python Exceptions"
                next(path_iterator)
                exception_names = []
                for path in path_iterator:
                    for ex_name in path['names']:
                        exception_names.append(ex_name)
                for exception_name in exception_names:
                    self.add_exception_break(
                        exception_name, break_raised,
                        break_uncaught, skip_stdlib)

    def _is_python_exception_category(self, option):
        """
        Check if the option has entires and that the first entry
        is 'Python Exceptions'.
        """
        exception_paths = option['path']
        if not exception_paths:
            return False

        category = exception_paths[0]['names']
        if category is None or len(category) != 1:
            return False

        return category[0] == 'Python Exceptions'


class VariablesSorter(object):
    def __init__(self):
        self.variables = []  # variables that do not begin with underscores
        self.single_underscore = []  # variables beginning with underscores
        self.double_underscore = []  # variables beginning with two underscores
        self.dunder = []  # variables that begin & end with double underscores

    def append(self, var):
        var_name = var['name']
        if var_name.startswith('__'):
            if var_name.endswith('__'):
                self.dunder.append(var)
                #print('Apended dunder: %s' % var_name)
            else:
                self.double_underscore.append(var)
                #print('Apended double under: %s' % var_name)
        elif var_name.startswith('_'):
            self.single_underscore.append(var)
            #print('Apended single under: %s' % var_name)
        else:
            self.variables.append(var)
            #print('Apended variable: %s' % var_name)

    def get_sorted_variables(self):
        def get_sort_key(o):
            return o['name']
        self.variables.sort(key=get_sort_key)
        self.single_underscore.sort(key=get_sort_key)
        self.double_underscore.sort(key=get_sort_key)
        self.dunder.sort(key=get_sort_key)
        #print('sorted')
        return self.variables + self.single_underscore + self.double_underscore + self.dunder  # noqa


class ModulesManager(object):
    def __init__(self, proc):
        self.module_id_to_details = {}
        self.path_to_module_id = {}
        self._lock = threading.Lock()
        self.proc = proc
        self._next_id = 1

    def add_or_get_from_path(self, module_path):
        with self._lock:
            try:
                module_id = self.path_to_module_id[module_path]
                return self.module_id_to_details[module_id]
            except KeyError:
                pass

            search_path = self._get_platform_file_path(module_path)
            for _, value in list(sys.modules.items()):
                try:
                    path = self._get_platform_file_path(value.__file__)
                except AttributeError:
                    path = None

                if path and search_path == path:
                    module_id = self._next_id
                    self._next_id += 1

                    module = {
                        'id': module_id,
                        'package': value.__package__,
                        'path': module_path,
                    }

                    try:
                        module['name'] = value.__qualname__
                    except AttributeError:
                        module['name'] = value.__name__

                    try:
                        module['version'] = value.__version__
                    except AttributeError:
                        pass

                    self.path_to_module_id[module_path] = module_id
                    self.module_id_to_details[module_id] = module

                    self.proc.send_event('module', reason='new', module=module)
                    return module

        return None

    def _get_platform_file_path(self, path):
        if platform.system() == 'Windows':
            return path.lower()
        return path

    def get_all(self):
        with self._lock:
            return list(self.module_id_to_details.values())

    def check_unloaded_modules(self, module_event):
        pass


class InternalsFilter(object):
    """Identifies debugger internal artifacts.
    """
    # TODO: Move the internal thread identifier here
    def __init__(self):
        if platform.system() == 'Windows':
            self._init_windows()
        else:
            self._init_default()

    def _init_default(self):
        self._ignore_files = [
            '/ptvsd_launcher.py',
        ]

        self._ignore_path_prefixes = [
            os.path.dirname(os.path.abspath(__file__)),
        ]

    def _init_windows(self):
        self._init_default()
        files = []
        for f in self._ignore_files:
            files.append(f.lower())
        self._ignore_files = files

        prefixes = []
        for p in self._ignore_path_prefixes:
            prefixes.append(p.lower())
        self._ignore_path_prefixes = prefixes

    def is_internal_path(self, abs_file_path):
        # TODO: Remove replace('\\', '/') after the path mapping in pydevd
        # is fixed. Currently if the client is windows and server is linux
        # the path separators used are windows path separators for linux
        # source paths.
        is_windows = platform.system() == 'Windows'

        file_path = abs_file_path.lower() if is_windows else abs_file_path
        file_path = file_path.replace('\\', '/')
        for f in self._ignore_files:
            if file_path.endswith(f):
                return True
        for prefix in self._ignore_path_prefixes:
            prefix_path = prefix.replace('\\', '/')
            if file_path.startswith(prefix_path):
                return True
        return False


########################
# the debug config

def bool_parser(str):
    return str in ("True", "true", "1")


DEBUG_OPTIONS_PARSER = {
    'WAIT_ON_ABNORMAL_EXIT': bool_parser,
    'WAIT_ON_NORMAL_EXIT': bool_parser,
    'REDIRECT_OUTPUT': bool_parser,
    'VERSION': unquote,
    'INTERPRETER_OPTIONS': unquote,
    'WEB_BROWSER_URL': unquote,
    'DJANGO_DEBUG': bool_parser,
    'FLASK_DEBUG': bool_parser,
    'FIX_FILE_PATH_CASE': bool_parser,
    'WINDOWS_CLIENT': bool_parser,
    'DEBUG_STDLIB': bool_parser,
}


DEBUG_OPTIONS_BY_FLAG = {
    'RedirectOutput': 'REDIRECT_OUTPUT=True',
    'WaitOnNormalExit': 'WAIT_ON_NORMAL_EXIT=True',
    'WaitOnAbnormalExit': 'WAIT_ON_ABNORMAL_EXIT=True',
    'Django': 'DJANGO_DEBUG=True',
    'Flask': 'FLASK_DEBUG=True',
    'Jinja': 'FLASK_DEBUG=True',
    'FixFilePathCase': 'FIX_FILE_PATH_CASE=True',
    'DebugStdLib': 'DEBUG_STDLIB=True',
    'WindowsClient': 'WINDOWS_CLIENT=True',
}


def _extract_debug_options(opts, flags=None):
    """Return the debug options encoded in the given value.

    "opts" is a semicolon-separated string of "key=value" pairs.
    "flags" is a list of strings.

    If flags is provided then it is used as a fallback.

    The values come from the launch config:

     {
         type:'python',
         request:'launch'|'attach',
         name:'friendly name for debug config',
         debugOptions:[
             'RedirectOutput', 'Django'
         ],
         options:'REDIRECT_OUTPUT=True;DJANGO_DEBUG=True'
     }

    Further information can be found here:

     https://code.visualstudio.com/docs/editor/debugging#_launchjson-attributes
    """
    if not opts:
        opts = _build_debug_options(flags)
    return _parse_debug_options(opts)


def _build_debug_options(flags):
    """Build string representation of debug options from the launch config."""
    return ';'.join(DEBUG_OPTIONS_BY_FLAG[flag]
                    for flag in flags or []
                    if flag in DEBUG_OPTIONS_BY_FLAG)


def _parse_debug_options(opts):
    """Debug options are semicolon separated key=value pairs
        WAIT_ON_ABNORMAL_EXIT=True|False
        WAIT_ON_NORMAL_EXIT=True|False
        REDIRECT_OUTPUT=True|False
        VERSION=string
        INTERPRETER_OPTIONS=string
        WEB_BROWSER_URL=string url
        DJANGO_DEBUG=True|False
        WINDOWS_CLIENT=True|False
        DEBUG_STDLIB=True|False
    """
    options = {}
    if not opts:
        return options

    for opt in opts.split(';'):
        try:
            key, value = opt.split('=')
        except ValueError:
            continue
        try:
            options[key] = DEBUG_OPTIONS_PARSER[key](value)
        except KeyError:
            continue

    if 'WINDOWS_CLIENT' not in options:
        options['WINDOWS_CLIENT'] = platform.system() == 'Windows' # noqa

    return options


########################
# the message processor

# TODO: Embed instead of extend (inheritance -> composition).


class VSCodeMessageProcessorBase(ipcjson.SocketIO, ipcjson.IpcChannel):
    """The base class for VSC message processors."""

    def __init__(self, socket, notify_closing,
                 timeout=None, logfile=None, own_socket=False
                 ):
        super(VSCodeMessageProcessorBase, self).__init__(
            socket=socket,
            own_socket=False,
            timeout=timeout,
            logfile=logfile,
        )
        self.socket = socket
        self._own_socket = own_socket
        self._notify_closing = notify_closing

        self.server_thread = None
        self._closed = False
        self.readylock = threading.Lock()
        self.readylock.acquire()  # Unlock at the end of start().

        self._connected = threading.Lock()
        self._listening = None
        self._connlock = threading.Lock()

    @property
    def connected(self):  # may send responses/events
        with self._connlock:
            return _util.is_locked(self._connected)

    @property
    def listening(self):
        # TODO: must be disconnected?
        with self._connlock:
            if self._listening is None:
                return False
            return _util.is_locked(self._listening)

    def wait_while_connected(self, timeout=None):
        """Wait until the client socket is disconnected."""
        with self._connlock:
            lock = self._listening
        _util.lock_wait(lock, timeout)  # Wait until no longer connected.

    def wait_while_listening(self, timeout=None):
        """Wait until no longer listening for incoming messages."""
        with self._connlock:
            lock = self._listening
            if lock is None:
                raise RuntimeError('not listening yet')
        _util.lock_wait(lock, timeout)  # Wait until no longer listening.

    def start(self, threadname):
        # event loop
        self._start_event_loop()

        # VSC msg processing loop
        def process_messages():
            self.readylock.acquire()
            with self._connlock:
                self._listening = threading.Lock()
            try:
                self.process_messages()
            except (EOFError, TimeoutError):
                debug('client socket closed')
                with self._connlock:
                    _util.lock_release(self._listening)
                    _util.lock_release(self._connected)
                self.close()
        self.server_thread = threading.Thread(
            target=process_messages,
            name=threadname,
        )
        self.server_thread.pydev_do_not_trace = True
        self.server_thread.is_pydev_daemon_thread = True
        self.server_thread.daemon = True
        self.server_thread.start()

        # special initialization
        debug('sending output')
        self.send_event(
            'output',
            category='telemetry',
            output='ptvsd',
            data={'version': __version__},
        )
        debug('output sent')
        self.readylock.release()

    def close(self):
        """Stop the message processor and release its resources."""
        if self._closed:
            return
        self._closed = True
        debug('raw closing')

        self._notify_closing()
        # Close the editor-side socket.
        self._stop_vsc_message_loop()

        # Ensure that the connection is marked as closed.
        with self._connlock:
            _util.lock_release(self._listening)
            _util.lock_release(self._connected)

    # VSC protocol handlers

    def send_error_response(self, request, message=None):
        self.send_response(
            request,
            success=False,
            message=message
        )

    # internal methods

    def _set_disconnected(self):
        with self._connlock:
            _util.lock_release(self._connected)

    def _wait_for_server_thread(self):
        if self.server_thread is None:
            return
        if not self.server_thread.is_alive():
            return
        self.server_thread.join(WAIT_FOR_THREAD_FINISH_TIMEOUT)

    def _stop_vsc_message_loop(self):
        self.set_exit()
        self._stop_event_loop()
        if self.socket is not None and self._own_socket:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
                self.socket.close()
                self._set_disconnected()
            except Exception:
                # TODO: log the error
                pass

    # methods for subclasses to override

    def _start_event_loop(self):
        pass

    def _stop_event_loop(self):
        pass


INITIALIZE_RESPONSE = dict(
    supportsConditionalBreakpoints=True,
    supportsConfigurationDoneRequest=True,
    supportsDebuggerProperties=True,
    supportsEvaluateForHovers=True,
    supportsExceptionInfoRequest=True,
    supportsExceptionOptions=True,
    supportsHitConditionalBreakpoints=True,
    supportsLogPoints=True,
    supportsModulesRequest=True,
    supportsSetExpression=True,
    supportsSetVariable=True,
    supportsValueFormattingOptions=True,
    supportTerminateDebuggee=True,
    exceptionBreakpointFilters=[
        {
            'filter': 'raised',
            'label': 'Raised Exceptions',
            'default': False
        },
        {
            'filter': 'uncaught',
            'label': 'Uncaught Exceptions',
            'default': True
        },
    ],
)


class VSCLifecycleMsgProcessor(VSCodeMessageProcessorBase):
    """Handles adapter lifecycle messages of the VSC debugger protocol."""

    EXITWAIT = 1

    def __init__(self, socket,
                 notify_disconnecting, notify_closing, notify_launch=None,
                 timeout=None, logfile=None, debugging=True,
                 ):
        super(VSCLifecycleMsgProcessor, self).__init__(
            socket=socket,
            notify_closing=notify_closing,
            timeout=timeout,
            logfile=logfile,
        )
        self._notify_launch = notify_launch or (lambda: None)
        self._notify_disconnecting = notify_disconnecting

        self._stopped = False

        # adapter state
        self.start_reason = None
        self.debug_options = {}
        self._statelock = threading.Lock()
        self._debugging = debugging
        self._handshakelock = threading.Lock()
        self._handshakelock.acquire()  # released in on_configurationDone()
        self._debuggerstopped = False
        self._exitlock = threading.Lock()
        self._exitlock.acquire()  # released in handle_exiting()
        self._exiting = False

    def handle_debugger_stopped(self, wait=None):
        """Deal with the debugger exiting."""
        # Notify the editor that the debugger has stopped.
        if not self._debugging:
            # TODO: Fail?  If this gets called then we must be debugging.
            return

        # We run this in a thread to allow handle_exiting() to be called
        # at the same time.
        def stop():
            if wait is not None:
                wait()
            # Since pydevd is embedded in the debuggee process, always
            # make sure the exited event is sent first.
            self._wait_until_exiting(self.EXITWAIT)
            self._ensure_debugger_stopped()
        t = threading.Thread(target=stop, name='ptvsd.stopping')
        t.start()

    def handle_exiting(self, exitcode=None, wait=None):
        """Deal with the debuggee exiting."""
        # Notify the editor that the "debuggee" (e.g. script, app) exited.
        with self._statelock:
            if self._exiting:
                return
            self._exiting = True

        self.send_event('exited', exitCode=exitcode or 0)

        self._waiting = True
        if wait is not None:
            normal, abnormal = self._wait_options()
            cfg = (normal and not exitcode) or (abnormal and exitcode)
            # This must be done before we send a disconnect response
            # (which implies before we close the client socket).
            wait(cfg)

        # If we are exiting then pydevd must have stopped.
        self._ensure_debugger_stopped()

        if self._exitlock is not None:
            _util.lock_release(self._exitlock)

    def wait_until_ready(self):
        """Wait until the protocol handshake is complete."""
        _util.lock_wait(self._handshakelock)

    # VSC protocol handlers

    def on_initialize(self, request, args):
        # TODO: docstring
        self.send_response(request, **INITIALIZE_RESPONSE)
        self.send_event('initialized')

    def on_configurationDone(self, request, args):
        # TODO: docstring
        self.send_response(request)
        self._process_debug_options(self.debug_options)
        self._handle_configurationDone(args)
        _util.lock_release(self._handshakelock)

    def on_attach(self, request, args):
        # TODO: docstring
        self.start_reason = 'attach'
        self._set_debug_options(args)
        self._handle_attach(args)
        self.send_response(request)

    def on_launch(self, request, args):
        # TODO: docstring
        self.start_reason = 'launch'
        self._set_debug_options(args)
        self._notify_launch()
        self._handle_launch(args)
        self.send_response(request)

    def on_disconnect(self, request, args):
        # TODO: docstring
        if self._debuggerstopped:  # A "terminated" event must have been sent.
            self._wait_until_exiting(self.EXITWAIT)
        self._notify_disconnecting()
        self.send_response(request)
        self._set_disconnected()

        # TODO: We should be able drop the remaining lines.
        if not self._closed and self.start_reason == 'launch':
            # Closing the socket causes pydevd to resume all threads,
            # so just terminate the process altogether.
            sys.exit(0)

    # internal methods

    def _set_debug_options(self, args):
        self.debug_options = _extract_debug_options(
            args.get('options'),
            args.get('debugOptions'),
        )

    def _ensure_debugger_stopped(self):
        if not self._debugging:
            return
        with self._statelock:
            if self._debuggerstopped:
                return
            self._debuggerstopped = True
        self.send_event('terminated')

    def _wait_until_exiting(self, timeout):
        lock = self._exitlock
        if lock is None:
            return
        try:
            _util.lock_wait(lock, timeout, 'waiting for process exit')
        except _util.TimeoutError as exc:
            warnings.warn(str(exc))

    # methods related to shutdown

    def _wait_options(self):
        normal = self.debug_options.get('WAIT_ON_NORMAL_EXIT', False)
        abnormal = self.debug_options.get('WAIT_ON_ABNORMAL_EXIT', False)
        return normal, abnormal

    # methods for subclasses to override

    def _process_debug_options(self, opts):
        pass

    def _handle_configurationDone(self, args):
        pass

    def _handle_attach(self, args):
        pass

    def _handle_launch(self, args):
        pass


class VSCodeMessageProcessor(VSCLifecycleMsgProcessor):
    """IPC JSON message processor for VSC debugger protocol.

    This translates between the VSC debugger protocol and the pydevd
    protocol.
    """

    def __init__(self, socket, pydevd_notify, pydevd_request,
                 notify_disconnecting, notify_closing,
                 timeout=None, logfile=None,
                 ):
        super(VSCodeMessageProcessor, self).__init__(
            socket=socket,
            notify_disconnecting=notify_disconnecting,
            notify_closing=notify_closing,
            timeout=timeout,
            logfile=logfile,
        )
        self._pydevd_notify = pydevd_notify
        self._pydevd_request = pydevd_request

        self.loop = None
        self.event_loop_thread = None
        self.bkpoints = None

        # debugger state
        self.is_process_created = False
        self.is_process_created_lock = threading.Lock()
        self.stack_traces = {}
        self.stack_traces_lock = threading.Lock()
        self.active_exceptions = {}
        self.active_exceptions_lock = threading.Lock()
        self.thread_map = IDMap()
        self.frame_map = IDMap()
        self.var_map = IDMap()
        self.bp_map = IDMap()
        self.source_map = IDMap()
        self.enable_source_references = False
        self.next_var_ref = 0
        self.exceptions_mgr = ExceptionsManager(self)
        self.modules_mgr = ModulesManager(self)
        self.internals_filter = InternalsFilter()

        # adapter state
        self.path_casing = PathUnNormcase()

    def _start_event_loop(self):
        self.loop = futures.EventLoop()
        self.event_loop_thread = threading.Thread(
            target=self.loop.run_forever,
            name='ptvsd.EventLoop',
        )
        self.event_loop_thread.pydev_do_not_trace = True
        self.event_loop_thread.is_pydev_daemon_thread = True
        self.event_loop_thread.daemon = True
        self.event_loop_thread.start()

    def _stop_event_loop(self):
        self.loop.stop()
        self.event_loop_thread.join(WAIT_FOR_THREAD_FINISH_TIMEOUT)

    # async helpers

    def async_method(m):
        """Converts a generator method into an async one."""
        m = futures.wrap_async(m)

        def f(self, *args, **kwargs):
            return m(self, self.loop, *args, **kwargs)

        return f

    def async_handler(m):
        """Converts a generator method into a fire-and-forget async one."""
        m = futures.wrap_async(m)

        def f(self, *args, **kwargs):
            fut = m(self, self.loop, *args, **kwargs)

            def done(fut):
                try:
                    fut.result()
                except BaseException:
                    traceback.print_exc(file=sys.__stderr__)

            fut.add_done_callback(done)

        return f

    def sleep(self):
        fut = futures.Future(self.loop)
        self.loop.call_soon(lambda: fut.set_result(None))
        return fut

    # PyDevd "socket" entry points (and related helpers)

    def pydevd_notify(self, cmd_id, args):
        # TODO: docstring
        try:
            return self._pydevd_notify(cmd_id, args)
        except BaseException:
            traceback.print_exc(file=sys.__stderr__)
            raise

    def pydevd_request(self, cmd_id, args):
        # TODO: docstring
        return self._pydevd_request(self.loop, cmd_id, args)

    # Instances of this class provide decorators to mark methods as
    # handlers for various # pydevd messages - a decorated method is
    # added to the map with the corresponding message ID, and is
    # looked up there by pydevd event handler below.
    class EventHandlers(dict):
        def handler(self, cmd_id):
            def decorate(f):
                self[cmd_id] = f
                return f
            return decorate

    pydevd_events = EventHandlers()

    def on_pydevd_event(self, cmd_id, seq, args):
        # TODO: docstring
        try:
            f = self.pydevd_events[cmd_id]
        except KeyError:
            raise UnsupportedPyDevdCommandError(cmd_id)
        return f(self, seq, args)

    @staticmethod
    def parse_xml_response(args):
        return untangle.parse(io.BytesIO(args.encode('utf8'))).xml

    @async_method
    def using_format(self, fmt):
        while not SafeReprPresentationProvider._lock.acquire(False):
            yield self.sleep()
        provider = SafeReprPresentationProvider._instance

        @contextlib.contextmanager
        def context():
            with provider.using_format(fmt):
                yield
            provider._lock.release()
        yield futures.Result(context())

    # VSC protocol handlers

    def _handle_configurationDone(self, args):
        self.pydevd_request(pydevd_comm.CMD_RUN, '')

        if self.start_reason == 'attach':
            # Send event notifying the creation of the process.
            # If we do not do this and try to pause, VSC throws errors,
            # complaining about debugger still initializing.
            with self.is_process_created_lock:
                if not self.is_process_created:
                    self.is_process_created = True
                    self.send_process_event(self.start_reason)

    def _process_debug_options(self, opts):
        """Process the launch arguments to configure the debugger."""
        if opts.get('FIX_FILE_PATH_CASE', False):
            self.path_casing.enable()

        if opts.get('REDIRECT_OUTPUT', False):
            redirect_output = 'STDOUT\tSTDERR'
        else:
            redirect_output = ''
        self.pydevd_request(pydevd_comm.CMD_REDIRECT_OUTPUT, redirect_output)
        self._apply_code_stepping_settings()

    def _is_just_my_code_stepping_enabled(self):
        """Returns true if just-me-code stepping is enabled.

        Note: for now we consider DEBUG_STDLIB = False as just-my-code.
        """
        dbg_stdlib = self.debug_options.get('DEBUG_STDLIB', False)
        return not dbg_stdlib

    def _apply_code_stepping_settings(self):
        if self._is_just_my_code_stepping_enabled():
            vendored_pydevd = os.path.sep + \
                              os.path.join('ptvsd', '_vendored', 'pydevd')
            ptvsd_path = os.path.sep + 'ptvsd'

            project_dirs = []
            for path in sys.path + [os.getcwd()]:
                is_stdlib = False
                norm_path = os.path.normcase(path)
                if path.endswith(ptvsd_path) or \
                   path.endswith(vendored_pydevd):
                    is_stdlib = True
                else:
                    for prefix in STDLIB_PATH_PREFIXES:
                        if norm_path.startswith(prefix):
                            is_stdlib = True
                            break

                if not is_stdlib and len(path) > 0:
                    project_dirs.append(path)
            self.pydevd_request(pydevd_comm.CMD_SET_PROJECT_ROOTS,
                                '\t'.join(project_dirs))

    def _is_stdlib(self, filepath):
        for prefix in STDLIB_PATH_PREFIXES:
            if prefix != '' and filepath.startswith(prefix):
                return True
        return filepath.startswith(NORM_PTVSD_DIR_PATH)

    def _should_debug(self, filepath):
        if self._is_just_my_code_stepping_enabled() and \
           self._is_stdlib(filepath):
            return False
        return True

    def _initialize_path_maps(self, args):
        pathMaps = []
        for pathMapping in args.get('pathMappings', []):
            localRoot = pathMapping.get('localRoot', '')
            remoteRoot = pathMapping.get('remoteRoot', '')
            if (len(localRoot) > 0 and len(remoteRoot) > 0):
                pathMaps.append((localRoot, remoteRoot))

        if len(pathMaps) > 0:
            pydevd_file_utils.setup_client_server_paths(pathMaps)

    def _send_cmd_version_command(self):
        cmd = pydevd_comm.CMD_VERSION
        windows_client = self.debug_options.get(
            'WINDOWS_CLIENT',
            platform.system() == 'Windows')
        os_id = 'WINDOWS' if windows_client else 'UNIX'
        msg = '1.1\t{}\tID'.format(os_id)
        return self.pydevd_request(cmd, msg)

    @async_handler
    def _handle_attach(self, args):
        self._initialize_path_maps(args)
        yield self._send_cmd_version_command()

    @async_handler
    def _handle_launch(self, args):
        self._initialize_path_maps(args)
        yield self._send_cmd_version_command()

    def send_process_event(self, start_method):
        # TODO: docstring
        evt = {
            'name': sys.argv[0],
            'systemProcessId': os.getpid(),
            'isLocalProcess': True,
            'startMethod': start_method,
        }
        self.send_event('process', **evt)

    @async_handler
    def on_threads(self, request, args):
        # TODO: docstring
        cmd = pydevd_comm.CMD_LIST_THREADS
        _, _, resp_args = yield self.pydevd_request(cmd, '')

        try:
            xml = self.parse_xml_response(resp_args)
        except SAXParseException as ex:
            self.send_error_response(request)
            return

        try:
            xthreads = xml.thread
        except AttributeError:
            xthreads = []

        threads = []
        for xthread in xthreads:
            try:
                name = unquote(xthread['name'])
            except KeyError:
                name = None

            if not is_debugger_internal_thread(name):
                pyd_tid = xthread['id']
                try:
                    vsc_tid = self.thread_map.to_vscode(pyd_tid, autogen=False)
                except KeyError:
                    # This is a previously unseen thread
                    vsc_tid = self.thread_map.to_vscode(pyd_tid, autogen=True)
                    self.send_event('thread', reason='started',
                                    threadId=vsc_tid)

                threads.append({'id': vsc_tid, 'name': name})

        self.send_response(request, threads=threads)

    @async_handler
    def on_source(self, request, args):
        """Request to get the source"""
        source_reference = args.get('sourceReference', 0)
        filename = '' if source_reference == 0 else \
            self.source_map.to_pydevd(source_reference)

        if source_reference == 0:
            self.send_error_response(request, 'Source unavailable')
        else:
            server_filename = pydevd_file_utils.norm_file_to_server(filename)

            cmd = pydevd_comm.CMD_LOAD_SOURCE
            _, _, content = yield self.pydevd_request(cmd, server_filename)
            self.send_response(request, content=content)

    def get_source_reference(self, filename):
        """Gets the source reference only in remote debugging scenarios.
        And we know that the path returned is the same as the server path
        (i.e. path has not been translated)"""

        if self.start_reason == 'launch':
            return 0

        try:
            return self.source_map.to_vscode(filename, autogen=False)
        except KeyError:
            # If attaching to a local process (then remote and local are same)
            for local_prefix, remote_prefix in pydevd_file_utils.PATHS_FROM_ECLIPSE_TO_PYTHON: # noqa
                if local_prefix != remote_prefix:
                    continue
                if filename.startswith(local_prefix): # noqa
                    return 0
                if platform.system() == 'Windows' and filename.upper().startswith(local_prefix.upper()): # noqa
                    return 0

        server_filename = pydevd_file_utils.norm_file_to_server(filename)

        # If the mapped file is the same as the file we provided,
        # then we can generate a soure reference.
        if server_filename == filename and os.path.exists(server_filename):
            return self.source_map.to_vscode(filename, autogen=True)
        elif platform.system() == 'Windows' and \
            server_filename.upper() == filename.upper() and \
            os.path.exists(server_filename):
            return self.source_map.to_vscode(filename, autogen=True)
        elif server_filename.replace('\\', '/') == filename.replace('\\', '/'):
            # If remote is Unix and local is Windows, then PyDevD will
            #   replace the path separator in remote with with
            #   the os path separator of remote client
            return self.source_map.to_vscode(filename, autogen=True)
        else:
            return 0

    @async_handler
    def on_stackTrace(self, request, args):
        # TODO: docstring
        vsc_tid = int(args['threadId'])
        startFrame = int(args.get('startFrame', 0))
        levels = int(args.get('levels', 0))
        fmt = args.get('format', {})

        pyd_tid = self.thread_map.to_pydevd(vsc_tid)
        with self.stack_traces_lock:
            try:
                xframes = self.stack_traces[pyd_tid]
            except KeyError:
                # This means the stack was requested before the
                # thread was suspended
                xframes = []
        totalFrames = len(xframes)

        if levels == 0:
            levels = totalFrames

        stackFrames = []
        for xframe in xframes:
            if startFrame > 0:
                startFrame -= 1
                continue

            if levels <= 0:
                break
            levels -= 1

            key = (pyd_tid, int(xframe['id']))
            fid = self.frame_map.to_vscode(key, autogen=True)
            name = unquote(xframe['name'])
            norm_path = self.path_casing.un_normcase(unquote(xframe['file']))
            source_reference = self.get_source_reference(norm_path)
            if not self.internals_filter.is_internal_path(norm_path):
                module = self.modules_mgr.add_or_get_from_path(norm_path)
            else:
                module = None
            line = int(xframe['line'])
            frame_name = self._format_frame_name(
                fmt,
                name,
                module,
                line,
                norm_path)

            stackFrames.append({
                'id': fid,
                'name': frame_name,
                'source': {
                    'path': norm_path,
                    'sourceReference': source_reference
                },
                'line': line, 'column': 1,
            })

        user_frames = []
        for frame in stackFrames:
            if not self.internals_filter.is_internal_path(
                frame['source']['path']):
                user_frames.append(frame)

        totalFrames = len(user_frames)
        self.send_response(request,
                           stackFrames=user_frames,
                           totalFrames=totalFrames)

    def _format_frame_name(self, fmt, name, module, line, path):
        frame_name = name
        if fmt.get('module', False):
            if module:
                if name == '<module>':
                    frame_name = module['name']
                else:
                    frame_name = '%s.%s' % (module['name'], name)
            else:
                _, tail = os.path.split(path)
                tail = tail[0:-3] if tail.lower().endswith('.py') else tail
                if name == '<module>':
                    frame_name = '%s in %s' % (name, tail)
                else:
                    frame_name = '%s.%s' % (tail, name)

        if fmt.get('line', False):
            frame_name = '%s : %d' % (frame_name, line)

        return frame_name

    @async_handler
    def on_scopes(self, request, args):
        # TODO: docstring
        vsc_fid = int(args['frameId'])
        pyd_tid, pyd_fid = self.frame_map.to_pydevd(vsc_fid)
        pyd_var = (pyd_tid, pyd_fid, 'FRAME')
        vsc_var = self.var_map.to_vscode(pyd_var, autogen=True)
        scope = {
            'name': 'Locals',
            'expensive': False,
            'variablesReference': vsc_var,
        }
        self.send_response(request, scopes=[scope])

    @async_handler
    def on_variables(self, request, args):
        """Handles DAP VariablesRequest."""

        vsc_var = int(args['variablesReference'])
        fmt = args.get('format', {})

        try:
            pyd_var = self.var_map.to_pydevd(vsc_var)
        except KeyError:
            self.send_error_response(request)
            return

        if len(pyd_var) == 3:
            cmd = pydevd_comm.CMD_GET_FRAME
        else:
            cmd = pydevd_comm.CMD_GET_VARIABLE
        cmdargs = (str(s) for s in pyd_var)
        msg = '\t'.join(cmdargs)
        with (yield self.using_format(fmt)):
            _, _, resp_args = yield self.pydevd_request(cmd, msg)

        try:
            xml = self.parse_xml_response(resp_args)
        except SAXParseException as ex:
            self.send_error_response(request)
            return

        try:
            xvars = xml.var
        except AttributeError:
            xvars = []

        variables = VariablesSorter()
        for xvar in xvars:
            var_name = unquote(xvar['name'])
            var_type = unquote(xvar['type'])
            var_value = unquote(xvar['value'])
            var = {
                'name': var_name,
                'type': var_type,
                'value': var_value,
            }

            if self._is_raw_string(var_type):
                var['presentationHint'] = {'attributes': ['rawString']}

            if bool(xvar['isContainer']):
                pyd_child = pyd_var + (var_name,)
                var['variablesReference'] = self.var_map.to_vscode(
                    pyd_child, autogen=True)

            eval_name = self._get_variable_evaluate_name(pyd_var, var_name)
            if eval_name:
                var['evaluateName'] = eval_name

            variables.append(var)

        self.send_response(request, variables=variables.get_sorted_variables())

    def _is_raw_string(self, var_type):
        return var_type in ('str', 'unicode', 'bytes', 'bytearray')

    def _get_variable_evaluate_name(self, pyd_var_parent, var_name):
        # TODO: docstring
        eval_name = None
        if len(pyd_var_parent) > 3:
            # This means the current variable has a parent i.e, it is not a
            # FRAME variable. These require evaluateName to work in VS
            # watch window
            var = pyd_var_parent + (var_name,)
            eval_name = var[3]
            for s in var[4:]:
                try:
                    # Check and get the dictionary key or list index.
                    # Note: this is best effort, keys that are object
                    # references will not work
                    i = self._get_index_or_key(s)
                    eval_name += '[{}]'.format(i)
                except Exception:
                    eval_name += '.' + s

        return eval_name

    def _get_index_or_key(self, text):
        # Dictionary resolver in pydevd provides key
        # in '<repr> (<hash>)' format
        result = re.match(r"(.*)\ \(([0-9]*)\)", text,
                          re.IGNORECASE | re.UNICODE)
        if result and len(result.groups()) == 2:
            try:
                # check if group 2 is a hash
                int(result.group(2))
                return result.group(1)
            except Exception:
                pass
        # In the result XML from pydevd list indexes appear
        # as names. If the name is a number then it is a index.
        return int(text)

    @async_handler
    def on_setVariable(self, request, args):
        """Handles DAP SetVariableRequest."""

        vsc_var = int(args['variablesReference'])
        try:
            pyd_var = self.var_map.to_pydevd(vsc_var)
        except KeyError:
            self.send_error_response(request)
            return

        var_name = args['name']
        var_value = args['value']
        fmt = args.get('format', {})

        lhs_expr = self._get_variable_evaluate_name(pyd_var, var_name)
        if not lhs_expr:
            lhs_expr = var_name
        expr = '%s = %s' % (lhs_expr, var_value)
        # pydevd message format doesn't permit tabs in expressions
        expr = expr.replace('\t', ' ')

        pyd_tid = str(pyd_var[0])
        pyd_fid = str(pyd_var[1])

        # VSC gives us variablesReference to the parent of the variable
        # being set, and variable name; but pydevd wants the ID
        # (or rather path) of the variable itself.
        pyd_var += (var_name,)
        vsc_var = self.var_map.to_vscode(pyd_var, autogen=True)

        cmd_args = [pyd_tid, pyd_fid, 'LOCAL', expr, '1']
        with (yield self.using_format(fmt)):
            yield self.pydevd_request(
                pydevd_comm.CMD_EXEC_EXPRESSION,
                '\t'.join(cmd_args),
            )

        cmd_args = [pyd_tid, pyd_fid, 'LOCAL', lhs_expr, '1']
        with (yield self.using_format(fmt)):
            _, _, resp_args = yield self.pydevd_request(
                pydevd_comm.CMD_EVALUATE_EXPRESSION,
                '\t'.join(cmd_args),
            )

        try:
            xml = self.parse_xml_response(resp_args)
        except SAXParseException as ex:
            self.send_error_response(request)
            return

        try:
            xvar = xml.var
        except AttributeError:
            self.send_response(request, success=False)
            return

        response = {
            'type': unquote(xvar['type']),
            'value': unquote(xvar['value']),
        }
        if bool(xvar['isContainer']):
            response['variablesReference'] = vsc_var

        self.send_response(request, **response)

    @async_handler
    def on_evaluate(self, request, args):
        """Handles DAP EvaluateRequest."""

        # pydevd message format doesn't permit tabs in expressions
        expr = args['expression'].replace('\t', ' ')
        fmt = args.get('format', {})

        vsc_fid = int(args['frameId'])
        pyd_tid, pyd_fid = self.frame_map.to_pydevd(vsc_fid)

        cmd_args = (pyd_tid, pyd_fid, 'LOCAL', expr, '1')
        msg = '\t'.join(str(s) for s in cmd_args)
        with (yield self.using_format(fmt)):
            _, _, resp_args = yield self.pydevd_request(
                pydevd_comm.CMD_EVALUATE_EXPRESSION,
                msg)

        try:
            xml = self.parse_xml_response(resp_args)
        except SAXParseException as ex:
            self.send_error_response(request)
            return

        try:
            xvar = xml.var
        except AttributeError:
            self.send_response(request, success=False)
            return

        context = args.get('context', '')
        is_eval_error = xvar['isErrorOnEval']
        if context == 'hover' and is_eval_error == 'True':
            self.send_response(
                request,
                result=None,
                variablesReference=0)
            return

        if context == 'repl' and is_eval_error == 'True':
            # try exec for repl requests
            with (yield self.using_format(fmt)):
                _, _, resp_args = yield self.pydevd_request(
                    pydevd_comm.CMD_EXEC_EXPRESSION,
                    msg)
            try:
                xml2 = self.parse_xml_response(resp_args)
                xvar2 = xml2.var
                result_type = unquote(xvar2['type'])
                result = unquote(xvar2['value'])
            except Exception:
                # if resp_args is not xml then it contains the error traceback
                result_type = unquote(xvar['type'])
                result = unquote(xvar['value'])
            self.send_response(
                request,
                result=(None
                        if result == 'None' and result_type == 'NoneType'
                        else result),
                type=result_type,
                variablesReference=0,
            )
            return

        pyd_var = (pyd_tid, pyd_fid, 'EXPRESSION', expr)
        vsc_var = self.var_map.to_vscode(pyd_var, autogen=True)
        var_type = unquote(xvar['type'])
        var_value = unquote(xvar['value'])
        response = {
            'type': var_type,
            'result': var_value,
        }

        if self._is_raw_string(var_type):
            response['presentationHint'] = {'attributes': ['rawString']}

        if bool(xvar['isContainer']):
            response['variablesReference'] = vsc_var

        self.send_response(request, **response)

    @async_handler
    def on_setExpression(self, request, args):
        # TODO: docstring

        vsc_fid = int(args['frameId'])
        pyd_tid, pyd_fid = self.frame_map.to_pydevd(vsc_fid)
        fmt = args.get('format', {})

        lhs_expr = args.get('expression')
        rhs_expr = args.get('value')
        expr = '%s = (%s)' % (lhs_expr, rhs_expr)

        # pydevd message format doesn't permit tabs in expressions
        expr = expr.replace('\t', ' ')

        cmd_args = (pyd_tid, pyd_fid, 'LOCAL', expr, '1')
        msg = '\t'.join(str(s) for s in cmd_args)
        with (yield self.using_format(fmt)):
            yield self.pydevd_request(
                pydevd_comm.CMD_EXEC_EXPRESSION,
                msg)

        # Return 'None' here, VS will call getVariables to retrieve
        # updated values anyway. Doing eval on the left-hand-side
        # expression may have side-effects
        self.send_response(request, value=None)

    @async_handler
    def on_modules(self, request, args):
        modules = list(self.modules_mgr.get_all())
        user_modules = []
        for module in modules:
            if not self.internals_filter.is_internal_path(module['path']):
                user_modules.append(module)
        self.send_response(request,
                           modules=user_modules,
                           totalModules=len(user_modules))

    @async_handler
    def on_pause(self, request, args):
        # TODO: docstring

        # Pause requests cannot be serviced until pydevd is fully initialized.
        with self.is_process_created_lock:
            if not self.is_process_created:
                self.send_response(
                    request,
                    success=False,
                    message='Cannot pause while debugger is initializing',
                )
                return

        # Always suspend all threads.
        for pyd_tid in self.thread_map.pydevd_ids():
            self.pydevd_notify(pydevd_comm.CMD_THREAD_SUSPEND, pyd_tid)
        self.send_response(request)

    @async_handler
    def on_continue(self, request, args):
        # TODO: docstring
        tid = self.thread_map.to_pydevd(int(args['threadId']))
        self.pydevd_notify(pydevd_comm.CMD_THREAD_RUN, tid)
        self.send_response(request)

    @async_handler
    def on_next(self, request, args):
        # TODO: docstring
        tid = self.thread_map.to_pydevd(int(args['threadId']))
        self.pydevd_notify(pydevd_comm.CMD_STEP_OVER, tid)
        self.send_response(request)

    @async_handler
    def on_stepIn(self, request, args):
        # TODO: docstring
        tid = self.thread_map.to_pydevd(int(args['threadId']))
        if self._is_just_my_code_stepping_enabled():
            self.pydevd_notify(pydevd_comm.CMD_STEP_INTO_MY_CODE, tid)
        else:
            self.pydevd_notify(pydevd_comm.CMD_STEP_INTO, tid)
        self.send_response(request)

    @async_handler
    def on_stepOut(self, request, args):
        # TODO: docstring
        tid = self.thread_map.to_pydevd(int(args['threadId']))
        self.pydevd_notify(pydevd_comm.CMD_STEP_RETURN, tid)
        self.send_response(request)

    def _get_hit_condition_expression(self, hit_condition):
        """Following hit condition values are supported

        * x or == x when breakpoint is hit x times
        * >= x when breakpoint is hit more than or equal to x times
        * % x when breakpoint is hit multiple of x times

        Returns '@HIT@ == x' where @HIT@ will be replaced by number of hits
        """
        if not hit_condition:
            return None

        expr = hit_condition.strip()
        try:
            int(expr)
            return '@HIT@ == {}'.format(expr)
        except ValueError:
            pass

        if expr.startswith('%'):
            return '@HIT@ {} == 0'.format(expr)

        if expr.startswith('==') or \
            expr.startswith('>') or \
            expr.startswith('<'):
            return '@HIT@ {}'.format(expr)

        return hit_condition

    def re_build_breakpoints(self):
        self.wait_until_ready()
        if self.bkpoints is None:
            return
        self.on_setBreakpoints(None, self.bkpoints)

    @async_handler
    def on_setBreakpoints(self, request, args):
        # TODO: docstring
        self.bkpoints = args
        bps = []
        path = args['source']['path']
        self.path_casing.track_file_path_case(path)
        src_bps = args.get('breakpoints', [])

        bp_type = 'python-line'
        if not path.lower().endswith('.py'):
            if self.debug_options.get('DJANGO_DEBUG', False):
                bp_type = 'django-line'
            elif self.debug_options.get('FLASK_DEBUG', False):
                bp_type = 'jinja2-line'

        # First, we must delete all existing breakpoints in that source.
        cmd = pydevd_comm.CMD_REMOVE_BREAK
        for pyd_bpid, vsc_bpid in self.bp_map.pairs():
            if pyd_bpid[0] == path:
                msg = '{}\t{}\t{}'.format(bp_type, path, vsc_bpid)
                self.pydevd_notify(cmd, msg)
                self.bp_map.remove(pyd_bpid, vsc_bpid)

        cmd = pydevd_comm.CMD_SET_BREAK
        msgfmt = '{}\t{}\t{}\t{}\tNone\t{}\t{}\t{}\t{}'
        for src_bp in src_bps:
            line = src_bp['line']
            vsc_bpid = self.bp_map.add(
                    lambda vsc_bpid: (path, vsc_bpid))
            self.path_casing.track_file_path_case(path)

            hit_condition = self._get_hit_condition_expression(
                                src_bp.get('hitCondition', None))
            logMessage = src_bp.get('logMessage', '')
            if len(logMessage) == 0:
                is_logpoint = None
                condition = src_bp.get('condition', None)
                expression = None
            else:
                is_logpoint = True
                condition = None
                expressions = re.findall('\{.*?\}', logMessage)
                if len(expressions) == 0:
                    expression = 'print({})'.format(repr(logMessage)) # noqa
                else:
                    raw_text = reduce(lambda a, b: a.replace(b, '{}'), expressions, logMessage) # noqa
                    raw_text = raw_text.replace('"', '\\"')
                    expression_list = ', '.join([s.strip('{').strip('}').strip() for s in expressions]) # noqa
                    expression = 'print("{}".format({}))'.format(raw_text, expression_list) # noqa

            msg = msgfmt.format(vsc_bpid, bp_type, path, line, condition,
                                expression, hit_condition, is_logpoint)
            self.pydevd_notify(cmd, msg)
            bps.append({
                'id': vsc_bpid,
                'verified': True,
                'line': line,
            })

        if request is not None:
            self.send_response(request, breakpoints=bps)

    @async_handler
    def on_setExceptionBreakpoints(self, request, args):
        # TODO: docstring
        filters = args['filters']
        exception_options = args.get('exceptionOptions', [])
        jmc = self._is_just_my_code_stepping_enabled()

        if exception_options:
            self.exceptions_mgr.apply_exception_options(
                exception_options, jmc)
        else:
            self.exceptions_mgr.remove_all_exception_breaks()
            break_raised = 'raised' in filters
            break_uncaught = 'uncaught' in filters
            if break_raised or break_uncaught:
                self.exceptions_mgr.add_exception_break(
                    'BaseException', break_raised, break_uncaught,
                    skip_stdlib=jmc)
        self.send_response(request)

    @async_handler
    def on_exceptionInfo(self, request, args):
        # TODO: docstring
        pyd_tid = self.thread_map.to_pydevd(args['threadId'])
        with self.active_exceptions_lock:
            try:
                exc = self.active_exceptions[pyd_tid]
            except KeyError:
                exc = ExceptionInfo('BaseException',
                                    'exception: no description',
                                    None, None)
        self.send_response(
            request,
            exceptionId=exc.name,
            description=exc.description,
            breakMode=self.exceptions_mgr.get_break_mode(exc.name),
            details={'typeName': exc.name,
                     'message': exc.description,
                     'stackTrace': exc.stack,
                     'source': exc.source},
        )

    # Custom ptvsd message
    def on_ptvsd_systemInfo(self, request, args):
        try:
            pid = os.getpid()
        except AttributeError:
            pid = None

        try:
            impl_desc = platform.python_implementation()
        except AttributeError:
            try:
                impl_desc = sys.implementation.name
            except AttributeError:
                impl_desc = None

        def version_str(v):
            return '{}.{}.{}{}{}'.format(
                v.major,
                v.minor,
                v.micro,
                v.releaselevel,
                v.serial)

        try:
            impl_name = sys.implementation.name
        except AttributeError:
            impl_name = None

        try:
            impl_version = version_str(sys.implementation.version)
        except AttributeError:
            impl_version = None

        sys_info = {
            'ptvsd': {
                'version': __version__,
            },
            'python': {
                'version': version_str(sys.version_info),
                'implementation': {
                    'name': impl_name,
                    'version': impl_version,
                    'description': impl_desc,
                },
            },
            'platform': {
                'name': sys.platform,
            },
            'process': {
                'pid': pid,
                'executable': sys.executable,
                'bitness': 64 if sys.maxsize > 2**32 else 32,
            },
        }
        self.send_response(request, **sys_info)

    # VS specific custom message handlers
    @async_handler
    def on_setDebuggerProperty(self, request, args):
        if 'JustMyCodeStepping' in args:
            jmc = int(args.get('JustMyCodeStepping', 0)) > 0
            self.debug_options['DEBUG_STDLIB'] = not jmc
            self._apply_code_stepping_settings()

        self.send_response(request)

    # PyDevd protocol event handlers

    @pydevd_events.handler(pydevd_comm.CMD_INPUT_REQUESTED)
    def on_pydevd_input_requested(self, seq, args):
        '''
        no-op: if stdin is requested, right now the user is expected to enter
        text in the terminal and the debug adapter doesn't really do anything
        (although in the future it could see that stdin is being requested and
        redirect any evaluation request to stdin).
        '''

    @pydevd_events.handler(pydevd_comm.CMD_THREAD_CREATE)
    def on_pydevd_thread_create(self, seq, args):
        # If this is the first thread reported, report process creation
        # as well.
        with self.is_process_created_lock:
            if not self.is_process_created:
                self.is_process_created = True
                self.send_process_event(self.start_reason)

        xml = self.parse_xml_response(args)
        try:
            name = unquote(xml.thread['name'])
        except KeyError:
            name = None
        if not is_debugger_internal_thread(name):
            # Any internal pydevd or ptvsd threads will be ignored everywhere
            tid = self.thread_map.to_vscode(xml.thread['id'], autogen=True)
            self.send_event('thread', reason='started', threadId=tid)

    @pydevd_events.handler(pydevd_comm.CMD_THREAD_KILL)
    def on_pydevd_thread_kill(self, seq, args):
        # TODO: docstring
        pyd_tid = args.strip()
        try:
            vsc_tid = self.thread_map.to_vscode(pyd_tid, autogen=False)
        except KeyError:
            pass
        else:
            self.thread_map.remove(pyd_tid, vsc_tid)
            self.send_event('thread', reason='exited', threadId=vsc_tid)

    @pydevd_events.handler(pydevd_comm.CMD_THREAD_SUSPEND)
    @async_handler
    def on_pydevd_thread_suspend(self, seq, args):
        # TODO: docstring
        xml = self.parse_xml_response(args)
        pyd_tid = xml.thread['id']
        reason = int(xml.thread['stop_reason'])
        STEP_REASONS = {
                pydevd_comm.CMD_STEP_INTO,
                pydevd_comm.CMD_STEP_OVER,
                pydevd_comm.CMD_STEP_RETURN,
                pydevd_comm.CMD_STEP_INTO_MY_CODE,
        }
        EXCEPTION_REASONS = {
            pydevd_comm.CMD_STEP_CAUGHT_EXCEPTION,
            pydevd_comm.CMD_ADD_EXCEPTION_BREAK
        }

        # This is needed till https://github.com/Microsoft/ptvsd/issues/477
        # is done. Remove this after adding the appropriate pydevd commands to
        # do step over and step out
        xframes = list(xml.thread.frame)
        xframe = xframes[0]
        filepath = unquote(xframe['file'])
        if reason in STEP_REASONS or reason in EXCEPTION_REASONS:
            if not self._should_debug(filepath):
                self.pydevd_notify(pydevd_comm.CMD_THREAD_RUN, pyd_tid)
                return

        # NOTE: We should add the thread to VSC thread map only if the
        # thread is seen here for the first time in 'attach' scenario.
        # If we are here in 'launch' scenario and we get KeyError then
        # there is an issue in reporting of thread creation.
        autogen = self.start_reason == 'attach'
        vsc_tid = self.thread_map.to_vscode(pyd_tid, autogen=autogen)

        with self.stack_traces_lock:
            self.stack_traces[pyd_tid] = list(xml.thread.frame)

        description = None
        text = None
        if reason in STEP_REASONS:
            reason = 'step'
        elif reason in EXCEPTION_REASONS:
            reason = 'exception'
        elif reason == pydevd_comm.CMD_SET_BREAK:
            reason = 'breakpoint'
        else:
            reason = 'pause'

        # For exception cases both raise and uncaught, pydevd adds a
        # __exception__ object to the top most frame. Extracting the
        # exception name and description from that frame gives accurate
        # exception information.
        if reason == 'exception':
            # Get exception info from frame
            try:
                pyd_fid = xframe['id']
                cmdargs = '{}\t{}\tFRAME\t__exception__'.format(pyd_tid,
                                                                pyd_fid)
                cmdid = pydevd_comm.CMD_GET_VARIABLE
                _, _, resp_args = yield self.pydevd_request(cmdid, cmdargs)
                xml = self.parse_xml_response(resp_args)
                text = unquote(xml.var[1]['type'])
                description = unquote(xml.var[1]['value'])
                frame_data = []
                for f in xframes:
                    file_path = unquote(f['file'])
                    if not self.internals_filter.is_internal_path(file_path):
                        line_no = int(f['line'])
                        func_name = unquote(f['name'])
                        if _util.is_py34():
                            # NOTE: In 3.4.* format_list requires the text
                            # to be passed in the tuple list.
                            line_text = _util.get_line_for_traceback(file_path,
                                                                     line_no)
                            frame_data.append((file_path, line_no,
                                               func_name, line_text))
                        else:
                            frame_data.append((file_path, line_no,
                                               func_name, None))
                stack = ''.join(traceback.format_list(frame_data))
                source = unquote(xframe['file'])
                if self.internals_filter.is_internal_path(source):
                    source = None
            except Exception:
                text = 'BaseException'
                description = 'exception: no description'
                stack = None
                source = None

            with self.active_exceptions_lock:
                self.active_exceptions[pyd_tid] = ExceptionInfo(text,
                                                                description,
                                                                stack,
                                                                source)

        self.send_event(
            'stopped',
            reason=reason,
            threadId=vsc_tid,
            text=text,
            description=description)

    @pydevd_events.handler(pydevd_comm.CMD_THREAD_RUN)
    def on_pydevd_thread_run(self, seq, args):
        # TODO: docstring
        pyd_tid, _ = args.split('\t')
        pyd_tid = pyd_tid.strip()

        # Stack trace, active exception, all frames, and variables for
        # this thread are now invalid; clear their IDs.
        with self.stack_traces_lock:
            try:
                del self.stack_traces[pyd_tid]
            except KeyError:
                pass

        with self.active_exceptions_lock:
            try:
                del self.active_exceptions[pyd_tid]
            except KeyError:
                pass

        for pyd_fid, vsc_fid in self.frame_map.pairs():
            if pyd_fid[0] == pyd_tid:
                self.frame_map.remove(pyd_fid, vsc_fid)

        for pyd_var, vsc_var in self.var_map.pairs():
            if pyd_var[0] == pyd_tid:
                self.var_map.remove(pyd_var, vsc_var)

        try:
            vsc_tid = self.thread_map.to_vscode(pyd_tid, autogen=False)
        except KeyError:
            pass
        else:
            self.send_event('continued', threadId=vsc_tid)

    @pydevd_events.handler(pydevd_comm.CMD_SEND_CURR_EXCEPTION_TRACE)
    def on_pydevd_send_curr_exception_trace(self, seq, args):
        # TODO: docstring
        pass

    @pydevd_events.handler(pydevd_comm.CMD_SEND_CURR_EXCEPTION_TRACE_PROCEEDED)
    def on_pydevd_send_curr_exception_trace_proceeded(self, seq, args):
        # TODO: docstring
        pyd_tid = args.strip()
        with self.active_exceptions_lock:
            try:
                del self.active_exceptions[pyd_tid]
            except KeyError:
                pass

    @pydevd_events.handler(pydevd_comm.CMD_WRITE_TO_CONSOLE)
    def on_pydevd_cmd_write_to_console2(self, seq, args):
        """Handle console output"""
        xml = self.parse_xml_response(args)
        ctx = xml.io['ctx']
        category = 'stdout' if ctx == '1' else 'stderr'
        content = unquote(xml.io['s'])
        self.send_event('output', category=category, output=content)
