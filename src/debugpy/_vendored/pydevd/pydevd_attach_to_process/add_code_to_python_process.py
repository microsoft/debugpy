r"""
Copyright: Brainwy Software Ltda.

License: EPL.
=============

Works for Windows by using an executable that'll inject a dll to a process and call a function.

Windows target architecture is queried with IsWow64Process2, with a winappdbg fallback on older x86/x64 Windows.

Works for Linux relying on gdb.

Limitations:
============

    Linux:
    ------

        1. It possible that ptrace is disabled: /etc/sysctl.d/10-ptrace.conf

        Note that even enabling it in /etc/sysctl.d/10-ptrace.conf (i.e.: making the
        ptrace_scope=0), it's possible that we need to run the application that'll use ptrace (or
        gdb in this case) as root (so, we must sudo the python which'll run this module).

        2. It currently doesn't work in debug builds (i.e.: python_d)


Other implementations:
- pyrasite.com:
    GPL
    Windows/linux (in Linux it also uses gdb to connect -- although specifics are different as we use a dll to execute
    code with other threads stopped). It's Windows approach is more limited because it doesn't seem to deal properly with
    Python 3 if threading is disabled.

- https://github.com/google/pyringe:
    Apache v2.
    Only linux/Python 2.

- http://pytools.codeplex.com:
    Apache V2
    Windows Only (but supports mixed mode debugging)
    Our own code relies heavily on a part of it: http://pytools.codeplex.com/SourceControl/latest#Python/Product/PyDebugAttach/PyDebugAttach.cpp
    to overcome some limitations of attaching and running code in the target python executable on Python 3.
    See: attach.cpp

Linux: References if we wanted to use a pure-python debugger:
    https://bitbucket.org/haypo/python-ptrace/
    http://stackoverflow.com/questions/7841573/how-to-get-an-error-message-for-errno-value-in-python
    Jugaad:
        https://www.defcon.org/images/defcon-19/dc-19-presentations/Jakhar/DEFCON-19-Jakhar-Jugaad-Linux-Thread-Injection.pdf
        https://github.com/aseemjakhar/jugaad

Something else (general and not Python related):
- http://www.codeproject.com/Articles/4610/Three-Ways-to-Inject-Your-Code-into-Another-Proces

Other references:
- https://github.com/haypo/faulthandler
- http://nedbatchelder.com/text/trace-function.html
- https://github.com/python-git/python/blob/master/Python/sysmodule.c (sys_settrace)
- https://github.com/python-git/python/blob/master/Python/ceval.c (PyEval_SetTrace)
- https://github.com/python-git/python/blob/master/Python/thread.c (PyThread_get_key_value)


To build the dlls needed on windows, visual studio express 13 was used (see compile_dll.bat)

See: attach_pydevd.py to attach the pydev debugger to a running python process.
"""

# Note: to work with nasm compiling asm to code and decompiling to see asm with shellcode:
# x:\nasm\nasm-2.07-win32\nasm-2.07\nasm.exe
# nasm.asm&x:\nasm\nasm-2.07-win32\nasm-2.07\ndisasm.exe -b arch nasm
import ctypes
from ctypes import wintypes
import os
import shutil
import struct
import subprocess
import sys
import time
from contextlib import contextmanager
import platform
import traceback

try:
    TimeoutError = TimeoutError  # @ReservedAssignment
except NameError:

    class TimeoutError(RuntimeError):  # @ReservedAssignment
        pass


def _get_windows_kernel32():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
    kernel32.ReleaseMutex.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateEventW.restype = wintypes.HANDLE
    kernel32.CreateFileMappingW.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.LPCWSTR
    ]
    kernel32.CreateFileMappingW.restype = wintypes.HANDLE
    kernel32.MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
    kernel32.MapViewOfFile.restype = ctypes.c_void_p
    kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
    kernel32.UnmapViewOfFile.restype = wintypes.BOOL
    return kernel32


@contextmanager
def _create_win_event(name):
    kernel32 = _get_windows_kernel32()

    manual_reset = False  # i.e.: after someone waits it, automatically set to False.
    initial_state = False
    if isinstance(name, bytes):
        name = name.decode("utf-8")
    event = kernel32.CreateEventW(None, manual_reset, initial_state, name)
    if not event:
        raise ctypes.WinError(ctypes.get_last_error())

    class _WinEvent(object):
        def wait_for_event_set(self, timeout=None):
            """
            :param timeout: in seconds
            """
            if timeout is None:
                timeout = 0xFFFFFFFF
            else:
                timeout = int(timeout * 1000)
            ret = kernel32.WaitForSingleObject(event, timeout)
            if ret in (0, 0x80):
                return True
            elif ret == 0x102:
                # Timed out
                return False
            else:
                raise ctypes.WinError(ctypes.get_last_error())

    try:
        yield _WinEvent()
    finally:
        if not kernel32.CloseHandle(event):
            raise ctypes.WinError(ctypes.get_last_error())


IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform in ("linux", "linux2")
IS_MAC = sys.platform == "darwin"


def is_python_64bit():
    return struct.calcsize("P") == 8


def get_windows_process_architecture(pid):
    kernel32 = _get_windows_kernel32()
    try:
        is_wow64_process2 = kernel32.IsWow64Process2
    except AttributeError:
        # Windows versions predating IsWow64Process2 only support our x86/x64 targets.
        from winappdbg import win32
        from winappdbg.process import Process

        if win32.arch not in (win32.ARCH_I386, win32.ARCH_AMD64):
            raise RuntimeError("IsWow64Process2 is required to identify a Windows ARM64 target.")
        return "amd64" if Process(pid).get_bits() == 64 else "x86"

    is_wow64_process2.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.WORD), ctypes.POINTER(wintypes.WORD)]
    is_wow64_process2.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        process_machine = wintypes.WORD()
        native_machine = wintypes.WORD()
        if not is_wow64_process2(handle, ctypes.byref(process_machine), ctypes.byref(native_machine)):
            raise ctypes.WinError(ctypes.get_last_error())
        machine = process_machine.value or native_machine.value
        arch = {0x014C: "x86", 0x8664: "amd64", 0xAA64: "arm64"}.get(machine)
        if arch is None:
            raise RuntimeError("Unsupported Windows target machine: 0x%04x." % (machine,))
        return arch
    finally:
        if not kernel32.CloseHandle(handle):
            raise ctypes.WinError(ctypes.get_last_error())


def get_target_filename(is_target_process_64=None, prefix=None, extension=None, target_arch=None):
    # Note: we have an independent (and similar -- but not equal) version of this method in
    # `pydevd_tracing.py` which should be kept synchronized with this one (we do a copy
    # because the `pydevd_attach_to_process` is mostly independent and shouldn't be imported in the
    # debugger -- the only situation where it's imported is if the user actually does an attach to
    # process, through `attach_pydevd.py`, but this should usually be called from the IDE directly
    # and not from the debugger).
    libdir = os.path.dirname(os.path.abspath(__file__))

    if IS_WINDOWS:
        if target_arch is None:
            if is_target_process_64 is None:
                raise AssertionError("On Windows the target architecture must be specified.")
            # Retain the legacy bitness argument for x86/x64 callers.
            target_arch = "amd64" if is_target_process_64 else "x86"
        if target_arch not in ("x86", "amd64", "arm64"):
            raise RuntimeError("Unsupported Windows target architecture: %s." % (target_arch,))
        filename = os.path.join(libdir, "%s%s%s" % (prefix or "attach_", target_arch, extension or ".dll"))
        if not os.path.exists(filename):
            print("Expected: %s to exist." % (filename,))
            return None
        return filename

    if is_target_process_64 is None:
        # For other platforms, just use the the same bitness of the process we're running in.
        is_target_process_64 = is_python_64bit()

    arch = platform.machine()
    if not arch:
        print("platform.machine() did not return valid value.")  # This shouldn't happen...
        return None

    if IS_LINUX:
        if not extension:
            extension = ".so"
        suffix_64 = "amd64"
        suffix_32 = "x86"

    elif IS_MAC:
        if not extension:
            extension = ".dylib"
        suffix_64 = "x86_64"
        suffix_32 = "x86"

    else:
        print("Unable to attach to process in platform: %s", sys.platform)
        return None

    if arch.lower() not in ("arm64", "amd64", "x86", "x86_64", "i386", "x86"):
        # We don't support this processor by default. Still, let's support the case where the
        # user manually compiled it himself with some heuristics.
        #
        # Ideally the user would provide a library in the format: "attach_<arch>.<extension>"
        # based on the way it's currently compiled -- see:
        # - windows/compile_windows.bat
        # - linux_and_mac/compile_linux.sh
        # - linux_and_mac/compile_mac.sh

        try:
            found = [name for name in os.listdir(libdir) if name.startswith("attach_") and name.endswith(extension)]
        except:
            print("Error listing dir: %s" % (libdir,))
            traceback.print_exc()
            return None

        if prefix:
            expected_name = prefix + arch + extension
            expected_name_linux = prefix + "linux_" + arch + extension
        else:
            # Default is looking for the attach_ / attach_linux
            expected_name = "attach_" + arch + extension
            expected_name_linux = "attach_linux_" + arch + extension

        filename = None
        if expected_name in found:  # Heuristic: user compiled with "attach_<arch>.<extension>"
            filename = os.path.join(libdir, expected_name)

        elif IS_LINUX and expected_name_linux in found:  # Heuristic: user compiled with "attach_linux_<arch>.<extension>"
            filename = os.path.join(libdir, expected_name_linux)

        elif len(found) == 1:  # Heuristic: user removed all libraries and just left his own lib.
            filename = os.path.join(libdir, found[0])

        else:  # Heuristic: there's one additional library which doesn't seem to be our own. Find the odd one.
            filtered = [name for name in found if not name.endswith((suffix_64 + extension, suffix_32 + extension))]
            if len(filtered) == 1:  # If more than one is available we can't be sure...
                filename = os.path.join(libdir, found[0])

        if filename is None:
            print("Unable to attach to process in arch: %s (did not find %s in %s)." % (arch, expected_name, libdir))
            return None

        print("Using %s in arch: %s." % (filename, arch))

    else:
        if is_target_process_64:
            suffix = suffix_64
        else:
            suffix = suffix_32

        if not prefix:
            # Default is looking for the attach_ / attach_linux
            if IS_MAC:
                prefix = "attach"
                suffix = ""
            elif IS_LINUX:
                prefix = "attach_linux_"  # historically it has a different name
            else:
                print("Unable to attach to process in platform: %s" % (sys.platform,))
                return None

        filename = os.path.join(libdir, "%s%s%s" % (prefix, suffix, extension))

    if not os.path.exists(filename):
        print("Expected: %s to exist." % (filename,))
        return None

    return filename


def run_python_code_windows(pid, python_code, connect_debugger_tracing=False, show_debug_info=0):
    assert "'" not in python_code, "Having a single quote messes with our command."

    if not isinstance(python_code, bytes):
        python_code = python_code.encode("utf-8")

    target_arch = get_windows_process_architecture(pid)

    with _acquire_mutex("_pydevd_pid_attach_mutex_%s" % (pid,), 10):
        print("--- Connecting to %s target (current process is: %s bits) ---" % (target_arch, 64 if is_python_64bit() else 32))
        sys.stdout.flush()

        with _win_write_to_shared_named_memory(python_code, pid):
            target_executable = get_target_filename(prefix="inject_dll_", extension=".exe", target_arch=target_arch)
            if not target_executable:
                raise RuntimeError("Could not find expected .exe file to inject dll in attach to process.")

            target_dll = get_target_filename(target_arch=target_arch)
            if not target_dll:
                raise RuntimeError("Could not find expected .dll file in attach to process.")

            print("\n--- Injecting attach dll: %s into pid: %s ---" % (os.path.basename(target_dll), pid))
            sys.stdout.flush()
            args = [target_executable, str(pid), target_dll]
            subprocess.check_call(args)

            # Now, if the first injection worked, go on to the second which will actually
            # run the code.
            target_dll_run_on_dllmain = get_target_filename(prefix="run_code_on_dllmain_", target_arch=target_arch)
            if not target_dll_run_on_dllmain:
                raise RuntimeError("Could not find expected .dll in attach to process.")

            with _create_win_event("_pydevd_pid_event_%s" % (pid,)) as event:
                print("\n--- Injecting run code dll: %s into pid: %s ---" % (os.path.basename(target_dll_run_on_dllmain), pid))
                sys.stdout.flush()
                args = [target_executable, str(pid), target_dll_run_on_dllmain]
                subprocess.check_call(args)

                if not event.wait_for_event_set(15):
                    raise TimeoutError("Timed out waiting for code injection into pid: %s." % (pid,))
            print("--- Finished dll injection ---\n")
            sys.stdout.flush()

    return 0


@contextmanager
def _acquire_mutex(mutex_name, timeout):
    """
    Only one process may be attaching to a pid, so, create a system mutex
    to make sure this holds in practice.
    """
    kernel32 = _get_windows_kernel32()
    mutex = kernel32.CreateMutexW(None, False, mutex_name)
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())

    try:
        result = kernel32.WaitForSingleObject(mutex, int(timeout * 1000))
        if result == 0x102:  # WAIT_TIMEOUT
            raise TimeoutError("Unable to acquire mutex to make attach before timeout.")
        if result not in (0, 0x80):  # WAIT_OBJECT_0, WAIT_ABANDONED
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            yield
        finally:
            if not kernel32.ReleaseMutex(mutex):
                raise ctypes.WinError(ctypes.get_last_error())
    finally:
        if not kernel32.CloseHandle(mutex):
            raise ctypes.WinError(ctypes.get_last_error())


@contextmanager
def _win_write_to_shared_named_memory(python_code, pid):
    # Note: BUFSIZE must be the same from run_code_in_memory.hpp
    BUFSIZE = 2048
    assert isinstance(python_code, bytes)
    assert len(python_code) > 0, "Python code must not be empty."
    # Note: -1 so that we're sure we'll add a \0 to the end.
    assert len(python_code) < BUFSIZE - 1, "Python code must have at most %s bytes (found: %s)" % (BUFSIZE - 1, len(python_code))

    python_code += b"\0" * (BUFSIZE - len(python_code))
    assert python_code.endswith(b"\0")

    INVALID_HANDLE_VALUE = -1
    PAGE_READWRITE = 0x4
    FILE_MAP_WRITE = 0x2
    kernel32 = _get_windows_kernel32()
    filemap = kernel32.CreateFileMappingW(
        INVALID_HANDLE_VALUE, None, PAGE_READWRITE, 0, BUFSIZE, "__pydevd_pid_code_to_run__%s" % (pid,)
    )

    if not filemap:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        view = kernel32.MapViewOfFile(filemap, FILE_MAP_WRITE, 0, 0, 0)
        if not view:
            raise ctypes.WinError(ctypes.get_last_error())

        try:
            ctypes.memmove(view, python_code, BUFSIZE)
            yield
        finally:
            if not kernel32.UnmapViewOfFile(view):
                raise ctypes.WinError(ctypes.get_last_error())
    finally:
        if not kernel32.CloseHandle(filemap):
            raise ctypes.WinError(ctypes.get_last_error())


def run_python_code_linux_gdb(pid, python_code, connect_debugger_tracing=False, show_debug_info=0):
    assert "'" not in python_code, "Having a single quote messes with our command."

    target_dll = get_target_filename()
    if not target_dll:
        libdir = os.path.dirname(os.path.abspath(__file__))
        found = [name for name in os.listdir(libdir)]
        raise RuntimeError(
            "Could not find .so for attach to process.\nlibdir: %s\nAvailable in dir: %s"
            % (
                libdir,
                found,
            )
        )
    target_dll_name = os.path.splitext(os.path.basename(target_dll))[0]

    # Note: we currently don't support debug builds
    is_debug = 0
    # Note that the space in the beginning of each line in the multi-line is important!
    cmd = [
        "gdb",
        "--nw",  # no gui interface
        "--nh",  # no ~/.gdbinit
        "--nx",  # no .gdbinit
        #         '--quiet',  # no version number on startup
        "--pid",
        str(pid),
        "--batch",
        #         '--batch-silent',
    ]

    # PYDEVD_GDB_SCAN_SHARED_LIBRARIES can be a list of strings with the shared libraries
    # which should be scanned by default to make the attach to process (i.e.: libdl, libltdl, libc, libfreebl3).
    #
    # The default is scanning all shared libraries, but on some cases this can be in the 20-30
    # seconds range for some corner cases.
    # See: https://github.com/JetBrains/intellij-community/pull/1608
    #
    # By setting PYDEVD_GDB_SCAN_SHARED_LIBRARIES (to a comma-separated string), it's possible to
    # specify just a few libraries to be loaded (not many are needed for the attach,
    # but it can be tricky to pre-specify for all Linux versions as this may change
    # across different versions).
    #
    # See: https://github.com/microsoft/debugpy/issues/762#issuecomment-947103844
    # for a comment that explains the basic steps on how to discover what should be available
    # in each case (mostly trying different versions based on the output of gdb).
    #
    # The upside is that for cases when too many libraries are loaded the attach could be slower
    # and just specifying the one that is actually needed for the attach can make it much faster.
    #
    # The downside is that it may be dependent on the Linux version being attached to (which is the
    # reason why this is no longer done by default -- see: https://github.com/microsoft/debugpy/issues/882).
    gdb_load_shared_libraries = os.environ.get("PYDEVD_GDB_SCAN_SHARED_LIBRARIES", "").strip()
    if gdb_load_shared_libraries:
        print("PYDEVD_GDB_SCAN_SHARED_LIBRARIES set: %s." % (gdb_load_shared_libraries,))
        cmd.extend(["--init-eval-command='set auto-solib-add off'"])  # Don't scan all libraries.

        for lib in gdb_load_shared_libraries.split(","):
            lib = lib.strip()
            cmd.extend(["--eval-command='sharedlibrary %s'" % (lib,)])  # Scan the specified library
    else:
        print("PYDEVD_GDB_SCAN_SHARED_LIBRARIES not set (scanning all libraries for needed symbols).")

    cmd.extend(["--eval-command='set scheduler-locking off'"])  # If on we'll deadlock.

    # Leave auto by default (it should do the right thing as we're attaching to a process in the
    # current host).
    cmd.extend(["--eval-command='set architecture auto'"])

    cmd.extend(
        [
            "--eval-command='call (void*)dlopen(\"%s\", 2)'" % target_dll,
            "--eval-command='call (char*)dlerror()'",
            "--eval-command='sharedlibrary %s'" % target_dll_name,
            "--eval-command='call (int)DoAttach(%s, \"%s\", %s)'" % (is_debug, python_code, show_debug_info),
        ]
    )

    # print ' '.join(cmd)

    env = os.environ.copy()
    # Remove the PYTHONPATH (if gdb has a builtin Python it could fail if we
    # have the PYTHONPATH for a different python version or some forced encoding).
    env.pop("PYTHONIOENCODING", None)
    env.pop("PYTHONPATH", None)
    print("Running: %s" % (" ".join(cmd)))
    subprocess.check_call(" ".join(cmd), shell=True, env=env)


def find_helper_script(filedir, script_name):
    target_filename = os.path.join(filedir, "linux_and_mac", script_name)
    target_filename = os.path.normpath(target_filename)
    if not os.path.exists(target_filename):
        raise RuntimeError("Could not find helper script: %s" % target_filename)

    return target_filename


def _run_python_code_lldb(pid, python_code, missing_target_dll_error, show_debug_info=0):
    # Injects python_code into pid using lldb.

    assert "'" not in python_code, "Having a single quote messes with our command."

    target_dll = get_target_filename()
    if not target_dll:
        raise RuntimeError(missing_target_dll_error)

    libdir = os.path.dirname(__file__)
    lldb_prepare_file = find_helper_script(libdir, "lldb_prepare.py")
    # Note: we currently don't support debug builds

    is_debug = 0
    # Note that the space in the beginning of each line in the multi-line is important!
    cmd = [
        "lldb",
        "--no-lldbinit",  # Do not automatically parse any '.lldbinit' files.
        # '--attach-pid',
        # str(pid),
        # '--arch',
        # arch,
        "--script-language",
        "Python",
        #         '--batch-silent',
    ]

    cmd.extend(
        [
            "-o 'process attach --pid %d'" % pid,
            "-o 'command script import \"%s\"'" % (lldb_prepare_file,),
            '-o \'load_lib_and_attach "%s" %s "%s" %s\'' % (target_dll, is_debug, python_code, show_debug_info),
        ]
    )

    cmd.extend(
        [
            "-o 'process detach'",
            "-o 'script import os; os._exit(0)'",
        ]
    )

    # print ' '.join(cmd)

    env = os.environ.copy()
    # Remove the PYTHONPATH (if lldb has a builtin Python it could fail if we
    # have the PYTHONPATH for a different python version or some forced encoding).
    env.pop("PYTHONIOENCODING", None)
    env.pop("PYTHONPATH", None)
    print("Running: %s" % (" ".join(cmd)))
    subprocess.check_call(" ".join(cmd), shell=True, env=env)


def run_python_code_mac(pid, python_code, connect_debugger_tracing=False, show_debug_info=0):
    _run_python_code_lldb(pid, python_code, "Could not find .dylib for attach to process.", show_debug_info)


def run_python_code_linux_lldb(pid, python_code, connect_debugger_tracing=False, show_debug_info=0):
    _run_python_code_lldb(pid, python_code, "Could not find .so for attach to process.", show_debug_info)


def run_python_code_linux(pid, python_code, connect_debugger_tracing=False, show_debug_info=0):
    # On Linux gdb is used by default. lldb can be preferred via the
    # PYDEVD_ATTACH_PREFER_LLDB environment variable (set from the "linuxAttachPreferLldb"
    # launch configuration option). The variable is read here, at call time, so the
    # choice doesn't depend on import ordering. When lldb is preferred but not available
    # on the PATH, we transparently fall back to gdb.
    prefer_lldb = os.environ.get("PYDEVD_ATTACH_PREFER_LLDB", "").strip().lower() in ("1", "true", "yes")
    if prefer_lldb:
        if shutil.which("lldb") is not None:
            return run_python_code_linux_lldb(pid, python_code, connect_debugger_tracing, show_debug_info)
        print("PYDEVD_ATTACH_PREFER_LLDB is set but 'lldb' was not found on the PATH; falling back to gdb.")
    return run_python_code_linux_gdb(pid, python_code, connect_debugger_tracing, show_debug_info)


if IS_WINDOWS:
    run_python_code = run_python_code_windows
elif IS_MAC:
    run_python_code = run_python_code_mac
elif IS_LINUX:
    run_python_code = run_python_code_linux
else:

    def run_python_code(*args, **kwargs):
        print("Unable to attach to process in platform: %s", sys.platform)


def test():
    print("Running with: %s" % (sys.executable,))
    code = """
import os, time, sys
print(os.getpid())
#from threading import Thread
#Thread(target=str).start()
if __name__ == '__main__':
    while True:
        time.sleep(.5)
        sys.stdout.write('.\\n')
        sys.stdout.flush()
"""

    p = subprocess.Popen([sys.executable, "-u", "-c", code])
    try:
        code = 'print("It worked!")\n'

        # Real code will be something as:
        # code = '''import sys;sys.path.append(r'X:\winappdbg-code\examples'); import imported;'''
        run_python_code(p.pid, python_code=code)
        print("\nRun a 2nd time...\n")
        run_python_code(p.pid, python_code=code)

        time.sleep(3)
    finally:
        p.kill()


def main(args):
    # Otherwise, assume the first parameter is the pid and anything else is code to be executed
    # in the target process.
    pid = int(args[0])
    del args[0]
    python_code = ";".join(args)

    # Note: on Linux the python code may not have a single quote char: '
    run_python_code(pid, python_code)


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("Expected pid and Python code to execute in target process.")
    else:
        if "--test" == args[0]:
            test()
        else:
            main(args)
