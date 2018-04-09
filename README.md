# Python Tools for Visual Studio debug server

[![Build Status](https://travis-ci.org/Microsoft/ptvsd.svg?branch=master)](https://travis-ci.org/Microsoft/ptvsd)

## Contributing

This project welcomes contributions and suggestions.  Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit https://cla.microsoft.com.

When you submit a pull request, a CLA-bot will automatically determine whether you need to provide
a CLA and decorate the PR appropriately (e.g., label, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## Custom Protocol arguments

### 1. Launch request arguments
```js
{
    "debugOptions":  [
            "RedirectOutput",       // Whether to redirect stdout and stderr (see pydevd_comm.CMD_REDIRECT_OUTPUT)
            "WaitOnNormalExit",     // See WAIT_ON_NORMAL_EXIT in wrapper.py
            "WaitOnAbnormalExit",   // See WAIT_ON_ABNORMAL_EXIT in wrapper.py
            "Django",               // Enables Django Template debugging
            "Jinja",                // Enables Jinja (Flask) Template debugging
            "FixFilePathCase",      // See FIX_FILE_PATH_CASE in wrapper.py
            "DebugStdLib"           // Whether to enable debugging of standard library functions
    ]
}
```

### 2. Attach request arguments
```js
{
    "debugOptions":  [
            "RedirectOutput",       // Whether to redirect stdout and stderr (see pydevd_comm.CMD_REDIRECT_OUTPUT)
            "WaitOnNormalExit",     // See WAIT_ON_NORMAL_EXIT in wrapper.py
            "WaitOnAbnormalExit",   // See WAIT_ON_ABNORMAL_EXIT in wrapper.py
            "Django",               // Enables Django Template debugging
            "Jinja",                // Enables Jinja (Flask) Template debugging
            "FixFilePathCase",      // See FIX_FILE_PATH_CASE in wrapper.py
            "DebugStdLib"           // Whether to enable debugging of standard library functions
            "WindowsClient"         // Whether client OS is Windows or not
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
