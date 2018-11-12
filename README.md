# Python Tools for Visual Studio debug server

[![Build Status](https://ptvsd.visualstudio.com/_apis/public/build/definitions/557bd35a-f98d-4c49-9bc9-c7d548f78e4d/1/badge)](https://ptvsd.visualstudio.com/ptvsd/ptvsd%20Team/_build/index?definitionId=1)
[![Build Status](https://travis-ci.org/Microsoft/ptvsd.svg?branch=master)](https://travis-ci.org/Microsoft/ptvsd)
[![GitHub](https://img.shields.io/badge/license-MIT-brightgreen.svg)](https://raw.githubusercontent.com/Microsoft/ptvsd/master/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/ptvsd.svg)](https://pypi.org/project/ptvsd/)

## `ptvsd` CLI Usage
### Debugging a script file
To run a script file with debugging enabled, but without waiting for the debugger to attach (i.e. code starts executing immediately):
```console
-m ptvsd --host localhost --port 5678 myfile.py
```
To wait until the debugger attaches before running your code, use the `--wait` switch.
```console
-m ptvsd --host localhost  --port 5678 --wait myfile.py
```
The `--host` option specifies the interface on which the debug server is listening for connections. To be able to attach from another machine, make sure that the server is listening on a public interface - using `0.0.0.0` will make it listen on all available interfaces:
```console
-m ptvsd --host 0.0.0.0 --port 5678 myfile.py
```
This should only be done on secure networks, since anyone who can connect to the specified port can then execute arbitrary code within the debugged process.

To pass arguments to the script, just specify them after the filename. This works the same as with Python itself - everything up to  the filename is processed by ptvsd, but everything after that becomes `sys.argv` of the running process.

### Debugging a module
To run a module, use the `-m` switch instead of filename:
```console
-m ptvsd --host localhost --port 5678 -m mymodule
```
Same as with scripts, command line arguments can be passed to the module by specifying them after the module name. All other ptvsd switches work identically in this mode; in particular, `--wait` can be used to block execution until the debugger attaches.

### Attaching to a running process by ID
The following command injects the debugger into a process with a given PID that is running Python code. Once the command returns, a ptvsd server is running within the process, as if that process was launched via `-m ptvsd` itself.
```console
-m ptvsd --host localhost --port 5678 --pid 12345
```

## `ptvsd` Import usage
### Enabling debugging
At the beginning of your script, import ptvsd, and call `ptvsd.enable_attach()` to start the debug server. The default hostname is `0.0.0.0`, and the default port is 5678; these can be overridden by passing a `(host, port)` tuple as the first argument of `enable_attach()`.
```python
import ptvsd
ptvsd.enable_attach()
...
```

### Waiting for the debugger to attach
Use the `ptvsd.wait_for_attach()` function to block program execution until the debugger is attached.
```python
import ptvsd
ptvsd.enable_attach()
ptvsd.wait_for_attach()  # blocks execution until debugger is attached
...
```

### `breakpoint()` function
In Python 3.7 and above, `ptvsd` supports the standard `breakpoint()` function. Use `ptvsd.break_into_debugger()` function for similar behavior and compatibility with older versions of Python (3.6 and below). If the debugger is attached when either of these functions is invoked, it will pause execution on the calling line, as if it had a breakpoint set. If there's no debugger attached, the functions do nothing, and the code continues to execute normally.
```python
import ptvsd
ptvsd.enable_attach()

while True:
    ...
    breakpoint() # or ptvsd.break_into_debugger() on <3.7
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
            "localRoot": "C:\\Project\\src",   // Local root  (where source and debugger running)
            "remoteRoot": "/home/smith/proj"   // Remote root (where remote code is running)
        },
        // Add more path mappings
    ]
}
```
