# Troubleshooting

If you're having trouble with debugpy, check below for information which may help. If something isn't covered here, please file an issue with the information given in [Filing an issue](#filing-an-issue).

## Known Issues

There are a few known issues in the current version of the debugger:

### Breakpoints not set
If you receive an error saying **breakpoint not set**, then look at your path mappings in `launch.json`. See Meta-Issue [#2976](https://github.com/Microsoft/vscode-python/issues/2976) for more details. 

### Debugging Library Files
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

### Debugger breaks on SystemExit
By default, the debugger treats `SystemExit` with a non-zero exit code as an uncaught exception and breaks on it. If you use `sys.exit()` intentionally (e.g. in CLI tools, test runners like pytest, or frameworks like Django/Flask), this can be unwanted.

You can control exactly which `SystemExit` codes the debugger breaks on using the `breakOnSystemExit` setting in `launch.json`. It accepts an array of exit codes and/or ranges:

```js
// Never break on any SystemExit:
    {
        "breakOnSystemExit": []
    }

// Only break on specific exit codes:
{
    "breakOnSystemExit": [1, 2]
}

// Break on exit codes using ranges (inclusive):
{
    "breakOnSystemExit": [{"from": 1, "to": 255}]
}

// Mix specific codes and ranges:
{
    "breakOnSystemExit": [0, {"from": 3, "to": 100}]
}
```

When `breakOnSystemExit` is not specified, the default behavior applies:
- `SystemExit(0)` and `SystemExit(None)` are ignored (successful exit).
- All other non-zero exit codes cause a break.
- When **`django`** or **`flask`** is `true`, exit code `3` is also ignored (used for reload signaling).
- When **`breakOnSystemExitZero`** is `true`, the debugger also breaks on `SystemExit(0)` and `SystemExit(None)`.

When `breakOnSystemExit` is explicitly set, it overrides all of the above — only the listed codes and ranges will cause breaks.

## Filing an issue

When filing an issue, make sure you do the following:

- Check existing issues for the same problem (also see the "Known Issues" section above for widespread problems).
- Follow instructions in [this](https://github.com/microsoft/debugpy/blob/main/.github/ISSUE_TEMPLATE/bug_report.md) template for filing a bug report.
- Include any debugger logs that you may have. See [here](https://github.com/microsoft/debugpy#debugger-logging) for instructions on how to enable logging.
