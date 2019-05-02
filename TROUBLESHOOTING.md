# Troubleshooting

If you're having trouble with the Debugger package for Visual Studio and VS Code, check below for information which
may help. If something isn't covered here, please file an issue with the information given
in [Filing an issue](#filing-an-issue).

## Known Issues

There are a few known issues in the current version of the debugger:
### 1. Multiprocessing on Linux/Mac
 Multiprocess debugging on a Linux machine requires the `spawn` setting. We are working on improving this experience, see [#943](https://github.com/Microsoft/ptvsd/issues/943). Meanwhile do this to improve your debugging experience:
```py
import multiprocessing
multiprocessing.set_start_method('spawn', True)
```
Note: On Windows, the `multiprocessing` package uses "spawn" as the default and only option, so it is recommended for cross-platform code to ensure uniform behavior. If you choose to use `spawn` you may have to structure your `__main__` module like this https://docs.python.org/3/library/multiprocessing.html#the-spawn-and-forkserver-start-methods.

### 2. Breakpoints not set
If you receive an error saying **breakpoint not set**, then look at your path mappings in `launch.json`. See Meta-Issue [#2976](https://github.com/Microsoft/vscode-python/issues/2976) for more details. 

### 3. Debugging Library Files
If you want to debug library files, you have to disable `justMyCode` in `launch.json`. Previously this setting was `debugStdLib`. For example:
```js
{
    "name": "Terminal",
    "type": "python",
    "request": "launch",
    "pythonPath": "${config:python.pythonPath}",
    "program": "${file}",
    "console": "integratedTerminal",
    "justMyCode": false
},
```

## Filing an issue

When filing an issue, make sure you do the following:

- Check existing issues for the same problem (also see the "Known Issues" section above for widespread problems).
- Follow instructions in [this](https://github.com/Microsoft/ptvsd/blob/master/.github/ISSUE_TEMPLATE/bug_report.md) template for filing a bug report.
- Include any debugger logs that you may have. See [here](https://github.com/Microsoft/ptvsd#debugger-logging) for instructions on how to enable logging.
