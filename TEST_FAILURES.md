Py39 eval failures? Need to double check on original


Pydevd failures (py312)
FAILED tests_python/test_debugger.py::test_case_handled_exceptions4 - AssertionError: TimeoutError (note: error trying to dump threads on timeout).
FAILED tests_python/test_debugger.py::test_path_translation[True] - AssertionError: TimeoutError (note: error trying to dump threads on timeout).
FAILED tests_python/test_debugger.py::test_path_translation[False] - AssertionError: TimeoutError (note: error trying to dump threads on timeout).
FAILED tests_python/test_debugger.py::test_remote_debugger_basic - AssertionError: TimeoutError
FAILED tests_python/test_debugger.py::test_remote_debugger_threads - AssertionError: TimeoutError
FAILED tests_python/test_debugger.py::test_py_37_breakpoint_remote - AssertionError: TimeoutError
FAILED tests_python/test_debugger.py::test_remote_debugger_multi_proc[True] - AssertionError: TimeoutError
FAILED tests_python/test_debugger.py::test_remote_debugger_multi_proc[False] - AssertionError: TimeoutError
FAILED tests_python/test_debugger.py::test_remote_unhandled_exceptions[True] - AssertionError: TimeoutError
FAILED tests_python/test_debugger.py::test_remote_unhandled_exceptions[False] - AssertionError: TimeoutError
FAILED tests_python/test_debugger.py::test_top_level_exceptions_on_attach[scenario_uncaught] - AssertionError: TimeoutError
FAILED tests_python/test_debugger.py::test_top_level_exceptions_on_attach[scenario_caught] - AssertionError: TimeoutError
FAILED tests_python/test_debugger.py::test_top_level_exceptions_on_attach[scenario_caught_and_uncaught] - AssertionError: TimeoutError
FAILED tests_python/test_debugger.py::test_asyncio_step_over_basic[_debugger_case_trio.py] - AssertionError: TimeoutError (note: error trying to dump threads on timeout).
FAILED tests_python/test_debugger.py::test_asyncio_step_over_end_of_function[_debugger_case_trio.py] - AssertionError: TimeoutError (note: error trying to dump threads on timeout).
FAILED tests_python/test_debugger.py::test_asyncio_step_in[_debugger_case_trio.py] - AssertionError: TimeoutError (note: error trying to dump threads on timeout).
FAILED tests_python/test_debugger.py::test_asyncio_step_return[_debugger_case_trio.py] - AssertionError: TimeoutError (note: error trying to dump threads on timeout).
FAILED tests_python/test_debugger.py::test_frame_eval_mode_corner_case_03 - AssertionError: TimeoutError
FAILED tests_python/test_debugger_json.py::test_evaluate_numpy - assert [{'special variables': ''}, {'dtype': "dtype('int64')"}, {'max': 'np.int64(2)'}, {'min': 'np.int64(2)'}, {'s...
FAILED tests_python/test_debugger_json.py::test_step_next_step_in_multi_threads[step_in-True] - AssertionError: Expected _event2_set to be set already.
FAILED tests_python/test_debugger_json.py::test_wait_for_attach_debugpy_mode - AssertionError: [WinError 10038] An operation was attempted on something that is not a socket
FAILED tests_python/test_debugger_json.py::test_wait_for_attach - AssertionError: [WinError 10038] An operation was attempted on something that is not a socket
FAILED tests_python/test_debugger_json.py::test_path_translation_and_source_reference - AssertionError: TimeoutError (note: error trying to dump threads on timeout).
FAILED tests_python/test_debugger_json.py::test_remote_debugger_basic - AssertionError: TimeoutError
FAILED tests_python/test_debugger_json.py::test_subprocess_pydevd_customization[] - AssertionError: TimeoutError
FAILED tests_python/test_debugger_json.py::test_subprocess_pydevd_customization[--use-c-switch] - AssertionError: TimeoutError
FAILED tests_python/test_debugger_json.py::test_terminate[kill_subprocesses_ignore_pid-terminate_request] - AssertionError: process PID not found (pid=22876)
FAILED tests_python/test_debugger_json.py::test_terminate[dont_kill_subprocesses-terminate_request] - AssertionError: process PID not found (pid=12860)
FAILED tests_python/test_debugger_json.py::test_terminate[dont_kill_subprocesses-terminate_debugee] - AssertionError: process PID not found (pid=27936)
FAILED tests_python/test_debugger_json.py::test_use_real_path_and_not_links[True] - OSError: [WinError 1314] A required privilege is not held by the client: 'C:\\Users\\rchiodo\\AppData\\Local\\Temp\...
FAILED tests_python/test_debugger_json.py::test_use_real_path_and_not_links[False] - OSError: [WinError 1314] A required privilege is not held by the client: 'C:\\Users\\rchiodo\\AppData\\Local\\Temp\...
FAILED tests_python/test_debugger_json.py::test_logging_api - AssertionError: Expected process.returncode to be 0. Found: 1
FAILED tests_python/test_safe_repr.py::TestSafeRepr::test_largest_repr - assert 158538 < 8192
FAILED tests_python/test_safe_repr.py::TestStrings::test_str_large - AssertionError: Expected:
FAILED tests_python/test_safe_repr.py::TestStrings::test_str_list_largest_unchanged - AssertionError: Expected:
FAILED tests_python/test_safe_repr.py::TestStrings::test_str_list_smallest_changed - AssertionError: Expected:
FAILED tests_python/test_safe_repr.py::TestStrings::test_bytes_large - AssertionError: Expected:
FAILED tests_python/test_safe_repr.py::TestUserDefinedObjects::test_custom_repr_many_items - AssertionError: Expected:
Pydevd Failures on main

FAILED tests_python/test_debugger.py::test_path_translation[True] - AssertionError: TimeoutError (note: error trying to dump threads on timeout).
FAILED tests_python/test_debugger.py::test_path_translation[False] - AssertionError: TimeoutError (note: error trying to dump threads on timeout).
FAILED tests_python/test_debugger.py::test_remote_debugger_basic - AssertionError: TimeoutError
FAILED tests_python/test_debugger.py::test_remote_debugger_threads - AssertionError: TimeoutError
FAILED tests_python/test_debugger.py::test_py_37_breakpoint_remote - AssertionError: TimeoutError
FAILED tests_python/test_debugger.py::test_remote_debugger_multi_proc[True] - AssertionError: TimeoutError
FAILED tests_python/test_debugger.py::test_remote_debugger_multi_proc[False] - AssertionError: TimeoutError
FAILED tests_python/test_debugger.py::test_remote_unhandled_exceptions[True] - AssertionError: TimeoutError
FAILED tests_python/test_debugger.py::test_remote_unhandled_exceptions[False] - AssertionError: TimeoutError
FAILED tests_python/test_debugger.py::test_top_level_exceptions_on_attach[scenario_uncaught] - AssertionError: TimeoutError
FAILED tests_python/test_debugger.py::test_top_level_exceptions_on_attach[scenario_caught] - AssertionError: TimeoutError
FAILED tests_python/test_debugger.py::test_top_level_exceptions_on_attach[scenario_caught_and_uncaught] - AssertionError: TimeoutError
FAILED tests_python/test_debugger.py::test_asyncio_step_over_basic[_debugger_case_trio.py] - AssertionError: TimeoutError (note: error trying to dump threads on timeout).
FAILED tests_python/test_debugger.py::test_asyncio_step_over_end_of_function[_debugger_case_trio.py] - AssertionError: TimeoutError (note: error trying to dump threads on timeout).
FAILED tests_python/test_debugger.py::test_asyncio_step_in[_debugger_case_trio.py] - AssertionError: TimeoutError (note: error trying to dump threads on timeout).
FAILED tests_python/test_debugger.py::test_asyncio_step_return[_debugger_case_trio.py] - AssertionError: TimeoutError (note: error trying to dump threads on timeout).
FAILED tests_python/test_debugger_json.py::test_evaluate_numpy - assert [{'special variables': ''}, {'dtype': "dtype('int64')"}, {'max': 'np.int64(2)'}, {'min': 'np.int64(2)'}, {'s...
FAILED tests_python/test_debugger_json.py::test_wait_for_attach_debugpy_mode - AssertionError: [WinError 10038] An operation was attempted on something that is not a socket
FAILED tests_python/test_debugger_json.py::test_wait_for_attach - AssertionError: [WinError 10038] An operation was attempted on something that is not a socket
FAILED tests_python/test_debugger_json.py::test_path_translation_and_source_reference - AssertionError: TimeoutError (note: error trying to dump threads on timeout).
FAILED tests_python/test_debugger_json.py::test_remote_debugger_basic - AssertionError: TimeoutError
FAILED tests_python/test_debugger_json.py::test_subprocess_pydevd_customization[] - AssertionError: TimeoutError
FAILED tests_python/test_debugger_json.py::test_subprocess_pydevd_customization[--use-c-switch] - AssertionError: TimeoutError
FAILED tests_python/test_debugger_json.py::test_terminate[kill_subprocesses_ignore_pid-terminate_request] - AssertionError: process PID not found (pid=27712)
FAILED tests_python/test_debugger_json.py::test_terminate[kill_subprocesses_ignore_pid-terminate_debugee] - AssertionError: process no longer exists (pid=15000)
FAILED tests_python/test_debugger_json.py::test_terminate[dont_kill_subprocesses-terminate_request] - AssertionError: process no longer exists (pid=10368)
FAILED tests_python/test_debugger_json.py::test_terminate[dont_kill_subprocesses-terminate_debugee] - AssertionError: process PID not found (pid=32164)
FAILED tests_python/test_debugger_json.py::test_use_real_path_and_not_links[True] - OSError: [WinError 1314] A required privilege is not held by the client: 'C:\\Users\\rchiodo\\AppData\\Local\\Temp\...
FAILED tests_python/test_debugger_json.py::test_use_real_path_and_not_links[False] - OSError: [WinError 1314] A required privilege is not held by the client: 'C:\\Users\\rchiodo\\AppData\\Local\\Temp\...
FAILED tests_python/test_debugger_json.py::test_logging_api - AssertionError: Expected process.returncode to be 0. Found: 1