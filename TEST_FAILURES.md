Py39 eval failures? Need to double check on original

Left to do:
- Get Cython stuff built again? Maybe it's only on windows (pxd files)

After Cython Update:
FAILED tests/debugpy/test_exception.py::test_systemexit[0-zero-uncaught--launch(console=internalConsole)-program]
FAILED tests/debugpy/test_args.py::test_args[attach_listen(api)-program]
FAILED tests/debugpy/test_exception.py::test_systemexit[1-zero-uncaught--launch(console=externalTerminal)-module]
FAILED tests/debugpy/test_exception.py::test_systemexit[nan--uncaught-raised-launch(console=internalConsole)-program]
FAILED tests/debugpy/test_exception.py::test_vsc_exception_options_raise_without_except[program-launch-uncaught-raised]
FAILED tests/debugpy/test_exception.py::test_success_exitcodes[django-break_on_system_exit_zero-3-launch(console=internalConsole)-program]
FAILED tests/debugpy/test_exception.py::test_systemexit[1-zero-uncaught-raised-launch(console=internalConsole)-program]
FAILED tests/debugpy/test_exception.py::test_raise_exception_options[program-launch-exceptions1-unhandled]
FAILED tests/debugpy/test_exclude_rules.py::test_exceptions_and_partial_exclude_rules[program-launch-exclude_callback_dir]
FAILED tests/debugpy/test_exception.py::test_systemexit[1--uncaught--launch(console=internalConsole)-program]
FAILED tests/debugpy/test_exception.py::test_systemexit[nan-zero-uncaught-raised-launch(console=integratedTerminal)-module]
FAILED tests/debugpy/test_exception.py::test_success_exitcodes[--3-launch(console=internalConsole)-program]
FAILED tests/debugpy/test_exception.py::test_systemexit[nan-zero-uncaught-raised-launch(console=internalConsole)-program]
FAILED tests/debugpy/test_stop_on_entry.py::test_stop_on_entry[program-launch(console=internalConsole)-breakpoint] - ...
FAILED tests/debugpy/test_stop_on_entry.py::test_stop_on_entry[program-launch(console=internalConsole)-] - assert [{'...
FAILED tests/debugpy/test_stop_on_entry.py::test_stop_on_entry[program-launch(console=integratedTerminal)-breakpoint]
FAILED tests/debugpy/test_stop_on_entry.py::test_stop_on_entry[program-launch(console=integratedTerminal)-] - assert ...
FAILED tests/debugpy/test_stop_on_entry.py::test_stop_on_entry[program-launch(console=externalTerminal)-breakpoint]
FAILED tests/debugpy/test_stop_on_entry.py::test_stop_on_entry[program-launch(console=externalTerminal)-] - assert [{...
FAILED tests/debugpy/test_exception.py::test_systemexit[0-zero-uncaught--launch(console=internalConsole)-module]
FAILED tests/debugpy/test_stop_on_entry.py::test_stop_on_entry[module-launch(console=internalConsole)-breakpoint] - a...
FAILED tests/debugpy/test_stop_on_entry.py::test_stop_on_entry[module-launch(console=internalConsole)-] - assert [{'i...
FAILED tests/debugpy/test_stop_on_entry.py::test_stop_on_entry[module-launch(console=integratedTerminal)-breakpoint]
FAILED tests/debugpy/test_stop_on_entry.py::test_stop_on_entry[module-launch(console=integratedTerminal)-] - assert [...
FAILED tests/debugpy/test_stop_on_entry.py::test_stop_on_entry[module-launch(console=externalTerminal)-breakpoint] - ...
FAILED tests/debugpy/test_stop_on_entry.py::test_stop_on_entry[module-launch(console=externalTerminal)-] - assert [{'...
FAILED tests/debugpy/test_exception.py::test_systemexit[1--uncaught-raised-launch(console=integratedTerminal)-module]
FAILED tests/debugpy/test_exception.py::test_systemexit[nan--uncaught--launch(console=internalConsole)-program]
FAILED tests/debugpy/test_exception.py::test_vsc_exception_options_raise_without_except[program-launch-uncaught-]
FAILED tests/debugpy/test_exception.py::test_systemexit[1--uncaught-raised-launch(console=internalConsole)-program]
FAILED tests/debugpy/test_exception.py::test_success_exitcodes[django-break_on_system_exit_zero-3-launch(console=integratedTerminal)-module]
FAILED tests/debugpy/test_exception.py::test_success_exitcodes[-break_on_system_exit_zero-3-launch(console=integratedTerminal)-module]
FAILED tests/debugpy/test_exception.py::test_systemexit[1-zero-uncaught-raised-launch(console=externalTerminal)-program]
FAILED tests/debugpy/test_exception.py::test_systemexit[1-zero-uncaught--launch(console=integratedTerminal)-program]
FAILED tests/debugpy/test_exception.py::test_success_exitcodes[django-break_on_system_exit_zero-0-launch(console=externalTerminal)-module]
FAILED tests/debugpy/test_exception.py::test_systemexit[1-zero-uncaught-raised-launch(console=internalConsole)-module]
FAILED tests/debugpy/test_exception.py::test_success_exitcodes[django-break_on_system_exit_zero-3-launch(console=internalConsole)-module]
FAILED tests/debugpy/test_exception.py::test_success_exitcodes[-break_on_system_exit_zero-3-launch(console=internalConsole)-program]
FAILED tests/debugpy/test_exception.py::test_systemexit[nan-zero-uncaught--launch(console=internalConsole)-module]
FAILED tests/debugpy/test_exception.py::test_systemexit[nan-zero-uncaught-raised-launch(console=externalTerminal)-program]
FAILED tests/debugpy/test_exception.py::test_success_exitcodes[--3-launch(console=internalConsole)-module]
FAILED tests/debugpy/test_exception.py::test_exception_stack[program-launch-default]
FAILED tests/debugpy/test_exclude_rules.py::test_exceptions_and_partial_exclude_rules[program-launch-exclude_code_to_debug]
FAILED tests/debugpy/test_exception.py::test_systemexit[1--uncaught--launch(console=internalConsole)-module]
FAILED tests/debugpy/test_exception.py::test_systemexit[nan--uncaught-raised-launch(console=internalConsole)-module]
FAILED tests/debugpy/test_exception.py::test_systemexit[nan--uncaught--launch(console=integratedTerminal)-module]
FAILED tests/debugpy/test_exception.py::test_systemexit[0-zero-uncaught-raised-launch(console=internalConsole)-program]
FAILED tests/debugpy/test_exception.py::test_systemexit[1--uncaught-raised-launch(console=internalConsole)-module]
FAILED tests/debugpy/test_exception.py::test_systemexit[1--uncaught-raised-launch(console=externalTerminal)-program]
FAILED tests/debugpy/test_exception.py::test_systemexit[0-zero-uncaught--launch(console=integratedTerminal)-program]
FAILED tests/debugpy/test_exception.py::test_success_exitcodes[django-break_on_system_exit_zero-3-launch(console=externalTerminal)-program]
ERROR tests/_logs/3.12-64/tests/debugpy/test_exception.py/test_raise_exception_options[program-launch-exceptions0-userUnhandled]/Session[1]