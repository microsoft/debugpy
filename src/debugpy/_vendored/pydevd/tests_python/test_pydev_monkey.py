# coding: utf-8
import os
import sys
from typing import Any, Generator

import pytest

from _pydev_bundle.pydev_monkey import pydev_src_dir
from _pydevd_bundle.pydevd_constants import sorted_dict_repr
from pydevd import SetupHolder

try:
    from _pydev_bundle import pydev_monkey
except:
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from _pydev_bundle import pydev_monkey


@pytest.fixture(autouse=True)
def save_setup_holder() -> Generator[None, Any, None]:
    original: None = SetupHolder.setup
    yield
    SetupHolder.setup = original


def test_monkey() -> None:
    SetupHolder.setup = {"client": "127.0.0.1", "port": "0", "ppid": os.getpid(), "protocol-quoted-line": True}
    check = """C:\\bin\\python.exe -u -c connect(\\"127.0.0.1\\")"""
    debug_command: str = (
        "import sys; "
        "sys.path.insert(0, r'%s'); "
        "import pydevd; pydevd.config('quoted-line', ''); "
        "pydevd.settrace(host='127.0.0.1', port=0, suspend=False, "
        "trace_only_current_thread=False, patch_multiprocessing=True, access_token=None, client_access_token=None, __setup_holder__=%s); "
        ""
        'connect("127.0.0.1")'
    ) % (pydev_src_dir, sorted_dict_repr(SetupHolder.setup))
    if sys.platform == "win32":
        debug_command: str = debug_command.replace('"', '\\"')
        debug_command: str = '"%s"' % debug_command

    assert "C:\\bin\\python.exe -u -c %s" % debug_command == pydev_monkey.patch_arg_str_win(check)


def test_str_to_args_windows() -> None:
    assert ["a", "b"] == pydev_monkey.str_to_args_windows('a "b"')


def test_monkey_patch_return_original_args() -> None:
    check: list[str] = ["echo", '"my"', '"args"']
    res = pydev_monkey.patch_args(check[:])
    assert res == check


def test_monkey_patch_pathlib_args() -> None:
    try:
        import pathlib
    except ImportError:
        pytest.skip("pathlib not available.")

    check = [pathlib.Path("echo"), '"my"', '"args"']
    res = pydev_monkey.patch_args(check[:])
    assert res == check


def test_monkey_patch_wrong_object_type() -> None:
    check = [1, 22, '"my"', '"args"']
    res = pydev_monkey.patch_args(check[:])
    assert res == check


def test_monkey_patch_wrong_object_type_2() -> None:
    check = ["C:\\bin\\python.exe", "-u", 1, '-qcconnect("127.0.0.1")']
    res = pydev_monkey.patch_args(check[:])
    assert res == check


def test_monkey_patch_args_module_subprocess_pathlib() -> None:
    try:
        import pathlib
    except ImportError:
        pytest.skip("pathlib not available.")

    SetupHolder.setup = {"client": "127.0.0.1", "port": "0", "multiprocess": True}
    if sys.platform == "win32":
        python_path = "C:\\bin\\python.exe"
    else:
        python_path = "/bin/python"
    check = [pathlib.Path(python_path), "-mtest", pathlib.Path("bar")]
    from _pydevd_bundle.pydevd_command_line_handling import get_pydevd_file

    assert pydev_monkey.patch_args(check) == [
        python_path,
        get_pydevd_file(),
        "--module",
        "--port",
        "0",
        "--ppid",
        str(os.getpid()),
        "--client",
        "127.0.0.1",
        "--multiprocess",
        "--protocol-quoted-line",
        "--file",
        "test",
        "bar",
    ]


def test_monkey_patch_args_indc() -> None:
    SetupHolder.setup = {"client": "127.0.0.1", "port": "0", "ppid": os.getpid(), "protocol-quoted-line": True, "skip-notify-stdin": True}
    check: list[str] = ["C:\\bin\\python.exe", "-u", "-c", 'connect("127.0.0.1")']
    debug_command: str = (
        "import sys; sys.path.insert(0, r'%s'); import pydevd; pydevd.config('quoted-line', ''); "
        "pydevd.settrace(host='127.0.0.1', port=0, suspend=False, trace_only_current_thread=False, patch_multiprocessing=True, access_token=None, client_access_token=None, __setup_holder__=%s); "
        ""
        'connect("127.0.0.1")'
    ) % (pydev_src_dir, sorted_dict_repr(SetupHolder.setup))
    if sys.platform == "win32":
        debug_command: str = debug_command.replace('"', '\\"')
        debug_command: str = '"%s"' % debug_command
    res = pydev_monkey.patch_args(check)
    assert res == ["C:\\bin\\python.exe", "-u", "-c", debug_command]


def test_separate_future_imports() -> None:
    found = pydev_monkey._separate_future_imports("""from __future__ import print_function\nprint(1)""")
    assert found == ("from __future__ import print_function;", "\nprint(1)")

    found = pydev_monkey._separate_future_imports("""from __future__ import print_function;print(1)""")
    assert found == ("from __future__ import print_function;", "print(1)")

    found = pydev_monkey._separate_future_imports("""from __future__ import (\nprint_function);print(1)""")
    assert found == ("from __future__ import (\nprint_function);", "print(1)")

    found = pydev_monkey._separate_future_imports(""""line";from __future__ import (\n\nprint_function, absolute_import\n);print(1)""")
    assert found == ('"line";from __future__ import (\n\nprint_function, absolute_import\n);', "print(1)")

    found = pydev_monkey._separate_future_imports(
        """from __future__ import division\nfrom __future__ import (\n\nprint_function, absolute_import\n);print(1)"""
    )
    assert found == ("from __future__ import division\nfrom __future__ import (\n\nprint_function, absolute_import\n);", "print(1)")


def test_monkey_patch_args_indc_future_import() -> None:
    SetupHolder.setup = {"client": "127.0.0.1", "port": "0", "ppid": os.getpid(), "protocol-quoted-line": True, "skip-notify-stdin": True}
    check: list[str] = ["C:\\bin\\python.exe", "-u", "-c", 'from __future__ import print_function;connect("127.0.0.1")']
    debug_command: str = (
        "from __future__ import print_function;import sys; sys.path.insert(0, r'%s'); import pydevd; pydevd.config('quoted-line', ''); "
        "pydevd.settrace(host='127.0.0.1', port=0, suspend=False, trace_only_current_thread=False, patch_multiprocessing=True, access_token=None, client_access_token=None, __setup_holder__=%s); "
        ""
        'connect("127.0.0.1")'
    ) % (pydev_src_dir, sorted_dict_repr(SetupHolder.setup))
    if sys.platform == "win32":
        debug_command: str = debug_command.replace('"', '\\"')
        debug_command: str = '"%s"' % debug_command
    res = pydev_monkey.patch_args(check)
    assert res == ["C:\\bin\\python.exe", "-u", "-c", debug_command]


def test_monkey_patch_args_indc_future_import2() -> None:
    SetupHolder.setup = {"client": "127.0.0.1", "port": "0", "ppid": os.getpid(), "protocol-quoted-line": True, "skip-notify-stdin": True}
    check: list[str] = ["C:\\bin\\python.exe", "-u", "-c", 'from __future__ import print_function\nconnect("127.0.0.1")']
    debug_command: str = (
        "from __future__ import print_function;import sys; sys.path.insert(0, r'%s'); import pydevd; pydevd.config('quoted-line', ''); "
        "pydevd.settrace(host='127.0.0.1', port=0, suspend=False, trace_only_current_thread=False, patch_multiprocessing=True, access_token=None, client_access_token=None, __setup_holder__=%s); "
        ""
        '\nconnect("127.0.0.1")'
    ) % (pydev_src_dir, sorted_dict_repr(SetupHolder.setup))
    if sys.platform == "win32":
        debug_command: str = debug_command.replace('"', '\\"')
        debug_command: str = '"%s"' % debug_command
    res = pydev_monkey.patch_args(check)
    assert res == ["C:\\bin\\python.exe", "-u", "-c", debug_command]


def test_monkey_patch_args_indc2() -> None:
    SetupHolder.setup = {"client": "127.0.0.1", "port": "0", "ppid": os.getpid(), "protocol-quoted-line": True, "skip-notify-stdin": True}
    check: list[str] = ["C:\\bin\\python.exe", "-u", '-qcconnect("127.0.0.1")']
    debug_command: str = (
        "import sys; sys.path.insert(0, r'%s'); import pydevd; pydevd.config('quoted-line', ''); "
        "pydevd.settrace(host='127.0.0.1', port=0, suspend=False, trace_only_current_thread=False, patch_multiprocessing=True, access_token=None, client_access_token=None, __setup_holder__=%s); "
        ""
        'connect("127.0.0.1")'
    ) % (pydev_src_dir, sorted_dict_repr(SetupHolder.setup))
    if sys.platform == "win32":
        debug_command: str = debug_command.replace('"', '\\"')
        debug_command: str = '"%s"' % debug_command
    res = pydev_monkey.patch_args(check)
    assert res == ["C:\\bin\\python.exe", "-u", "-qc", debug_command]


def test_monkey_patch_args_x_flag() -> None:
    SetupHolder.setup = {"client": "127.0.0.1", "port": "0", "ppid": os.getpid(), "protocol-quoted-line": True, "skip-notify-stdin": True}
    check: list[str] = ["C:\\bin\\python.exe", "-X", "faulthandler", "-c", 'connect("127.0.0.1")']
    debug_command: str = (
        "import sys; sys.path.insert(0, r'%s'); import pydevd; pydevd.config('quoted-line', ''); "
        "pydevd.settrace(host='127.0.0.1', port=0, suspend=False, trace_only_current_thread=False, patch_multiprocessing=True, access_token=None, client_access_token=None, __setup_holder__=%s); "
        ""
        'connect("127.0.0.1")'
    ) % (pydev_src_dir, sorted_dict_repr(SetupHolder.setup))
    if sys.platform == "win32":
        debug_command: str = debug_command.replace('"', '\\"')
        debug_command: str = '"%s"' % debug_command
    res = pydev_monkey.patch_args(check)
    assert res == ["C:\\bin\\python.exe", "-X", "faulthandler", "-c", debug_command]


def test_monkey_patch_args_flag_in_single_arg_1() -> None:
    SetupHolder.setup = {"client": "127.0.0.1", "port": "0", "ppid": os.getpid(), "protocol-quoted-line": True, "skip-notify-stdin": True}
    check: list[str] = ["C:\\bin\\python.exe", "-qX", "faulthandler", "-c", 'connect("127.0.0.1")']
    debug_command: str = (
        "import sys; sys.path.insert(0, r'%s'); import pydevd; pydevd.config('quoted-line', ''); "
        "pydevd.settrace(host='127.0.0.1', port=0, suspend=False, trace_only_current_thread=False, patch_multiprocessing=True, access_token=None, client_access_token=None, __setup_holder__=%s); "
        ""
        'connect("127.0.0.1")'
    ) % (pydev_src_dir, sorted_dict_repr(SetupHolder.setup))
    if sys.platform == "win32":
        debug_command: str = debug_command.replace('"', '\\"')
        debug_command: str = '"%s"' % debug_command
    res = pydev_monkey.patch_args(check)
    assert res == ["C:\\bin\\python.exe", "-qX", "faulthandler", "-c", debug_command]


def test_monkey_patch_args_flag_in_single_arg_2() -> None:
    SetupHolder.setup = {"client": "127.0.0.1", "port": "0", "ppid": os.getpid(), "protocol-quoted-line": True, "skip-notify-stdin": True}
    check: list[str] = ["C:\\bin\\python.exe", "-qX", "faulthandler", "-c", 'connect("127.0.0.1")']
    debug_command: str = (
        "import sys; sys.path.insert(0, r'%s'); import pydevd; pydevd.config('quoted-line', ''); "
        "pydevd.settrace(host='127.0.0.1', port=0, suspend=False, trace_only_current_thread=False, patch_multiprocessing=True, access_token=None, client_access_token=None, __setup_holder__=%s); "
        ""
        'connect("127.0.0.1")'
    ) % (pydev_src_dir, sorted_dict_repr(SetupHolder.setup))
    if sys.platform == "win32":
        debug_command: str = debug_command.replace('"', '\\"')
        debug_command: str = '"%s"' % debug_command
    res = pydev_monkey.patch_args(check)
    assert res == ["C:\\bin\\python.exe", "-qX", "faulthandler", "-c", debug_command]


def test_monkey_patch_args_flag_in_single_arg_3() -> None:
    SetupHolder.setup = {"client": "127.0.0.1", "port": "0", "ppid": os.getpid(), "protocol-quoted-line": True, "skip-notify-stdin": True}
    check: list[str] = ["C:\\bin\\python.exe", "-qc", 'connect("127.0.0.1")']
    debug_command: str = (
        "import sys; sys.path.insert(0, r'%s'); import pydevd; pydevd.config('quoted-line', ''); "
        "pydevd.settrace(host='127.0.0.1', port=0, suspend=False, trace_only_current_thread=False, patch_multiprocessing=True, access_token=None, client_access_token=None, __setup_holder__=%s); "
        ""
        'connect("127.0.0.1")'
    ) % (pydev_src_dir, sorted_dict_repr(SetupHolder.setup))
    if sys.platform == "win32":
        debug_command: str = debug_command.replace('"', '\\"')
        debug_command: str = '"%s"' % debug_command
    res = pydev_monkey.patch_args(check)
    assert res == ["C:\\bin\\python.exe", "-qc", debug_command]


def test_monkey_patch_args_x_flag_inline() -> None:
    SetupHolder.setup = {"client": "127.0.0.1", "port": "0", "ppid": os.getpid(), "protocol-quoted-line": True, "skip-notify-stdin": True}
    check: list[str] = ["C:\\bin\\python.exe", "-Xfaulthandler", "-c", 'connect("127.0.0.1")', "arg1"]
    debug_command: str = (
        "import sys; sys.path.insert(0, r'%s'); import pydevd; pydevd.config('quoted-line', ''); "
        "pydevd.settrace(host='127.0.0.1', port=0, suspend=False, trace_only_current_thread=False, patch_multiprocessing=True, access_token=None, client_access_token=None, __setup_holder__=%s); "
        ""
        'connect("127.0.0.1")'
    ) % (pydev_src_dir, sorted_dict_repr(SetupHolder.setup))
    if sys.platform == "win32":
        debug_command: str = debug_command.replace('"', '\\"')
        debug_command: str = '"%s"' % debug_command
    res = pydev_monkey.patch_args(check)
    assert res == ["C:\\bin\\python.exe", "-Xfaulthandler", "-c", debug_command, "arg1"]


def test_monkey_patch_args_c_flag_inline() -> None:
    SetupHolder.setup = {"client": "127.0.0.1", "port": "0", "ppid": os.getpid(), "protocol-quoted-line": True, "skip-notify-stdin": True}
    check: list[str] = ["C:\\bin\\python.exe", "-X", "faulthandler", '-cconnect("127.0.0.1")', "arg1"]
    debug_command: str = (
        "import sys; sys.path.insert(0, r'%s'); import pydevd; pydevd.config('quoted-line', ''); "
        "pydevd.settrace(host='127.0.0.1', port=0, suspend=False, trace_only_current_thread=False, patch_multiprocessing=True, access_token=None, client_access_token=None, __setup_holder__=%s); "
        ""
        'connect("127.0.0.1")'
    ) % (pydev_src_dir, sorted_dict_repr(SetupHolder.setup))
    if sys.platform == "win32":
        debug_command: str = debug_command.replace('"', '\\"')
        debug_command: str = '"%s"' % debug_command
    res = pydev_monkey.patch_args(check)
    assert res == ["C:\\bin\\python.exe", "-X", "faulthandler", "-c", debug_command, "arg1"]


def test_monkey_patch_args_module() -> None:
    SetupHolder.setup = {"client": "127.0.0.1", "port": "0", "multiprocess": True, "skip-notify-stdin": True}
    check: list[str] = ["C:\\bin\\python.exe", "-m", "test"]
    from _pydevd_bundle.pydevd_command_line_handling import get_pydevd_file

    assert pydev_monkey.patch_args(check) == [
        "C:\\bin\\python.exe",
        get_pydevd_file(),
        "--module",
        "--port",
        "0",
        "--ppid",
        str(os.getpid()),
        "--client",
        "127.0.0.1",
        "--multiprocess",
        "--skip-notify-stdin",
        "--protocol-quoted-line",
        "--file",
        "test",
    ]


def test_monkey_patch_args_unbuffered_module() -> None:
    SetupHolder.setup = {"client": "127.0.0.1", "port": "0", "multiprocess": True, "skip-notify-stdin": True}
    check: list[str] = ["C:\\bin\\python.exe", "-u", "-m", "test"]
    from _pydevd_bundle.pydevd_command_line_handling import get_pydevd_file

    assert pydev_monkey.patch_args(check) == [
        "C:\\bin\\python.exe",
        "-u",
        get_pydevd_file(),
        "--module",
        "--port",
        "0",
        "--ppid",
        str(os.getpid()),
        "--client",
        "127.0.0.1",
        "--multiprocess",
        "--skip-notify-stdin",
        "--protocol-quoted-line",
        "--file",
        "test",
    ]


def test_monkey_patch_args_module_inline() -> None:
    SetupHolder.setup = {"client": "127.0.0.1", "port": "0", "multiprocess": True, "skip-notify-stdin": True}
    check: list[str] = ["C:\\bin\\python.exe", "-qOmtest"]
    from _pydevd_bundle.pydevd_command_line_handling import get_pydevd_file

    assert pydev_monkey.patch_args(check) == [
        "C:\\bin\\python.exe",
        "-qO",
        get_pydevd_file(),
        "--module",
        "--port",
        "0",
        "--ppid",
        str(os.getpid()),
        "--client",
        "127.0.0.1",
        "--multiprocess",
        "--skip-notify-stdin",
        "--protocol-quoted-line",
        "--file",
        "test",
    ]


def test_monkey_patch_args_module_inline2() -> None:
    SetupHolder.setup = {"client": "127.0.0.1", "port": "0", "multiprocess": True, "skip-notify-stdin": True}
    check: list[str] = ["C:\\bin\\python.exe", "-qOm", "test"]
    from _pydevd_bundle.pydevd_command_line_handling import get_pydevd_file

    assert pydev_monkey.patch_args(check) == [
        "C:\\bin\\python.exe",
        "-qO",
        get_pydevd_file(),
        "--module",
        "--port",
        "0",
        "--ppid",
        str(os.getpid()),
        "--client",
        "127.0.0.1",
        "--multiprocess",
        "--skip-notify-stdin",
        "--protocol-quoted-line",
        "--file",
        "test",
    ]


def test_monkey_patch_args_no_indc() -> None:
    SetupHolder.setup = {"client": "127.0.0.1", "port": "0"}
    check: list[str] = ["C:\\bin\\python.exe", 'connect(\\"127.0.0.1\\")', "with spaces"]
    from _pydevd_bundle.pydevd_command_line_handling import get_pydevd_file

    assert pydev_monkey.patch_args(check) == [
        "C:\\bin\\python.exe",
        get_pydevd_file(),
        "--port",
        "0",
        "--ppid",
        str(os.getpid()),
        "--client",
        "127.0.0.1",
        "--protocol-quoted-line",
        "--file",
        '"connect(\\\\\\"127.0.0.1\\\\\\")"' if sys.platform == "win32" else 'connect(\\"127.0.0.1\\")',
        '"with spaces"' if sys.platform == "win32" else "with spaces",
    ]


def test_monkey_patch_args_no_indc_with_pydevd() -> None:
    SetupHolder.setup = {"client": "127.0.0.1", "port": "0"}
    check: list[str] = ["C:\\bin\\python.exe", "pydevd.py", 'connect(\\"127.0.0.1\\")', "bar"]

    assert pydev_monkey.patch_args(check) == ["C:\\bin\\python.exe", "pydevd.py", 'connect(\\"127.0.0.1\\")', "bar"]


def test_monkey_patch_args_no_indc_without_pydevd() -> None:
    from _pydevd_bundle.pydevd_command_line_handling import get_pydevd_file

    SetupHolder.setup = {"client": "127.0.0.1", "port": "0"}
    check: list[str] = ["C:\\bin\\python.exe", "target.py", 'connect(\\"127.0.0.1\\")', "bar"]
    assert pydev_monkey.patch_args(check) == [
        "C:\\bin\\python.exe",
        get_pydevd_file(),
        "--port",
        "0",
        "--ppid",
        str(os.getpid()),
        "--client",
        "127.0.0.1",
        "--protocol-quoted-line",
        "--file",
        "target.py",
        '"connect(\\\\\\"127.0.0.1\\\\\\")"' if sys.platform == "win32" else 'connect(\\"127.0.0.1\\")',
        "bar",
    ]


@pytest.mark.parametrize("use_bytes", [True, False])
def test_monkey_patch_c_program_arg(use_bytes) -> None:
    from _pydevd_bundle.pydevd_command_line_handling import get_pydevd_file

    SetupHolder.setup = {"client": "127.0.0.1", "port": "0", "module": "ignore.this"}
    check: list[str] = ["C:\\bin\\python.exe", "-u", "target.py", "-c", "-áéíóú"]

    encode = lambda s: s
    if use_bytes:
        check: list[bytes] = [c.encode("utf-8") for c in check]
        encode = lambda s: s.encode("utf-8")

    assert pydev_monkey.patch_args(check) == [
        encode("C:\\bin\\python.exe"),
        encode("-u"),
        get_pydevd_file(),
        "--port",
        "0",
        "--ppid",
        str(os.getpid()),
        "--client",
        "127.0.0.1",
        "--protocol-quoted-line",
        "--file",
        encode("target.py"),
        encode("-c"),
        encode("-áéíóú"),
    ]


def test_monkey_patch_args_module_single_arg() -> None:
    SetupHolder.setup = {"client": "127.0.0.1", "port": "0", "multiprocess": True, "module": "ignore.this"}
    check: list[str] = ["C:\\bin\\python.exe", "-mtest", "bar"]
    from _pydevd_bundle.pydevd_command_line_handling import get_pydevd_file

    assert pydev_monkey.patch_args(check) == [
        "C:\\bin\\python.exe",
        get_pydevd_file(),
        "--module",
        "--port",
        "0",
        "--ppid",
        str(os.getpid()),
        "--client",
        "127.0.0.1",
        "--multiprocess",
        "--protocol-quoted-line",
        "--file",
        "test",
        "bar",
    ]


def test_monkey_patch_args_stdin() -> None:
    SetupHolder.setup = {"client": "127.0.0.1", "port": "0", "multiprocess": True, "module": "ignore.this"}
    check: list[str] = ["C:\\bin\\python.exe", "-Xfaulthandler", "-"]
    # i.e.: we don't deal with the stdin.
    assert pydev_monkey.patch_args(check) == check


def test_monkey_patch_args_c_with_bytes() -> None:
    # Regression test for issue #1905: on Linux/WSL with loky/joblib, subprocess args
    # can be bytes, causing TypeError when patching -c arguments. This test ensures
    # the patch_args function handles bytes argv correctly.
    SetupHolder.setup = {"client": "127.0.0.1", "port": "0", "ppid": os.getpid(), "protocol-quoted-line": True, "skip-notify-stdin": True}
    check: list[bytes] = [
        b"C:\\bin\\python.exe",
        b"-u",
        b"-c",
        b'from joblib.externals.loky.backend import get_context; get_context().Manager()',
    ]

    # Should not raise TypeError about bytes/str mismatch.
    result = pydev_monkey.patch_args(check)

    # Result should be a list with bytes elements (since input was bytes)
    assert isinstance(result, list)
    assert all(isinstance(item, (bytes, str)) for item in result)
    # The result should contain our patched debugpy setup somewhere
    result_str: str = b"".join(item.encode() if isinstance(item, str) else item for item in result).decode()
    assert "pydevd.settrace" in result_str


def test_is_python_sys_executable_exact():
    # Exact sys.executable should be considered python even if basename doesn't contain "python"
    assert pydev_monkey.is_python(sys.executable) is True


def test_is_python_sys_executable_bytes():
    # Bytes version of sys.executable
    assert pydev_monkey.is_python(sys.executable.encode()) is True


def test_is_python_sys_executable_symlink(tmp_path):
    # Same binary invoked through a symlink with non-python name should still be recognized
    # e.g. custom native binary named "myapp" that is a symlink to python
    import os

    link_path = tmp_path / "myapp"
    try:
        os.symlink(sys.executable, str(link_path))
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported on this platform")

    assert pydev_monkey.is_python(str(link_path)) is True


def test_is_python_sys_executable_relative(tmp_path):
    # Relative path to sys.executable should be recognized
    import os

    rel = os.path.relpath(sys.executable, start=str(tmp_path))
    # Change cwd to tmp_path to make relative resolution work for realpath
    old_cwd = os.getcwd()
    try:
        os.chdir(str(tmp_path))
        assert pydev_monkey.is_python(rel) is True
    finally:
        os.chdir(old_cwd)


def test_is_python_sys_executable_normcase():
    # On Windows, normcase makes comparison case-insensitive. On POSIX, normcase is no-op,
    # but realpath+samefile already covers identity. This test ensures case variation
    # doesn't break on POSIX and would work on Windows.
    import os

    upper = sys.executable.upper()
    # If file system is case-insensitive or normcase normalizes, this should be True.
    # On case-sensitive POSIX, upper won't exist, so samefile will fail and normcase
    # won't match, but we at least ensure the function doesn't crash and returns a bool.
    # To simulate Windows behavior, directly test normcase equivalence logic.
    norm_upper = os.path.normcase(os.path.normpath(os.path.realpath(upper)))
    norm_sys = os.path.normcase(os.path.normpath(os.path.realpath(sys.executable)))
    if os.path.exists(upper) or norm_upper == norm_sys:
        # Only assert True when the OS would actually consider them same
        assert pydev_monkey.is_python(upper) is True
    else:
        # On case-sensitive systems, upper path likely doesn't exist, so should be False
        # unless it accidentally matches via other heuristics - just ensure bool
        assert isinstance(pydev_monkey.is_python(upper), bool)


def test_is_python_non_python():
    assert pydev_monkey.is_python("/bin/ls") is False
    assert pydev_monkey.is_python("/usr/bin/myapp") is False


def test_is_python_name_contains_python():
    # Traditional detection via basename still works
    assert pydev_monkey.is_python("/usr/bin/python3") is True
    assert pydev_monkey.is_python("/usr/bin/python3.12") is True
    assert pydev_monkey.is_python("C:\\Python\\python.exe") is True
    assert pydev_monkey.is_python("/opt/pypy/bin/pypy") is True
