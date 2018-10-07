# Python Tools for Visual Studio debug server

[![Build Status](https://ptvsd.visualstudio.com/_apis/public/build/definitions/557bd35a-f98d-4c49-9bc9-c7d548f78e4d/1/badge)](https://ptvsd.visualstudio.com/ptvsd/ptvsd%20Team/_build/index?definitionId=1)
[![Build Status](https://travis-ci.org/Microsoft/ptvsd.svg?branch=master)](https://travis-ci.org/Microsoft/ptvsd)
[![GitHub](https://img.shields.io/badge/license-MIT-brightgreen.svg)](https://raw.githubusercontent.com/Microsoft/ptvsd/master/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/ptvsd.svg)](https://pypi.org/project/ptvsd/)

## `ptvsd` CLI Usage
### Debug a script file
Use this to launch your script file. Launch script file without waiting for debugger to attach.
```console
-m ptvsd --port 5678 myfile.py
```
If you want the debugger to attach before running your code use `--wait` flag.
```console
-m ptvsd --port 5678 --wait myfile.py
```

### Debug a module
Use this to launch your module. Launch script file without waiting for debugger to attach.
```console
-m ptvsd --port 5678 -m mymodule
```
If you want the debugger to attach before running your code use `--wait` flag.
```console
-m ptvsd --port 5678 --wait -m mymodule
```

### Debug a process by id
Attach to a process running python code.
```console
-m ptvsd --host 0.0.0.0 --port 5678 --pid 12345
```

## `ptvsd` Import usage
### Enable debugging
In your script import ptvsd and call `enable_attach` to enable the process to attach to the debugger. The default port is 5678. You can configure this while calling `enable_attach`. 
```python
import ptvsd

ptvsd.enable_attach()

# your code
```
### Wait for attach
Use the `wait_for_attach()` function to block execution until debugger is attached.
```python
import ptvsd

ptvsd.enable_attach()
# script execution will stop here till debugger is attached
ptvsd.wait_for_attach()

# your code
```

### `breakpoint()` function
In python >= 3.7, `ptvsd` supports the `breakpoint()` function. Use `break_into_debugger()` function for similar behavior and compatibility with older versions of python (2.7 and >= 3.4). These functions will block only if the debugger is attached.
```python
import ptvsd

ptvsd.enable_attach()

while True:
    # your code
    breakpoint() # ptvsd.break_into_debugger()
    # your code
```

## Custom Protocol arguments
### Launch request arguments
```js
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
```js
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
