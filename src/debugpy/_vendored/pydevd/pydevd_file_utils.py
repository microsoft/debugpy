r'''
    This module provides utilities to get the absolute filenames so that we can be sure that:
        - The case of a file will match the actual file in the filesystem (otherwise breakpoints won't be hit).
        - Providing means for the user to make path conversions when doing a remote debugging session in
          one machine and debugging in another.

    To do that, the PATHS_FROM_ECLIPSE_TO_PYTHON constant must be filled with the appropriate paths.

    @note:
        in this context, the server is where your python process is running
        and the client is where eclipse is running.

    E.g.:
        If the server (your python process) has the structure
            /user/projects/my_project/src/package/module1.py

        and the client has:
            c:\my_project\src\package\module1.py

        the PATHS_FROM_ECLIPSE_TO_PYTHON would have to be:
            PATHS_FROM_ECLIPSE_TO_PYTHON = [(r'c:\my_project\src', r'/user/projects/my_project/src')]

        alternatively, this can be set with an environment variable from the command line:
           set PATHS_FROM_ECLIPSE_TO_PYTHON=[['c:\my_project\src','/user/projects/my_project/src']]

    @note: DEBUG_CLIENT_SERVER_TRANSLATION can be set to True to debug the result of those translations

    @note: the case of the paths is important! Note that this can be tricky to get right when one machine
    uses a case-independent filesystem and the other uses a case-dependent filesystem (if the system being
    debugged is case-independent, 'normcase()' should be used on the paths defined in PATHS_FROM_ECLIPSE_TO_PYTHON).

    @note: all the paths with breakpoints must be translated (otherwise they won't be found in the server)

    @note: to enable remote debugging in the target machine (pydev extensions in the eclipse installation)
        import pydevd;pydevd.settrace(host, stdoutToServer, stderrToServer, port, suspend)

        see parameter docs on pydevd.py

    @note: for doing a remote debugging session, all the pydevd_ files must be on the server accessible
        through the PYTHONPATH (and the PATHS_FROM_ECLIPSE_TO_PYTHON only needs to be set on the target
        machine for the paths that'll actually have breakpoints).
'''

from _pydev_bundle import pydev_log
from _pydevd_bundle.pydevd_constants import IS_PY2, IS_PY3K, DebugInfoHolder, IS_WINDOWS, IS_JYTHON
from _pydev_bundle._pydev_filesystem_encoding import getfilesystemencoding
from _pydevd_bundle.pydevd_comm_constants import file_system_encoding, filesystem_encoding_is_utf8
from _pydev_bundle.pydev_log import error_once

import json
import os.path
import sys
import itertools
import ntpath
from functools import partial

_nt_os_normcase = ntpath.normcase
basename = os.path.basename
os_path_exists = os.path.exists
join = os.path.join

try:
    FileNotFoundError
except NameError:
    FileNotFoundError = IOError  # noqa

try:
    rPath = os.path.realpath  # @UndefinedVariable
except:
    # jython does not support os.path.realpath
    # realpath is a no-op on systems without islink support
    rPath = os.path.abspath


def _get_library_dir():
    library_dir = None
    try:
        import sysconfig
        library_dir = sysconfig.get_path('purelib')
    except ImportError:
        pass  # i.e.: Only 2.7 onwards

    if library_dir is None or not os_path_exists(library_dir):
        for path in sys.path:
            if os_path_exists(path) and os.path.basename(path) == 'site-packages':
                library_dir = path
                break

    if library_dir is None or not os_path_exists(library_dir):
        library_dir = os.path.dirname(os.__file__)

    return library_dir


# Note: we can't call sysconfig.get_path from _NormPath (it deadlocks on Python 2.7) so, we
# need to get the library dir during module loading.
_library_dir = _get_library_dir()

# defined as a list of tuples where the 1st element of the tuple is the path in the client machine
# and the 2nd element is the path in the server machine.
# see module docstring for more details.
try:
    PATHS_FROM_ECLIPSE_TO_PYTHON = json.loads(os.environ.get('PATHS_FROM_ECLIPSE_TO_PYTHON', '[]'))
except Exception:
    pydev_log.critical('Error loading PATHS_FROM_ECLIPSE_TO_PYTHON from environment variable.')
    pydev_log.exception()
    PATHS_FROM_ECLIPSE_TO_PYTHON = []
else:
    if not isinstance(PATHS_FROM_ECLIPSE_TO_PYTHON, list):
        pydev_log.critical('Expected PATHS_FROM_ECLIPSE_TO_PYTHON loaded from environment variable to be a list.')
        PATHS_FROM_ECLIPSE_TO_PYTHON = []
    else:
        # Converting json lists to tuple
        PATHS_FROM_ECLIPSE_TO_PYTHON = [tuple(x) for x in PATHS_FROM_ECLIPSE_TO_PYTHON]

# example:
# PATHS_FROM_ECLIPSE_TO_PYTHON = [
#  (r'd:\temp\temp_workspace_2\test_python\src\yyy\yyy',
#   r'd:\temp\temp_workspace_2\test_python\src\hhh\xxx')
# ]

convert_to_long_pathname = lambda filename:filename
convert_to_short_pathname = lambda filename:filename
get_path_with_real_case = lambda filename:filename

if sys.platform == 'win32':
    try:
        import ctypes
        from ctypes.wintypes import MAX_PATH, LPCWSTR, LPWSTR, DWORD

        GetLongPathName = ctypes.windll.kernel32.GetLongPathNameW  # noqa
        GetLongPathName.argtypes = [LPCWSTR, LPWSTR, DWORD]
        GetLongPathName.restype = DWORD

        GetShortPathName = ctypes.windll.kernel32.GetShortPathNameW  # noqa
        GetShortPathName.argtypes = [LPCWSTR, LPWSTR, DWORD]
        GetShortPathName.restype = DWORD

        def _convert_to_long_pathname(filename):
            buf = ctypes.create_unicode_buffer(MAX_PATH)

            if IS_PY2 and isinstance(filename, str):
                filename = filename.decode(getfilesystemencoding())
            rv = GetLongPathName(filename, buf, MAX_PATH)
            if rv != 0 and rv <= MAX_PATH:
                filename = buf.value

            if IS_PY2:
                filename = filename.encode(getfilesystemencoding())
            return filename

        def _convert_to_short_pathname(filename):
            buf = ctypes.create_unicode_buffer(MAX_PATH)

            if IS_PY2 and isinstance(filename, str):
                filename = filename.decode(getfilesystemencoding())
            rv = GetShortPathName(filename, buf, MAX_PATH)
            if rv != 0 and rv <= MAX_PATH:
                filename = buf.value

            if IS_PY2:
                filename = filename.encode(getfilesystemencoding())
            return filename

        # Note that we have a cache for previous list dirs... the only case where this may be an
        # issue is if the user actually changes the case of an existing file on windows while
        # the debugger is executing (as this seems very unlikely and the cache can save a
        # reasonable time -- especially on mapped drives -- it seems nice to have it).
        _listdir_cache = {}

        def _resolve_listing(resolved, iter_parts, cache=_listdir_cache):
            while True:  # Note: while True to make iterative and not recursive
                try:
                    resolve_lowercase = next(iter_parts)  # must be lowercase already
                except StopIteration:
                    return resolved

                resolved_lower = resolved.lower()

                resolved_joined = cache.get((resolved_lower, resolve_lowercase))
                if resolved_joined is None:
                    dir_contents = cache.get(resolved_lower)
                    if dir_contents is None:
                        dir_contents = cache[resolved_lower] = os.listdir(resolved)

                    for filename in dir_contents:
                        if filename.lower() == resolve_lowercase:
                            resolved_joined = os.path.join(resolved, filename)
                            cache[(resolved_lower, resolve_lowercase)] = resolved_joined
                            break
                    else:
                        raise FileNotFoundError('Unable to find: %s in %s' % (
                            resolve_lowercase, resolved))

                resolved = resolved_joined

        def _get_path_with_real_case(filename):
            # Note: this previously made:
            # convert_to_long_pathname(convert_to_short_pathname(filename))
            # but this is no longer done because we can't rely on getting the shortname
            # consistently (there are settings to disable it on Windows).
            # So, using approach which resolves by listing the dir.

            if IS_PY2 and isinstance(filename, unicode):  # noqa
                filename = filename.encode(getfilesystemencoding())

            if '~' in filename:
                filename = convert_to_long_pathname(filename)

            if filename.startswith('<') or not os_path_exists(filename):
                return filename  # Not much we can do.

            drive, parts = os.path.splitdrive(os.path.normpath(filename))
            drive = drive.upper()
            while parts.startswith(os.path.sep):
                parts = parts[1:]
                drive += os.path.sep
            parts = parts.lower().split(os.path.sep)

            try:
                return _resolve_listing(drive, iter(parts))
            except FileNotFoundError:
                _listdir_cache.clear()
                # Retry once after clearing the cache we have.
                try:
                    return _resolve_listing(drive, iter(parts))
                except FileNotFoundError:
                    if os_path_exists(filename):
                        # This is really strange, ask the user to report as error.
                        pydev_log.critical(
                            'pydev debugger: critical: unable to get real case for file. Details:\n'
                            'filename: %s\ndrive: %s\nparts: %s\n'
                            '(please create a ticket in the tracker to address this).',
                            filename, drive, parts
                        )
                        pydev_log.exception()
                    # Don't fail, just return the original file passed.
                    return filename

        # Check that it actually works
        _get_path_with_real_case(__file__)
    except:
        # Something didn't quite work out, leave no-op conversions in place.
        if DebugInfoHolder.DEBUG_TRACE_LEVEL > 2:
            pydev_log.exception()
    else:
        convert_to_long_pathname = _convert_to_long_pathname
        convert_to_short_pathname = _convert_to_short_pathname
        get_path_with_real_case = _get_path_with_real_case

elif IS_JYTHON and IS_WINDOWS:

    def get_path_with_real_case(filename):
        from java.io import File  # noqa
        f = File(filename)
        ret = f.getCanonicalPath()
        if IS_PY2 and not isinstance(ret, str):
            return ret.encode(getfilesystemencoding())
        return ret

if IS_JYTHON:

    def _normcase_windows(filename):
        return filename.lower()

else:

    def _normcase_windows(filename):
        # `normcase` doesn't lower case on Python 2 for non-English locale, so we should do it manually.
        if '~' in filename:
            filename = convert_to_long_pathname(filename)

        filename = _nt_os_normcase(filename)
        return filename.lower()


def _normcase_linux(filename):
    return filename  # no-op


if IS_WINDOWS:
    normcase = _normcase_windows

else:
    normcase = _normcase_linux

_ide_os = 'WINDOWS' if IS_WINDOWS else 'UNIX'

_normcase_from_client = normcase

DEBUG_CLIENT_SERVER_TRANSLATION = os.environ.get('DEBUG_PYDEVD_PATHS_TRANSLATION', 'False').lower() in ('1', 'true')


def set_ide_os(os):
    '''
    We need to set the IDE os because the host where the code is running may be
    actually different from the client (and the point is that we want the proper
    paths to translate from the client to the server).

    :param os:
        'UNIX' or 'WINDOWS'
    '''
    global _ide_os
    global _normcase_from_client
    prev = _ide_os
    if os == 'WIN':  # Apparently PyCharm uses 'WIN' (https://github.com/fabioz/PyDev.Debugger/issues/116)
        os = 'WINDOWS'

    assert os in ('WINDOWS', 'UNIX')

    if DEBUG_CLIENT_SERVER_TRANSLATION:
        print('pydev debugger: client OS: %s' % (os,))

    _normcase_from_client = normcase
    if os == 'WINDOWS':

        # Client in Windows and server in Unix, we need to normalize the case.
        if not IS_WINDOWS:
            _normcase_from_client = _normcase_windows

    else:
        # Client in Unix and server in Windows, we can't normalize the case.
        if IS_WINDOWS:
            _normcase_from_client = _normcase_linux

    if prev != os:
        _ide_os = os
        # We need to (re)setup how the client <-> server translation works to provide proper separators.
        setup_client_server_paths(_last_client_server_paths_set)


# Caches filled as requested during the debug session.
NORM_PATHS_CONTAINER = {}
NORM_PATHS_AND_BASE_CONTAINER = {}


def _NormFile(filename):
    _abs_path, real_path = _NormPaths(filename)
    return real_path


def _AbsFile(filename):
    abs_path, _real_path = _NormPaths(filename)
    return abs_path


# Returns tuple of absolute path and real path for given filename
def _NormPaths(filename, NORM_PATHS_CONTAINER=NORM_PATHS_CONTAINER):
    try:
        return NORM_PATHS_CONTAINER[filename]
    except:
        if filename.__class__ != str:
            raise AssertionError('Paths passed to _NormPaths must be str. Found: %s (%s)' % (filename, type(filename)))
        if os is None:  # Interpreter shutdown
            return filename, filename

        os_path = os.path
        if os_path is None:  # Interpreter shutdown
            return filename, filename

        os_path_abspath = os_path.abspath
        os_path_isabs = os_path.isabs

        if os_path_abspath is None or os_path_isabs is None or rPath is None:  # Interpreter shutdown
            return filename, filename

        isabs = os_path_isabs(filename)

        abs_path = _NormPath(filename, os_path_abspath, isabs)
        real_path = _NormPath(filename, rPath, isabs)

        # cache it for fast access later
        NORM_PATHS_CONTAINER[filename] = abs_path, real_path
        return abs_path, real_path


def _get_relative_filename_abs_path(filename, normpath, os_path_exists=os_path_exists):
    # If we have a relative path and the file does not exist when made absolute, try to
    # resolve it based on the sys.path entries.
    for p in sys.path:
        r = normpath(os.path.join(p, filename))
        if os_path_exists(r):
            return r

    # We couldn't find the real file for the relative path. Resolve it as if it was in
    # a library (so that it's considered a library file and not a project file).
    r = normpath(os.path.join(_library_dir, filename))
    return r


def _NormPath(filename, normpath, isabs, os_path_exists=os_path_exists, join=join):
    if filename.startswith('<'):
        # Not really a file, rather a synthetic name like <string> or <ipython-...>;
        # shouldn't be normalized.
        return filename

    r = normpath(filename)

    if not isabs:
        if not os_path_exists(r):
            r = _get_relative_filename_abs_path(filename, normpath)

    ind = r.find('.zip')
    if ind == -1:
        ind = r.find('.egg')
    if ind != -1:
        ind += 4
        zip_path = r[:ind]
        inner_path = r[ind:]
        if inner_path.startswith('!'):
            # Note (fabioz): although I can replicate this by creating a file ending as
            # .zip! or .egg!, I don't really know what's the real-world case for this
            # (still kept as it was added by @jetbrains, but it should probably be reviewed
            # later on).
            # Note 2: it goes hand-in-hand with 'exists'.
            inner_path = inner_path[1:]
            zip_path = zip_path + '!'

        if inner_path.startswith('/') or inner_path.startswith('\\'):
            inner_path = inner_path[1:]
        if inner_path:
            r = join(normcase(zip_path), inner_path)
            return r

    r = normcase(r)
    return r


_ZIP_SEARCH_CACHE = {}
_NOT_FOUND_SENTINEL = object()


def exists(file):
    if os_path_exists(file):
        return True

    if not os.path.isabs(file):
        file = _get_relative_filename_abs_path(file, os.path.abspath)
        if os_path_exists(file):
            return True

    ind = file.find('.zip')
    if ind == -1:
        ind = file.find('.egg')

    if ind != -1:
        ind += 4
        zip_path = file[:ind]
        inner_path = file[ind:]
        if inner_path.startswith("!"):
            # Note (fabioz): although I can replicate this by creating a file ending as
            # .zip! or .egg!, I don't really know what's the real-world case for this
            # (still kept as it was added by @jetbrains, but it should probably be reviewed
            # later on).
            # Note 2: it goes hand-in-hand with '_NormPath'.
            inner_path = inner_path[1:]
            zip_path = zip_path + '!'

        zip_file_obj = _ZIP_SEARCH_CACHE.get(zip_path, _NOT_FOUND_SENTINEL)
        if zip_file_obj is None:
            return False
        elif zip_file_obj is _NOT_FOUND_SENTINEL:
            try:
                import zipfile
                zip_file_obj = zipfile.ZipFile(zip_path, 'r')
                _ZIP_SEARCH_CACHE[zip_path] = zip_file_obj
            except:
                _ZIP_SEARCH_CACHE[zip_path] = _NOT_FOUND_SENTINEL
                return False

        try:
            if inner_path.startswith('/') or inner_path.startswith('\\'):
                inner_path = inner_path[1:]

            _info = zip_file_obj.getinfo(inner_path.replace('\\', '/'))

            return join(zip_path, inner_path)
        except KeyError:
            return False
    return False


try:
    try:
        code = rPath.func_code
    except AttributeError:
        code = rPath.__code__
    if not os.path.isabs(code.co_filename):
        pydev_log.critical('This version of python seems to be incorrectly compiled')
        pydev_log.critical('(internal generated filenames are not absolute).')
        pydev_log.critical('This may make the debugger miss breakpoints.')
        pydev_log.critical('Related bug: http://bugs.python.org/issue1666807')
    elif not exists(code.co_filename):  # Note: checks for files inside .zip containers.
        pydev_log.critical('It seems the debugger cannot resolve %s', code.co_filename)
        pydev_log.critical('This may make the debugger miss breakpoints in the standard library.')
        pydev_log.critical('Related bug: https://bugs.python.org/issue1180193')
except:
    # Don't fail if there's something not correct here -- but at least print it to the user so that we can correct that
    pydev_log.exception()

# Note: as these functions may be rebound, users should always import
# pydevd_file_utils and then use:
#
# pydevd_file_utils.norm_file_to_client
# pydevd_file_utils.norm_file_to_server
#
# instead of importing any of those names to a given scope.


def _path_to_expected_str(filename):
    if IS_PY2:
        if not filesystem_encoding_is_utf8 and hasattr(filename, "decode"):
            # filename_in_utf8 is a byte string encoded using the file system encoding
            # convert it to utf8
            filename = filename.decode(file_system_encoding)

        if not isinstance(filename, bytes):
            filename = filename.encode('utf-8')

    else:  # py3
        if isinstance(filename, bytes):
            filename = filename.decode(file_system_encoding)

    return filename


def _original_file_to_client(filename, cache={}):
    try:
        return cache[filename]
    except KeyError:
        translated = _path_to_expected_str(get_path_with_real_case(_AbsFile(filename)))
        cache[filename] = translated
    return cache[filename]


_original_file_to_server = _NormFile

norm_file_to_client = _original_file_to_client
norm_file_to_server = _original_file_to_server


def _fix_path(path, sep):
    if path.endswith('/') or path.endswith('\\'):
        path = path[:-1]

    if sep != '/':
        path = path.replace('/', sep)
    return path


_last_client_server_paths_set = []

_source_reference_to_frame_id = {}
_source_reference_to_server_filename = {}
_line_cache_source_reference_to_server_filename = {}
_client_filename_in_utf8_to_source_reference = {}
_next_source_reference = partial(next, itertools.count(1))


def get_client_filename_source_reference(client_filename):
    return _client_filename_in_utf8_to_source_reference.get(client_filename, 0)


def get_server_filename_from_source_reference(source_reference):
    return _source_reference_to_server_filename.get(source_reference, '')


def create_source_reference_for_linecache(server_filename):
    source_reference = _next_source_reference()
    _line_cache_source_reference_to_server_filename[source_reference] = server_filename
    return source_reference


def get_source_reference_filename_from_linecache(source_reference):
    return _line_cache_source_reference_to_server_filename.get(source_reference)


def create_source_reference_for_frame_id(frame_id):
    source_reference = _next_source_reference()
    _source_reference_to_frame_id[source_reference] = frame_id
    return source_reference


def get_frame_id_from_source_reference(source_reference):
    return _source_reference_to_frame_id.get(source_reference)


def setup_client_server_paths(paths):
    '''paths is the same format as PATHS_FROM_ECLIPSE_TO_PYTHON'''

    global norm_file_to_client
    global norm_file_to_server
    global _last_client_server_paths_set
    global _next_source_reference

    _last_client_server_paths_set = paths[:]

    _source_reference_to_server_filename.clear()
    _client_filename_in_utf8_to_source_reference.clear()
    _next_source_reference = partial(next, itertools.count(1))

    # Work on the client and server slashes.
    python_sep = '\\' if IS_WINDOWS else '/'
    eclipse_sep = '\\' if _ide_os == 'WINDOWS' else '/'

    norm_filename_to_server_container = {}
    norm_filename_to_client_container = {}
    initial_paths = list(paths)
    paths_from_eclipse_to_python = initial_paths[:]

    # Apply normcase to the existing paths to follow the os preferences.

    for i, (path0, path1) in enumerate(paths_from_eclipse_to_python[:]):
        if IS_PY2:
            if isinstance(path0, unicode):  # noqa
                path0 = path0.encode(sys.getfilesystemencoding())
            if isinstance(path1, unicode):  # noqa
                path1 = path1.encode(sys.getfilesystemencoding())

        path0 = _fix_path(path0, eclipse_sep)
        path1 = _fix_path(path1, python_sep)
        initial_paths[i] = (path0, path1)

        paths_from_eclipse_to_python[i] = (_normcase_from_client(path0), normcase(path1))

    if not paths_from_eclipse_to_python:
        # no translation step needed (just inline the calls)
        norm_file_to_client = _original_file_to_client
        norm_file_to_server = _original_file_to_server
        return

    # only setup translation functions if absolutely needed!
    def _norm_file_to_server(filename, cache=norm_filename_to_server_container):
        # Eclipse will send the passed filename to be translated to the python process
        # So, this would be 'NormFileFromEclipseToPython'
        try:
            return cache[filename]
        except KeyError:
            if eclipse_sep != python_sep:
                # Make sure that the separators are what we expect from the IDE.
                filename = filename.replace(python_sep, eclipse_sep)

            # used to translate a path from the client to the debug server
            translated = filename
            translated_normalized = _normcase_from_client(filename)
            for eclipse_prefix, server_prefix in paths_from_eclipse_to_python:
                if translated_normalized.startswith(eclipse_prefix):
                    found_translation = True
                    if DEBUG_CLIENT_SERVER_TRANSLATION:
                        pydev_log.critical('pydev debugger: replacing to server: %s', filename)
                    translated = server_prefix + filename[len(eclipse_prefix):]
                    if DEBUG_CLIENT_SERVER_TRANSLATION:
                        pydev_log.critical('pydev debugger: sent to server: %s', translated)
                    break
            else:
                found_translation = False

            # Note that when going to the server, we do the replace first and only later do the norm file.
            if eclipse_sep != python_sep:
                translated = translated.replace(eclipse_sep, python_sep)

            if found_translation:
                translated = _NormFile(translated)
            else:
                if not os_path_exists(translated):
                    if not translated.startswith('<'):
                        # This is a configuration error, so, write it always so
                        # that the user can fix it.
                        error_once('pydev debugger: unable to find translation for: "%s" in [%s] (please revise your path mappings).\n',
                            filename, ', '.join(['"%s"' % (x[0],) for x in paths_from_eclipse_to_python]))
                else:
                    # It's possible that we had some round trip (say, we sent /usr/lib and received
                    # it back, so, having no translation is ok too).
                    translated = _NormFile(translated)

            cache[filename] = translated
            return translated

    def _norm_file_to_client(filename, cache=norm_filename_to_client_container):
        # The result of this method will be passed to eclipse
        # So, this would be 'NormFileFromPythonToEclipse'
        try:
            return cache[filename]
        except KeyError:
            # used to translate a path from the debug server to the client
            translated = _NormFile(filename)

            # After getting the real path, let's get it with the path with
            # the real case and then obtain a new normalized copy, just in case
            # the path is different now.
            translated_proper_case = get_path_with_real_case(translated)
            translated = _NormFile(translated_proper_case)

            path_mapping_applied = False

            if IS_WINDOWS:
                if translated.lower() != translated_proper_case.lower():
                    translated_proper_case = translated
                    if DEBUG_CLIENT_SERVER_TRANSLATION:
                        pydev_log.critical(
                            'pydev debugger: _NormFile changed path (from: %s to %s)',
                                translated_proper_case, translated)

            for i, (eclipse_prefix, python_prefix) in enumerate(paths_from_eclipse_to_python):
                if translated.startswith(python_prefix):
                    if DEBUG_CLIENT_SERVER_TRANSLATION:
                        pydev_log.critical('pydev debugger: replacing to client: %s', translated)

                    # Note: use the non-normalized version.
                    eclipse_prefix = initial_paths[i][0]
                    translated = eclipse_prefix + translated_proper_case[len(python_prefix):]
                    if DEBUG_CLIENT_SERVER_TRANSLATION:
                        pydev_log.critical('pydev debugger: sent to client: %s', translated)
                    path_mapping_applied = True
                    break
            else:
                if DEBUG_CLIENT_SERVER_TRANSLATION:
                    pydev_log.critical('pydev debugger: to client: unable to find matching prefix for: %s in %s',
                        translated, [x[1] for x in paths_from_eclipse_to_python])
                    translated = translated_proper_case

            if eclipse_sep != python_sep:
                translated = translated.replace(python_sep, eclipse_sep)

            translated = _path_to_expected_str(translated)

            # The resulting path is not in the python process, so, we cannot do a _NormFile here,
            # only at the beginning of this method.
            cache[filename] = translated

            if translated not in _client_filename_in_utf8_to_source_reference:
                if path_mapping_applied:
                    source_reference = 0
                else:
                    source_reference = _next_source_reference()
                _client_filename_in_utf8_to_source_reference[translated] = source_reference
                _source_reference_to_server_filename[source_reference] = filename

            return translated

    norm_file_to_server = _norm_file_to_server
    norm_file_to_client = _norm_file_to_client


setup_client_server_paths(PATHS_FROM_ECLIPSE_TO_PYTHON)


# For given file f returns tuple of its absolute path, real path and base name
def get_abs_path_real_path_and_base_from_file(
        filename, NORM_PATHS_AND_BASE_CONTAINER=NORM_PATHS_AND_BASE_CONTAINER):
    try:
        return NORM_PATHS_AND_BASE_CONTAINER[filename]
    except:
        f = filename
        if not f:
            # i.e.: it's possible that the user compiled code with an empty string (consider
            # it as <string> in this case).
            f = '<string>'
        if _NormPaths is None:  # Interpreter shutdown
            i = max(f.rfind('/'), f.rfind('\\'))
            return (f, f, f[i + 1:])

        if f is not None:
            if f.endswith('.pyc'):
                f = f[:-1]
            elif f.endswith('$py.class'):
                f = f[:-len('$py.class')] + '.py'

        abs_path, real_path = _NormPaths(f)

        try:
            base = basename(real_path)
        except AttributeError:
            # Error during shutdown.
            i = max(f.rfind('/'), f.rfind('\\'))
            base = f[i + 1:]
        ret = abs_path, real_path, base
        NORM_PATHS_AND_BASE_CONTAINER[filename] = ret
        return ret


def get_abs_path_real_path_and_base_from_frame(frame):
    try:
        return NORM_PATHS_AND_BASE_CONTAINER[frame.f_code.co_filename]
    except:
        # This one is just internal (so, does not need any kind of client-server translation)
        f = frame.f_code.co_filename
        if f is not None and f.startswith (('build/bdist.', 'build\\bdist.')):
            # files from eggs in Python 2.7 have paths like build/bdist.linux-x86_64/egg/<path-inside-egg>
            f = frame.f_globals['__file__']

        if get_abs_path_real_path_and_base_from_file is None:
            # Interpreter shutdown
            if not f:
                # i.e.: it's possible that the user compiled code with an empty string (consider
                # it as <string> in this case).
                f = '<string>'
            i = max(f.rfind('/'), f.rfind('\\'))
            return f, f, f[i + 1:]

        ret = get_abs_path_real_path_and_base_from_file(f)
        # Also cache based on the frame.f_code.co_filename (if we had it inside build/bdist it can make a difference).
        NORM_PATHS_AND_BASE_CONTAINER[frame.f_code.co_filename] = ret
        return ret


def get_fullname(mod_name):
    if IS_PY3K:
        import pkgutil
    else:
        from _pydev_imps import _pydev_pkgutil_old as pkgutil
    try:
        loader = pkgutil.get_loader(mod_name)
    except:
        return None
    if loader is not None:
        for attr in ("get_filename", "_get_filename"):
            meth = getattr(loader, attr, None)
            if meth is not None:
                return meth(mod_name)
    return None


def get_package_dir(mod_name):
    for path in sys.path:
        mod_path = join(path, mod_name.replace('.', '/'))
        if os.path.isdir(mod_path):
            return mod_path
    return None
