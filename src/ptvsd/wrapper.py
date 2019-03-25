# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, absolute_import, unicode_literals

import bisect
import copy
import errno
import io
import json
import os
import platform
import pydevd_file_utils
import site
import socket
import sys
import threading

try:
    import urllib
    urllib.unquote
except Exception:
    import urllib.parse as urllib
try:
    import queue
except ImportError:
    import Queue as queue
import warnings
from xml.sax.saxutils import unescape as xml_unescape

import pydevd  # noqa
import _pydevd_bundle.pydevd_comm as pydevd_comm  # noqa
import _pydevd_bundle.pydevd_comm_constants as pydevd_comm_constants  # noqa
import _pydevd_bundle.pydevd_extension_api as pydevd_extapi  # noqa
import _pydevd_bundle.pydevd_extension_utils as pydevd_extutil  # noqa
import _pydevd_bundle.pydevd_frame as pydevd_frame  # noqa
from pydevd_file_utils import get_abs_path_real_path_and_base_from_file  # noqa
from _pydevd_bundle.pydevd_dont_trace_files import PYDEV_FILE  # noqa
from _pydevd_bundle import pydevd_additional_thread_info

import ptvsd
import ptvsd.log
from ptvsd import _util
from ptvsd import multiproc
from ptvsd import options
from ptvsd.compat import unicode
import ptvsd.ipcjson as ipcjson  # noqa
import ptvsd.futures as futures  # noqa
import ptvsd.untangle as untangle  # noqa
from ptvsd.pathutils import PathUnNormcase  # noqa
from ptvsd.version import __version__  # noqa
from ptvsd.socket import TimeoutError  # noqa

WAIT_FOR_THREAD_FINISH_TIMEOUT = 1  # seconds

STEP_REASONS = {
        pydevd_comm.CMD_STEP_INTO,
        pydevd_comm.CMD_STEP_INTO_MY_CODE,
        pydevd_comm.CMD_STEP_OVER,
        pydevd_comm.CMD_STEP_OVER_MY_CODE,
        pydevd_comm.CMD_STEP_RETURN,
        pydevd_comm.CMD_STEP_INTO_MY_CODE,
}
EXCEPTION_REASONS = {
    pydevd_comm.CMD_STEP_CAUGHT_EXCEPTION,
    pydevd_comm.CMD_ADD_EXCEPTION_BREAK
}

debugger_attached = threading.Event()


def NOOP(*args, **kwargs):
    pass


def path_to_unicode(s):
    return s if isinstance(s, unicode) else s.decode(sys.getfilesystemencoding())


PTVSD_DIR_PATH = os.path.dirname(os.path.abspath(get_abs_path_real_path_and_base_from_file(__file__)[0])) + os.path.sep
NORM_PTVSD_DIR_PATH = os.path.normcase(PTVSD_DIR_PATH)


def dont_trace_ptvsd_files(file_path):
    """
    Returns true if the file should not be traced.
    """
    return file_path.startswith(PTVSD_DIR_PATH) or file_path.endswith('ptvsd_launcher.py')


original_get_file_type = pydevd.PyDB.get_file_type


def _get_file_type(py_db, abs_real_path_and_basename, _cache_file_type={}):
    abs_path = abs_real_path_and_basename[0]
    try:
        return _cache_file_type[abs_path]
    except KeyError:
        file_type = original_get_file_type(py_db, abs_real_path_and_basename)
        if file_type is not None:
            _cache_file_type[abs_path] = file_type
        elif dont_trace_ptvsd_files(abs_path):
            _cache_file_type[abs_path] = PYDEV_FILE
        else:
            _cache_file_type[abs_path] = None
        return _cache_file_type[abs_path]


pydevd.PyDB.get_file_type = _get_file_type

# NOTE: Previously this included sys.prefix, sys.base_prefix and sys.real_prefix
# On some systems those resolve to '/usr'. That means any user code will
# also be treated as library code.
STDLIB_PATH_PREFIXES = []
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


if sys.version_info >= (3,):

    def unquote(s):
        return None if s is None else urllib.unquote(s)

else:

    # In Python 2, urllib.unquote doesn't handle Unicode strings correctly,
    # so we need to convert to ASCII first, unquote, and then decode.
    def unquote(s):
        if s is None:
            return None
        if not isinstance(s, bytes):
            s = bytes(s)
        s = urllib.unquote(s)
        if isinstance(s, bytes):
            s = s.decode('utf-8')
        return s


def unquote_xml_path(s):
    """XML unescape after url unquote. This reverses the escapes and quotes done
    by pydevd.
    """
    if s is None:
        return None
    return xml_unescape(unquote(s))


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


class PydevdSocket(object):
    """A dummy socket-like object for communicating with pydevd.

    It parses pydevd messages and redirects them to the provided handler
    callback.  It also provides an interface to send notifications and
    requests to pydevd; for requests, the reply can be asynchronously
    awaited.
    """

    def __init__(self, handle_msg, handle_close, getpeername, getsockname):
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

        Note that the data is always a full message received from pydevd
        (sent from _pydevd_bundle.pydevd_comm.WriterThread), so, there's
        no need to actually treat received bytes as a stream of bytes.
        """
        result = len(data)

        # Defer logging until we have as much information about the message
        # as possible - after decoding it, parsing it, determining whether
        # it's a response etc. This way it can be logged in the most readable
        # representation and with the most context.
        #
        # However, if something fails at any of those stages, we want to log
        # as much as we have by then. Thus, the format string for for trace()
        # is also constructed dynamically, reflecting the available info.

        trace_prefix = 'PYD --> '
        trace_fmt = '{data}'

        try:
            if data.startswith(b'{'):  # JSON
                data = data.decode('utf-8')
                data = json.loads(data)
                trace_fmt = '{data!j}'
                cmd_id = data['pydevd_cmd_id']
                if 'request_seq' in data:
                    seq = data['request_seq']
                else:
                    seq = data['seq']
                args = data
            else:
                assert data.endswith(b'\n')
                data = self._decode_and_unquote(data[:-1])
                cmd_id, seq, args = data.split('\t', 2)
                if ptvsd.log.is_enabled():
                    trace_fmt = '{cmd_name} {seq}\n{args}'
        except:
            ptvsd.log.exception(trace_prefix + trace_fmt, data=data)
            raise

        seq = int(seq)
        cmd_id = int(cmd_id)
        try:
            cmd_name = pydevd_comm.ID_TO_MEANING[str(cmd_id)]
        except KeyError:
            cmd_name = cmd_id

        with self.lock:
            loop, fut, requesting_handler = self.requests.pop(seq, (None, None, None))

        if requesting_handler is not None:
            trace_prefix = '(requested while handling {requesting_handler})\n' + trace_prefix
        ptvsd.log.debug(
            trace_prefix + trace_fmt,
            data=data,
            cmd_id=cmd_id,
            cmd_name=cmd_name,
            seq=seq,
            args=args,
            requesting_handler=requesting_handler,
        )

        if fut is None:
            with ptvsd.log.handling((cmd_name, seq)):
                self._handle_msg(cmd_id, seq, args)
        else:
            loop.call_soon_threadsafe(fut.set_result, (cmd_id, seq, args))

        return result

    sendall = send

    def makefile(self, *args, **kwargs):
        """Return a file-like wrapper around the socket."""
        return os.fdopen(self.pipe_r)

    def make_packet(self, cmd_id, args):
        assert not isinstance(args, bytes)
        with self.lock:
            seq = self.seq
            self.seq += 1

        if ptvsd.log.is_enabled():
            try:
                cmd_name = pydevd_comm.ID_TO_MEANING[str(cmd_id)]
            except KeyError:
                cmd_name = cmd_id
            ptvsd.log.debug('PYD <-- {0} {1} {2}', cmd_name, seq, args)

        s = '{}\t{}\t{}\n'.format(cmd_id, seq, args)
        return seq, s

    def make_json_packet(self, cmd_id, args):
        assert isinstance(args, dict)
        with self.lock:
            seq = self.seq
            self.seq += 1
            args['seq'] = seq

        ptvsd.log.debug('PYD <-- {0!j}', args)

        s = json.dumps(args)
        return seq, s

    def pydevd_notify(self, cmd_id, args, is_json=False):
        if self.pipe_w is None:
            raise EOFError
        if is_json:
            seq, s = self.make_json_packet(cmd_id, args)
        else:
            seq, s = self.make_packet(cmd_id, args)
        with self.lock:
            os.write(self.pipe_w, s.encode('utf8'))

    def pydevd_request(self, loop, cmd_id, args, is_json=False):
        '''
        If is_json == True the args are expected to be a dict to be
        json-serialized with the request, otherwise it's expected
        to be the text (to be concatenated with the command id and
        seq in the pydevd line-based protocol).
        '''
        if self.pipe_w is None:
            raise EOFError
        if is_json:
            seq, s = self.make_json_packet(cmd_id, args)
        else:
            seq, s = self.make_packet(cmd_id, args)
        fut = loop.create_future()

        with self.lock:
            self.requests[seq] = loop, fut, ptvsd.log.current_handler()
            as_bytes = s
            if not isinstance(as_bytes, bytes):
                as_bytes = as_bytes.encode('utf-8')
            if is_json:
                os.write(self.pipe_w, ('Content-Length:%s\r\n\r\n' % (len(as_bytes),)).encode('ascii'))
            os.write(self.pipe_w, as_bytes)

        return fut


class ExceptionsManager(object):

    def __init__(self, proc):
        self.proc = proc
        self.exceptions = {}
        self.lock = threading.Lock()

    def remove_exception_break(self, ex_type='python', exception='BaseException'):
        cmdargs = (ex_type, exception)
        msg = '{}-{}'.format(*cmdargs)
        self.proc.pydevd_notify(pydevd_comm.CMD_REMOVE_EXCEPTION_BREAK, msg)

    def remove_all_exception_breaks(self):
        with self.lock:
            for exception in self.exceptions.keys():
                self.remove_exception_break(exception=exception)
            self.exceptions = {}

    def _find_exception(self, name):
        if name in self.exceptions:
            return name

        for ex_name in self.exceptions.keys():
            # exception name can be in repr form
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
                            skip_stdlib=False, ex_type='python'):

        notify_on_handled_exceptions = 1 if break_raised else 0
        notify_on_unhandled_exceptions = 1 if break_uncaught else 0
        ignore_libraries = 1 if skip_stdlib else 0

        cmdargs = (
            ex_type,
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

        msg = '{}-{}\t{}\t{}\t{}'.format(*cmdargs)
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
            else:
                self.double_underscore.append(var)
        elif var_name.startswith('_'):
            self.single_underscore.append(var)
        else:
            self.variables.append(var)

    def get_sorted_variables(self):

        def get_sort_key(o):
            return o['name']

        self.variables.sort(key=get_sort_key)
        self.single_underscore.sort(key=get_sort_key)
        self.double_underscore.sort(key=get_sort_key)
        self.dunder.sort(key=get_sort_key)
        return self.variables + self.single_underscore + self.double_underscore + self.dunder  # noqa


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
    'BREAK_SYSTEMEXIT_ZERO': bool_parser,
    'REDIRECT_OUTPUT': bool_parser,
    'VERSION': unquote,
    'INTERPRETER_OPTIONS': unquote,
    'WEB_BROWSER_URL': unquote,
    'DJANGO_DEBUG': bool_parser,
    'FLASK_DEBUG': bool_parser,
    'FIX_FILE_PATH_CASE': bool_parser,
    'CLIENT_OS_TYPE': unquote,
    'DEBUG_STDLIB': bool_parser,
    'STOP_ON_ENTRY': bool_parser,
    'SHOW_RETURN_VALUE': bool_parser,
    'MULTIPROCESS': bool_parser,
}

DEBUG_OPTIONS_BY_FLAG = {
    'RedirectOutput': 'REDIRECT_OUTPUT=True',
    'WaitOnNormalExit': 'WAIT_ON_NORMAL_EXIT=True',
    'WaitOnAbnormalExit': 'WAIT_ON_ABNORMAL_EXIT=True',
    'BreakOnSystemExitZero': 'BREAK_SYSTEMEXIT_ZERO=True',
    'Django': 'DJANGO_DEBUG=True',
    'Flask': 'FLASK_DEBUG=True',
    'Jinja': 'FLASK_DEBUG=True',
    'FixFilePathCase': 'FIX_FILE_PATH_CASE=True',
    'DebugStdLib': 'DEBUG_STDLIB=True',
    'WindowsClient': 'CLIENT_OS_TYPE=WINDOWS',
    'UnixClient': 'CLIENT_OS_TYPE=UNIX',
    'StopOnEntry': 'STOP_ON_ENTRY=True',
    'ShowReturnValue': 'SHOW_RETURN_VALUE=True',
    'Multiprocess': 'MULTIPROCESS=True',
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
        BREAK_SYSTEMEXIT_ZERO=True|False
        REDIRECT_OUTPUT=True|False
        VERSION=string
        INTERPRETER_OPTIONS=string
        WEB_BROWSER_URL=string url
        DJANGO_DEBUG=True|False
        CLIENT_OS_TYPE=WINDOWS|UNIX
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

    if 'CLIENT_OS_TYPE' not in options:
        options['CLIENT_OS_TYPE'] = 'WINDOWS' if platform.system() == 'Windows' else 'UNIX'  # noqa

    return options

########################
# the message processor

# TODO: Embed instead of extend (inheritance -> composition).


class VSCodeMessageProcessorBase(ipcjson.SocketIO, ipcjson.IpcChannel):
    """The base class for VSC message processors."""

    def __init__(self, socket, notify_closing, timeout=None, own_socket=False):
        super(VSCodeMessageProcessorBase, self).__init__(
            socket=socket,
            own_socket=False,
            timeout=timeout,
        )
        self.socket = socket
        self._own_socket = own_socket
        self._notify_closing = notify_closing

        self.server_thread = None
        self._closing = False
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
    def closed(self):
        return self._closed or self._closing

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
                ptvsd.log.exception('Client socket closed', category='I')
                with self._connlock:
                    _util.lock_release(self._listening)
                    _util.lock_release(self._connected)
                self.close()
            except socket.error as exc:
                if exc.errno == errno.ECONNRESET:
                    ptvsd.log.exception('Client socket forcibly closed', category='I')
                    with self._connlock:
                        _util.lock_release(self._listening)
                        _util.lock_release(self._connected)
                    self.close()
                else:
                    raise exc

        self.server_thread = _util.new_hidden_thread(
            target=process_messages,
            name=threadname,
        )
        self.server_thread.start()

        # special initialization
        self.send_event(
            'output',
            category='telemetry',
            output='ptvsd',
            data={'version': __version__},
        )
        self.readylock.release()

    def close(self):
        """Stop the message processor and release its resources."""
        if self.closed:
            return
        self._closing = True
        ptvsd.log.debug('Raw closing')

        self._notify_closing()
        # Close the editor-side socket.
        self._stop_vsc_message_loop()

        # Ensure that the connection is marked as closed.
        with self._connlock:
            _util.lock_release(self._listening)
            _util.lock_release(self._connected)
        self._closed = True

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
                ptvsd.log.exception('Error on socket shutdown')

    # methods for subclasses to override

    def _start_event_loop(self):
        pass

    def _stop_event_loop(self):
        pass


INITIALIZE_RESPONSE = dict(
    supportsCompletionsRequest=True,
    supportsConditionalBreakpoints=True,
    supportsConfigurationDoneRequest=True,
    supportsDebuggerProperties=True,
    supportsDelayedStackTraceLoading=True,
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
    supportsGotoTargetsRequest=True,
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

    def __init__(
        self, socket, notify_disconnecting, notify_closing,
        notify_launch=None, notify_ready=None, timeout=None, debugging=True,
    ):
        super(VSCLifecycleMsgProcessor, self).__init__(
            socket=socket,
            notify_closing=notify_closing,
            timeout=timeout,
        )
        self._notify_launch = notify_launch or NOOP
        self._notify_ready = notify_ready or NOOP
        self._notify_disconnecting = notify_disconnecting

        self._stopped = False

        # These are needed to handle behavioral differences between VS and VSC
        # https://github.com/Microsoft/VSDebugAdapterHost/wiki/Differences-between-Visual-Studio-Code-and-the-Visual-Studio-Debug-Adapter-Host # noqa
        # VS expects a single stopped event in a multi-threaded scenario.
        self._client_id = None

        # adapter state
        self.start_reason = None
        self.debug_options = {}
        self._statelock = threading.Lock()
        self._debugging = debugging
        self._debuggerstopped = False
        self._restart_debugger = False
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

        t = _util.new_hidden_thread(
            target=stop,
            name='stopping',
            daemon=False,
        )
        t.start()

    def handle_exiting(self, exitcode=None, wait=None):
        """Deal with the debuggee exiting."""
        with self._statelock:
            if self._exiting:
                return
            self._exiting = True

        # Notify the editor that the "debuggee" (e.g. script, app) exited.
        self.send_event('exited', exitCode=exitcode or 0)

        self._waiting = True
        if wait is not None and self.start_reason == 'launch':
            normal, abnormal = self._wait_options()
            cfg = (normal and not exitcode) or (abnormal and exitcode)
            # This must be done before we send a disconnect response
            # (which implies before we close the client socket).
            wait(cfg)

        # If we are exiting then pydevd must have stopped.
        self._ensure_debugger_stopped()

        if self._exitlock is not None:
            _util.lock_release(self._exitlock)

    # VSC protocol handlers

    def on_initialize(self, request, args):
        self._client_id = args.get('clientID', None)
        self._restart_debugger = False
        self.is_process_created = False
        self.send_response(request, **INITIALIZE_RESPONSE)
        self.send_event('initialized')

    def on_attach(self, request, args):
        multiproc.root_start_request = request
        self.start_reason = 'attach'
        self._set_debug_options(args)
        self._handle_launch_or_attach(request, args)
        self.send_response(request)

    def on_launch(self, request, args):
        multiproc.root_start_request = request
        self.start_reason = 'launch'
        self._set_debug_options(args)
        self._notify_launch()
        self._handle_launch_or_attach(request, args)
        self.send_response(request)

    def on_disconnect(self, request, args):
        multiproc.kill_subprocesses()

        debugger_attached.clear()
        self._restart_debugger = args.get('restart', False)

        # TODO: docstring
        if self._debuggerstopped:  # A "terminated" event must have been sent.
            self._wait_until_exiting(self.EXITWAIT)

        status = {'sent': False}

        def disconnect_response():
            if status['sent']:
                return
            self.send_response(request)
            status['sent'] = True

        self._notify_disconnecting(
            pre_socket_close=disconnect_response,
        )
        disconnect_response()

        self._set_disconnected()

        if self.start_reason == 'attach':
            if not self._debuggerstopped:
                self._handle_detach()
        # TODO: We should be able drop the "launch" branch.
        elif self.start_reason == 'launch':
            if not self.closed:
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
        if not self._restart_debugger:
            # multiproc.initial_request = None
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

    def _handle_configurationDone(self, request, args):
        pass

    def _handle_launch_or_attach(self, request, args):
        pass

    def _handle_detach(self):
        pass


class VSCodeMessageProcessor(VSCLifecycleMsgProcessor):
    """IPC JSON message processor for VSC debugger protocol.

    This translates between the VSC debugger protocol and the pydevd
    protocol.
    """

    def __init__(
        self, socket, pydevd_notify, pydevd_request,
        notify_debugger_ready,
        notify_disconnecting, notify_closing,
        timeout=None,
    ):
        super(VSCodeMessageProcessor, self).__init__(
            socket=socket,
            notify_disconnecting=notify_disconnecting,
            notify_closing=notify_closing,
            timeout=timeout,
        )
        self._pydevd_notify = pydevd_notify
        self._pydevd_request = pydevd_request
        self._notify_debugger_ready = notify_debugger_ready

        self.loop = None
        self.event_loop_thread = None

        # debugger state
        self.is_process_created = False
        self.is_process_created_lock = threading.Lock()
        self.thread_map = IDMap()
        self._path_mappings = []
        self.exceptions_mgr = ExceptionsManager(self)
        self.internals_filter = InternalsFilter()
        self.new_thread_lock = threading.Lock()

        # goto
        self.goto_target_map = IDMap()
        self.current_goto_request = None

        # adapter state
        self._detached = False
        self._path_mappings_received = False
        self._path_mappings_applied = False

    def _start_event_loop(self):
        self.loop = futures.EventLoop()
        self.event_loop_thread = _util.new_hidden_thread(
            target=self.loop.run_forever,
            name='EventLoop',
        )
        self.event_loop_thread.start()

    def _stop_event_loop(self):
        self.loop.stop()
        self.event_loop_thread.join(WAIT_FOR_THREAD_FINISH_TIMEOUT)

    def start(self, threadname):
        super(VSCodeMessageProcessor, self).start(threadname)
        if options.multiprocess:
            self.start_subprocess_notifier()

    def start_subprocess_notifier(self):
        self._subprocess_notifier_thread = _util.new_hidden_thread('SubprocessNotifier', self._subprocess_notifier)
        self._subprocess_notifier_thread.start()

    def close(self):
        super(VSCodeMessageProcessor, self).close()
        if options.multiprocess:
            self._subprocess_notifier_thread.join()

    def _subprocess_notifier(self):
        while not self.closed:
            try:
                subprocess_request, subprocess_response = multiproc.subprocess_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                self.send_event('ptvsd_subprocess', **subprocess_request)
            except Exception:
                pass
            else:
                subprocess_response['incomingConnection'] = True

            multiproc.subprocess_queue.task_done()

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
            return m(self, self.loop, *args, **kwargs)

        return f

    def sleep(self):
        fut = futures.Future(self.loop)
        self.loop.call_soon(lambda: fut.set_result(None))
        return fut

    # PyDevd "socket" entry points (and related helpers)

    def pydevd_notify(self, cmd_id, args, is_json=False):
        return self._pydevd_notify(cmd_id, args, is_json=is_json)

    def pydevd_request(self, cmd_id, args, is_json=False):
        return self._pydevd_request(self.loop, cmd_id, args, is_json=is_json)

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
        if not self._detached:
            try:
                f = self.pydevd_events[cmd_id]
            except KeyError:
                raise UnsupportedPyDevdCommandError(cmd_id)
            return f(self, seq, args)
        else:
            return None

    @staticmethod
    def parse_xml_response(args):
        return untangle.parse(io.BytesIO(args.encode('utf8'))).xml

    def _wait_for_pydevd_ready(self):
        # TODO: Call self._ensure_pydevd_requests_handled?
        pass

    def _ensure_pydevd_requests_handled(self):
        # PyDevd guarantees that a response means all previous requests
        # have been handled.  (PyDevd handles messages sequentially.)
        # See GH-448.
        #
        # This is particularly useful for those requests that do not
        # have responses (e.g. CMD_SET_BREAK).
        return self._send_cmd_version_command()

    # VSC protocol handlers

    @async_handler
    def on_configurationDone(self, request, args):
        self._process_debug_options(self.debug_options)
        yield self._ensure_pydevd_requests_handled()

        debugger_attached.set()

        self.pydevd_request(pydevd_comm.CMD_RUN, '')
        self._wait_for_pydevd_ready()
        self._notify_debugger_ready()

        # Send event notifying the creation of the process.
        # If we do not do this and try to pause, VSC throws errors,
        # complaining about debugger still initializing.
        with self.is_process_created_lock:
            if not self.is_process_created:
                self.is_process_created = True
                self.send_process_event(self.start_reason)

        self._notify_ready()
        self.send_response(request)

    def _process_debug_options(self, opts):
        """Process the launch arguments to configure the debugger."""
        if opts.get('REDIRECT_OUTPUT', False):
            redirect_output = 'STDOUT\tSTDERR'
        else:
            redirect_output = ''
        self.pydevd_request(pydevd_comm.CMD_REDIRECT_OUTPUT, redirect_output)

        if opts.get('STOP_ON_ENTRY', False) and self.start_reason == 'launch':
            info = pydevd_additional_thread_info.set_additional_thread_info(ptvsd.main_thread)
            info.pydev_step_cmd = pydevd_comm.CMD_STEP_INTO_MY_CODE

        if opts.get('SHOW_RETURN_VALUE', False):
            self.pydevd_request(pydevd_comm.CMD_SHOW_RETURN_VALUES, '1\t1')

        if opts.get('MULTIPROCESS', False):
            if not options.multiprocess:
                options.multiprocess = True
                multiproc.listen_for_subprocesses()
                self.start_subprocess_notifier()

        # Print on all but NameError, don't suspend on any.
        msg = json.dumps(dict(
            skip_suspend_on_breakpoint_exception=('BaseException',),
            skip_print_breakpoint_exception=('NameError',),
            multi_threads_single_notification=True,
        ))
        if isinstance(msg, bytes):
            msg = msg.decode('utf-8')
        self.pydevd_request(pydevd_comm.CMD_PYDEVD_JSON_CONFIG, msg)

    def _is_just_my_code_stepping_enabled(self):
        """Returns true if just-me-code stepping is enabled.

        Note: for now we consider DEBUG_STDLIB = False as just-my-code.
        """
        dbg_stdlib = self.debug_options.get('DEBUG_STDLIB', False)
        return not dbg_stdlib

    def _is_stdlib(self, filepath):
        filepath = os.path.normcase(os.path.normpath(filepath))
        for prefix in STDLIB_PATH_PREFIXES:
            if prefix != '' and filepath.startswith(prefix):
                return True
        return filepath.startswith(NORM_PTVSD_DIR_PATH)

    def _should_debug(self, filepath):
        if self._is_just_my_code_stepping_enabled() and \
           self._is_stdlib(filepath):
            return False
        return True

    def _resolve_remote_root(self, local_root, remote_root):
        if remote_root == '.':
            cwd = os.getcwd()
            append_pathsep = local_root.endswith('\\') or local_root.endswith('/')
            return cwd + (os.path.sep if append_pathsep else '')
        return remote_root

    def _initialize_path_maps(self, args):
        self._path_mappings = []
        for pathMapping in args.get('pathMappings', []):
            localRoot = pathMapping.get('localRoot', '')
            remoteRoot = pathMapping.get('remoteRoot', '')
            remoteRoot = self._resolve_remote_root(localRoot, remoteRoot)
            if (len(localRoot) > 0 and len(remoteRoot) > 0):
                self._path_mappings.append((localRoot, remoteRoot))

        if len(self._path_mappings) > 0:
            pydevd_file_utils.setup_client_server_paths(self._path_mappings)

        self._path_mappings_applied = True

    def _send_cmd_version_command(self):
        cmd = pydevd_comm.CMD_VERSION
        default_os_type = 'WINDOWS' if platform.system() == 'Windows' else 'UNIX'
        client_os_type = self.debug_options.get('CLIENT_OS_TYPE', default_os_type)
        os_id = client_os_type
        msg = '1.1\t{}\tID'.format(os_id)
        return self.pydevd_request(cmd, msg)

    @async_handler
    def _handle_launch_or_attach(self, request, args):
        self._path_mappings_received = True

        self.pydevd_request(pydevd_comm.CMD_SET_PROTOCOL, 'json')
        yield self._send_cmd_version_command()

        pydevd_request = copy.deepcopy(request)
        del pydevd_request['seq']  # A new seq should be created for pydevd.
        yield self.pydevd_request(-1, pydevd_request, is_json=True)

        self._initialize_path_maps(args)

    def _handle_detach(self):
        ptvsd.log.info('Detaching ...')
        # TODO: Skip if already detached?
        self._detached = True

        self._clear_output_redirection()
        self.exceptions_mgr.remove_all_exception_breaks()

        # No related pydevd command id (removes all breaks and resumes threads).
        self.pydevd_request(
            -1,
            {"command": "disconnect", "arguments": {}, "type": "request"},
            is_json=True
        )

    def _clear_output_redirection(self):
        self.pydevd_request(pydevd_comm.CMD_REDIRECT_OUTPUT, '')

    def _resume_all_threads(self):
        self.pydevd_notify(pydevd_comm.CMD_THREAD_RUN, '*')

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
            xthreads = resp_args['body']['threads']
        except KeyError:
            xthreads = []

        threads = []
        with self.new_thread_lock:
            for xthread in xthreads:
                try:
                    name = xthread['name']
                except KeyError:
                    name = '<Unable to get thread name>'

                pyd_tid = xthread['id']
                try:
                    vsc_tid = self.thread_map.to_vscode(pyd_tid,
                                                        autogen=False)
                except KeyError:
                    # This is a previously unseen thread
                    vsc_tid = self.thread_map.to_vscode(pyd_tid,
                                                        autogen=True)
                    self.send_event('thread', reason='started',
                                    threadId=vsc_tid)

                threads.append({'id': vsc_tid, 'name': name})

        self.send_response(request, threads=threads)

    @async_handler
    def on_source(self, request, args):
        """Request to get the source"""
        source_reference = args.get('sourceReference', 0)

        if source_reference == 0:
            self.send_error_response(request, 'Source unavailable')
        else:
            pydevd_request = copy.deepcopy(request)
            del pydevd_request['seq']  # A new seq should be created for pydevd.
            _, _, resp_args = yield self.pydevd_request(
                pydevd_comm.CMD_LOAD_SOURCE,
                pydevd_request,
                is_json=True)

            if resp_args.get('success', True):
                self.send_response(request, **resp_args['body'])
            else:
                self.send_error_response(request, resp_args.get('message', 'Error retrieving source'))

    @async_handler
    def on_stackTrace(self, request, args):
        vsc_tid = int(args['threadId'])

        try:
            pyd_tid = self.thread_map.to_pydevd(vsc_tid)
        except KeyError:
            # Unknown thread, nothing much we can do about it here
            self.send_error_response(
                request,
                'Thread {} not found'.format(vsc_tid))
            return
        pydevd_request = copy.deepcopy(request)
        del pydevd_request['seq']  # A new seq should be created for pydevd.
        # Translate threadId for pydevd.
        pydevd_request['arguments']['threadId'] = pyd_tid
        _, _, resp_args = yield self.pydevd_request(
            pydevd_comm.CMD_GET_THREAD_STACK,
            pydevd_request,
            is_json=True)

        levels = int(args.get('levels', 0))
        stackFrames = resp_args['body']['stackFrames']
        if levels > 0:
            start = int(args.get('startFrame', 0))
            end = min(start + levels, len(stackFrames))
            stackFrames = resp_args['body']['stackFrames'][start:end]
        totalFrames = resp_args['body']['totalFrames']
        self.send_response(request, stackFrames=stackFrames, totalFrames=totalFrames)

    @async_handler
    def on_scopes(self, request, args):
        pydevd_request = copy.deepcopy(request)
        del pydevd_request['seq']  # A new seq should be created for pydevd.
        _, _, resp_args = yield self.pydevd_request(
            -1,
            pydevd_request,
            is_json=True)

        scopes = resp_args['body']['scopes']
        self.send_response(request, scopes=scopes)

    @async_handler
    def on_variables(self, request, args):
        """Handles DAP VariablesRequest."""
        pydevd_request = copy.deepcopy(request)
        del pydevd_request['seq']  # A new seq should be created for pydevd.
        _, _, resp_args = yield self.pydevd_request(
            pydevd_comm.CMD_GET_VARIABLE,
            pydevd_request,
            is_json=True)

        variables = resp_args['body']['variables']
        self.send_response(request, variables=variables)

    @async_handler
    def on_setVariable(self, request, args):
        """Handles DAP SetVariableRequest."""
        var_name = args['name']

        if var_name.startswith('(return) '):
            self.send_error_response(
                request,
                'Cannot change return value')
            return

        pydevd_request = copy.deepcopy(request)
        del pydevd_request['seq']  # A new seq should be created for pydevd.
        _, _, resp_args = yield self.pydevd_request(
            pydevd_comm.CMD_CHANGE_VARIABLE,
            pydevd_request,
            is_json=True)

        body = resp_args['body']
        self.send_response(request, **body)

    @async_handler
    def on_evaluate(self, request, args):
        """Handles DAP EvaluateRequest."""

        pydevd_request = copy.deepcopy(request)
        del pydevd_request['seq']  # A new seq should be created for pydevd.
        _, _, resp_args = yield self.pydevd_request(
            pydevd_comm.CMD_EVALUATE_EXPRESSION,
            pydevd_request,
            is_json=True)

        body = resp_args['body']

        # Currently there is an issue in VSC where returning success=false for a eval request,
        # in repl context. VSC does not show the error response in the debug console.
        if args.get('context', None) == 'repl' and not resp_args['success']:
            body['result'] = resp_args['message']
        self.send_response(request, **body)

    @async_handler
    def on_setExpression(self, request, args):
        pydevd_request = copy.deepcopy(request)
        del pydevd_request['seq']  # A new seq should be created for pydevd.
        _, _, resp_args = yield self.pydevd_request(
            -1,
            pydevd_request,
            is_json=True)

        body = resp_args['body']
        self.send_response(request, **body)

    @async_handler
    def on_modules(self, request, args):
        pydevd_request = copy.deepcopy(request)
        del pydevd_request['seq']  # A new seq should be created for pydevd.
        _, _, resp_args = yield self.pydevd_request(
            -1,
            pydevd_request,
            is_json=True)

        body = resp_args.get('body', {})
        self.send_response(request, **body)

    @async_handler
    def on_pause(self, request, args):
        # Pause requests cannot be serviced until pydevd is fully initialized.
        with self.is_process_created_lock:
            if not self.is_process_created:
                self.send_response(
                    request,
                    success=False,
                    message='Cannot pause while debugger is initializing',
                )
                return

        pydevd_request = copy.deepcopy(request)
        del pydevd_request['seq']  # A new seq should be created for pydevd.
        try:
            pydevd_request['arguments']['threadId'] = '*'
        except KeyError:
            pydevd_request['arguments'] = {'threadId': '*'}

        # Always suspend all threads.
        yield self.pydevd_request(pydevd_comm.CMD_THREAD_SUSPEND,
                                  pydevd_request, is_json=True)
        self.send_response(request)

    @async_handler
    def on_continue(self, request, args):

        pydevd_request = copy.deepcopy(request)
        del pydevd_request['seq']  # A new seq should be created for pydevd.
        try:
            pydevd_request['arguments']['threadId'] = '*'
        except KeyError:
            pydevd_request['arguments'] = {'threadId': '*'}

        # Always continue all threads.
        yield self.pydevd_request(pydevd_comm.CMD_THREAD_RUN,
                                  pydevd_request, is_json=True)
        self.send_response(request, allThreadsContinued=True)

    @async_handler
    def on_next(self, request, args):

        pyd_tid = self.thread_map.to_pydevd(int(args['threadId']))

        pydevd_request = copy.deepcopy(request)
        del pydevd_request['seq']  # A new seq should be created for pydevd.
        pydevd_request['arguments']['threadId'] = pyd_tid
        cmd_id = pydevd_comm.CMD_STEP_OVER

        yield self.pydevd_request(cmd_id, pydevd_request, is_json=True)
        self.send_response(request)

    @async_handler
    def on_stepIn(self, request, args):

        pyd_tid = self.thread_map.to_pydevd(int(args['threadId']))

        pydevd_request = copy.deepcopy(request)
        del pydevd_request['seq']  # A new seq should be created for pydevd.
        pydevd_request['arguments']['threadId'] = pyd_tid
        cmd_id = pydevd_comm.CMD_STEP_INTO

        yield self.pydevd_request(cmd_id, pydevd_request, is_json=True)
        self.send_response(request)

    @async_handler
    def on_stepOut(self, request, args):

        pyd_tid = self.thread_map.to_pydevd(int(args['threadId']))

        pydevd_request = copy.deepcopy(request)
        del pydevd_request['seq']  # A new seq should be created for pydevd.
        pydevd_request['arguments']['threadId'] = pyd_tid
        cmd_id = pydevd_comm.CMD_STEP_RETURN

        yield self.pydevd_request(cmd_id, pydevd_request, is_json=True)
        self.send_response(request)

    @async_handler
    def on_gotoTargets(self, request, args):
        path = args['source']['path']
        line = args['line']
        target_id = self.goto_target_map.to_vscode((path, line), autogen=True)
        self.send_response(request, targets=[{
            'id': target_id,
            'label': '{}:{}'.format(path, line),
            'line': line,
        }])

    @async_handler
    def on_goto(self, request, args):
        if self.current_goto_request is not None:
            self.send_error_response(request, 'Already processing a "goto" request.')
            return

        vsc_tid = args['threadId']
        target_id = args['targetId']

        pyd_tid = self.thread_map.to_pydevd(vsc_tid)
        path, line = self.goto_target_map.to_pydevd(target_id)

        self.current_goto_request = request
        self.pydevd_notify(
            pydevd_comm.CMD_SET_NEXT_STATEMENT,
            '{}\t{}\t*'.format(pyd_tid, line))

    @async_handler
    def on_setBreakpoints(self, request, args):
        if not self._path_mappings_received:
            self.send_error_response(request, "'setBreakpoints' request must be issued after 'launch' or 'attach' request.")
            return

        # There might be a concurrent 'launch' or 'attach' request in flight that hasn't
        # gotten to processing path mappings yet. If so, spin until it finishes that.
        while not self._path_mappings_applied:
            yield self.sleep()

        pydevd_request = copy.deepcopy(request)
        del pydevd_request['seq']  # A new seq should be created for pydevd.

        # Validate breakpoints and adjust their positions.
        args = pydevd_request['arguments']
        if 'breakpoints' in args and 'path' in args['source']:
            path = args['source']['path']
            if sys.version_info < (3,) and not isinstance(path, bytes):
                path = path.encode(sys.getfilesystemencoding())
            path = path_to_unicode(pydevd_file_utils.norm_file_to_server(path))

        try:
            lines = sorted(_util.get_code_lines(path))
        except Exception:
            pass
        else:
            for bp in args['breakpoints']:
                line = bp['line']
                if line not in lines:
                    # Adjust to the first preceding valid line.
                    idx = bisect.bisect_left(lines, line)
                    if idx > 0:
                        bp['line'] = lines[idx - 1]

        _, _, resp_args = yield self.pydevd_request(
            pydevd_comm.CMD_SET_BREAK,
            pydevd_request,
            is_json=True)

        breakpoints = resp_args['body']['breakpoints']
        self.send_response(request, breakpoints=breakpoints)

    def _get_pydevex_type(self):
        if self.debug_options.get('DJANGO_DEBUG', False):
            return 'django'
        elif self.debug_options.get('FLASK_DEBUG', False):
            return 'jinja2'
        return 'python'

    @async_handler
    def on_setExceptionBreakpoints(self, request, args):
        # TODO: docstring
        filters = args['filters']
        exception_options = args.get('exceptionOptions', [])
        jmc = self._is_just_my_code_stepping_enabled()

        pydevex_type = self._get_pydevex_type()
        if exception_options:
            self.exceptions_mgr.apply_exception_options(
                exception_options, jmc)
            if pydevex_type != 'python':
                self.exceptions_mgr.remove_exception_break(ex_type=pydevex_type)
                self.exceptions_mgr.add_exception_break(
                    'BaseException', True, True,
                    skip_stdlib=jmc, ex_type=pydevex_type)
        else:
            self.exceptions_mgr.remove_all_exception_breaks()
            break_raised = 'raised' in filters
            break_uncaught = 'uncaught' in filters
            if break_raised or break_uncaught:
                self.exceptions_mgr.add_exception_break(
                    'BaseException', break_raised, break_uncaught,
                    skip_stdlib=jmc)
                if pydevex_type != 'python':
                    self.exceptions_mgr.remove_exception_break(ex_type=pydevex_type)
                    self.exceptions_mgr.add_exception_break(
                        'BaseException', break_raised, break_uncaught,
                        skip_stdlib=jmc, ex_type=pydevex_type)

        if request is not None:
            self.send_response(request)

    @async_handler
    def on_exceptionInfo(self, request, args):
        pyd_tid = self.thread_map.to_pydevd(args['threadId'])

        pydevd_request = copy.deepcopy(request)
        del pydevd_request['seq']  # A new seq should be created for pydevd.
        pydevd_request['arguments']['threadId'] = pyd_tid
        _, _, resp_args = yield self.pydevd_request(
            pydevd_comm.CMD_GET_EXCEPTION_DETAILS,
            pydevd_request,
            is_json=True)

        body = resp_args['body']
        body['breakMode'] = self.exceptions_mgr.get_break_mode(body['exceptionId'])
        self.send_response(request, **body)

    @async_handler
    def on_completions(self, request, args):
        pydevd_request = copy.deepcopy(request)
        del pydevd_request['seq']  # A new seq should be created for pydevd.
        _, _, resp_args = yield self.pydevd_request(
            pydevd_comm.CMD_GET_COMPLETIONS,
            pydevd_request,
            is_json=True)

        targets = resp_args['body']['targets']
        self.send_response(request, targets=targets)

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
                'bitness': 64 if sys.maxsize > 2 ** 32 else 32,
            },
        }
        self.send_response(request, **sys_info)

    # VS specific custom message handlers
    @async_handler
    def on_setDebuggerProperty(self, request, args):
        if 'JustMyCodeStepping' in args:
            jmc = int(args.get('JustMyCodeStepping', 0)) > 0
            self.debug_options['DEBUG_STDLIB'] = not jmc

        self.send_response(request)

    # PyDevd protocol event handlers

    @pydevd_events.handler(pydevd_comm.CMD_MODULE_EVENT)
    def on_pydevd_module_event(self, seq, args):
        body = args.get('body', {})
        self.send_event('module', **body)

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
        '''
        :param args: dict.
            i.e.:
            {
                'type': 'event',
                'event': 'thread',
                'seq': 4,
                'pydevd_cmd_id': 103
                'body': {'reason': 'started', 'threadId': 'pid_9236_id_2714288164368'},
            }
        '''
        # If this is the first thread reported, report process creation
        # as well.
        with self.is_process_created_lock:
            if not self.is_process_created:
                if not debugger_attached.isSet():
                    return
                self.is_process_created = True
                self.send_process_event(self.start_reason)

        body = args['body']
        with self.new_thread_lock:
            pyd_tid = body['threadId']
            try:
                tid = self.thread_map.to_vscode(pyd_tid,
                                                autogen=False)
            except KeyError:
                tid = self.thread_map.to_vscode(pyd_tid,
                                                autogen=True)
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
        pass  # We only care about the thread suspend single notification.

    @pydevd_events.handler(pydevd_comm.CMD_THREAD_RUN)
    def on_pydevd_thread_run(self, seq, args):
        pass  # We only care about the thread suspend single notification.

    @pydevd_events.handler(pydevd_comm_constants.CMD_THREAD_SUSPEND_SINGLE_NOTIFICATION)
    @async_handler
    def on_pydevd_thread_suspend_single_notification(self, seq, args):
        # NOTE: We should add the thread to VSC thread map only if the
        # thread is seen here for the first time in 'attach' scenario.
        # If we are here in 'launch' scenario and we get KeyError then
        # there is an issue in reporting of thread creation.
        suspend_info = json.loads(args)
        pyd_tid = suspend_info['thread_id']
        reason = suspend_info['stop_reason']
        autogen = self.start_reason == 'attach'
        vsc_tid = self.thread_map.to_vscode(pyd_tid, autogen=autogen)

        exc_desc = None
        exc_name = None
        extra = {}
        if reason in STEP_REASONS:
            reason = 'step'
        elif reason in EXCEPTION_REASONS:
            reason = 'exception'
        elif reason == pydevd_comm.CMD_SET_BREAK:
            reason = 'breakpoint'
        else:
            reason = 'pause'

        extra['preserveFocusHint'] = \
            reason not in ['step', 'exception', 'breakpoint']

        if reason == 'exception':
            pydevd_request = {
                'type': 'request',
                'command': 'exceptionInfo',
                'arguments': {
                    'threadId': pyd_tid
                },
            }

            _, _, resp_args = yield self.pydevd_request(
                pydevd_comm.CMD_GET_EXCEPTION_DETAILS,
                pydevd_request,
                is_json=True)
            exc_name = resp_args['body']['exceptionId']
            exc_desc = resp_args['body']['description']

        if not self.debug_options.get('BREAK_SYSTEMEXIT_ZERO', False):
            # SystemExit is qualified on Python 2, and unqualified on Python 3
            sysexit_exc_name = 'exceptions.SystemExit' if sys.version_info < (3,) else 'SystemExit'
            if exc_name == sysexit_exc_name:
                try:
                    exit_code = int(exc_desc)
                except ValueError:
                    # It is legal to invoke exit() with a non-integer argument, and SystemExit will
                    # pass that through. It's considered an error exit, same as non-zero integer.
                    ignore = False
                else:
                    ignore = (exit_code == 0)
                if ignore:
                    self._resume_all_threads()
                    return

        extra['allThreadsStopped'] = True
        self.send_event(
            'stopped',
            reason=reason,
            threadId=vsc_tid,
            text=exc_name,
            description=exc_desc,
            **extra)

    @pydevd_events.handler(pydevd_comm_constants.CMD_THREAD_RESUME_SINGLE_NOTIFICATION)
    def on_pydevd_thread_resume_single_notification(self, seq, args):
        resumed_info = json.loads(args)
        pyd_tid = resumed_info['thread_id']

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
        pass

    @pydevd_events.handler(pydevd_comm.CMD_WRITE_TO_CONSOLE)
    def on_pydevd_cmd_write_to_console2(self, seq, args):
        """Handle console output"""
        body = args.get('body', {})
        self.send_event('output', **body)

    @pydevd_events.handler(pydevd_comm.CMD_GET_BREAKPOINT_EXCEPTION)
    def on_pydevd_get_breakpoint_exception(self, seq, args):
        # If pydevd sends exception info from a failed breakpoint condition, just ignore.
        pass

    @pydevd_events.handler(pydevd_comm.CMD_PROCESS_CREATED)
    def on_pydevd_process_create(self, seq, args):
        pass

    @pydevd_events.handler(pydevd_comm.CMD_SET_NEXT_STATEMENT)
    def on_pydevd_set_next_statement(self, seq, args):
        goto_request = self.current_goto_request
        assert goto_request is not None
        self.current_goto_request = None

        success, message = args.split('\t', 2)

        if success == 'True':
            self.send_response(goto_request)
        else:
            self.send_error_response(goto_request, message)
