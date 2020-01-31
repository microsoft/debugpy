# debugpy - a debugger for Python

[![Build Status](https://dev.azure.com/debugpy/debugpy/_apis/build/status/debugpy-test-automation?branchName=master)](https://dev.azure.com/debugpy/debugpy/_build/latest?definitionId=1&branchName=master)
[![Build Status](https://travis-ci.org/microsoft/debugpy.svg?branch=master)](https://travis-ci.org/microsoft/debugpy)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=microsoft_debugpy&metric=coverage)](https://sonarcloud.io/dashboard?id=microsoft_debugpy)
[![GitHub](https://img.shields.io/badge/license-MIT-brightgreen.svg)](https://raw.githubusercontent.com/microsoft/debugpy/master/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/debugpy.svg)](https://pypi.org/project/debugpy/)
[![PyPI](https://img.shields.io/pypi/pyversions/debugpy.svg)](https://pypi.org/project/debugpy/)

This debugger implements the Debug Adapter Protocol: [debugProtocol.json](https://github.com/Microsoft/vscode-debugadapter-node/blob/master/debugProtocol.json)

## `debugpy` CLI Usage
### Debugging a script file
To run a script file with debugging enabled, but without waiting for the IDE to attach (i.e. code starts executing immediately):
```console
-m debugpy --host localhost --port 5678 myfile.py
```
To wait until the IDE attaches before running your code, use the `--wait` switch.
```console
-m debugpy --host localhost  --port 5678 --wait myfile.py
```
The `--host` option specifies the interface on which the debug server is listening for connections. To be able to attach from another machine, make sure that the server is listening on a public interface - using `0.0.0.0` will make it listen on all available interfaces:
```console
-m debugpy --host 0.0.0.0 --port 5678 myfile.py
```
This should only be done on secure networks, since anyone who can connect to the specified port can then execute arbitrary code within the debugged process.

To pass arguments to the script, just specify them after the filename. This works the same as with Python itself - everything up to  the filename is processed by debugpy, but everything after that becomes `sys.argv` of the running process.

### Debugging a module
To run a module, use the `-m` switch instead of filename:
```console
-m debugpy --host localhost --port 5678 -m mymodule
```
Same as with scripts, command line arguments can be passed to the module by specifying them after the module name. All other debugpy switches work identically in this mode; in particular, `--wait` can be used to block execution until the IDE attaches.

### Attaching to a running process by ID
The following command injects the debugger into a process with a given PID that is running Python code. Once the command returns, a debugpy server is running within the process, as if that process was launched via `-m debugpy` itself.
```console
-m debugpy --host localhost --port 5678 --pid 12345
```

## `debugpy` Import usage
### Enabling debugging
At the beginning of your script, import debugpy, and call `debugpy.enable_attach()` to start the debug server. The default hostname is `0.0.0.0`, and the default port is 5678; these can be overridden by passing a `(host, port)` tuple as the first argument of `enable_attach()`.
```python
import debugpy
debugpy.enable_attach()
...
```

### Waiting for the IDE to attach
Use the `debugpy.wait_for_attach()` function to block program execution until the IDE is attached.
```python
import debugpy
debugpy.enable_attach()
debugpy.wait_for_attach()  # blocks execution until IDE is attached
...
```

### `breakpoint()` function
In Python 3.7 and above, `debugpy` supports the standard `breakpoint()` function. Use `debugpy.break_into_debugger()` function for similar behavior and compatibility with older versions of Python (3.6 and below). If the debugger is attached when either of these functions is invoked, it will pause execution on the calling line, as if it had a breakpoint set. If there's no IDE attached, the functions do nothing, and the code continues to execute normally.
```python
import debugpy
debugpy.enable_attach()

while True:
    ...
    breakpoint()  # or debugpy.break_into_debugger() on <3.7
    ...
```

## Custom Protocol arguments
### Launch request arguments
```json5
{
    "debugOptions":  [
            "RedirectOutput",       // Whether to redirect stdout and stderr (see pydevd_comm.CMD_REDIRECT_OUTPUT)
            "WaitOnNormalExit",     // Wait for user input after user code exits normally
            "WaitOnAbnormalExit",   // Wait for user input after user code exits with error
            "Django",               // Enables Django Template debugging
            "Jinja",                // Enables Jinja (Flask) Template debugging
            "FixFilePathCase",      // See FIX_FILE_PATH_CASE in wrapper.py
            "DebugStdLib",          // Whether to enable debugging of standard library functions
            "StopOnEntry",          // Whether to stop at first line of user code
            "ShowReturnValue",      // Show return values of functions
    ]
}
```

### Attach request arguments
```json5
{
    "debugOptions":  [
            "RedirectOutput",       // Whether to redirect stdout and stderr (see pydevd_comm.CMD_REDIRECT_OUTPUT)
            "Django",               // Enables Django Template debugging
            "Jinja",                // Enables Jinja (Flask) Template debugging
            "FixFilePathCase",      // See FIX_FILE_PATH_CASE in wrapper.py
            "DebugStdLib",          // Whether to enable debugging of standard library functions
            "WindowsClient",        // Whether client OS is Windows
            "UnixClient",           // Whether client OS is Unix
            "ShowReturnValue",      // Show return values of functions
    ],
    "pathMappings": [
        {
            "localRoot": "C:\\Project\\src",   // Local root  (where the IDE is running)
            "remoteRoot": "/home/smith/proj"   // Remote root (where remote code is running)
        },
        // Add more path mappings
    ]
}
```

## Debugger logging

To enable debugger internal logging via CLI, the `--log-dir` switch can be used:
```console
-m debugpy --log-dir path/to/logs ...
```

When using `enable_attach`, the same can be done with `log_dir` argument:
```py
debugpy.enable_attach(log_dir='path/to/logs')
```

In both cases, the environment variable `DEBUGPY_LOG_DIR` can also be set to the same effect.

When logging is enabled, debugpy will create several log files with names matching `debugpy*.log` in the specified directory, corresponding to different components of the debugger. When subprocess debugging is enabled, separate logs are created for every subprocess.

