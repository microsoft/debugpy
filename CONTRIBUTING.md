# Contributing to `debugpy`

[![Build Status](https://dev.azure.com/debugpy/debugpy/_apis/build/status/debugpy-test-automation?branchName=main)](https://dev.azure.com/debugpy/debugpy/_build/latest?definitionId=1&branchName=main)
[![GitHub](https://img.shields.io/badge/license-MIT-brightgreen.svg)](https://raw.githubusercontent.com/microsoft/debugpy/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/ptvsd.svg)](https://pypi.org/project/ptvsd/)


## Contributing a pull request
This project welcomes contributions and suggestions. Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit https://cla.microsoft.com.

When you submit a pull request, a CLA-bot will automatically determine whether you need to provide
a CLA and decorate the PR appropriately (e.g., label, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.

## Development tools

The following tools are required to work on debugpy:

- At least one version of [Python 3](https://www.python.org/downloads/)
- [Python 2.7](https://www.python.org/downloads/release/python-2717/) (to run tests)
- [Flake8](http://flake8.pycqa.org/en/stable/)
- [Black](https://black.readthedocs.io/en/stable/)
- [tox](https://tox.readthedocs.io/en/latest/)

We recommend using [Visual Studio Code](https://code.visualstudio.com/) with the (Python extension)[https://marketplace.visualstudio.com/items?itemName=ms-python.python] to work on debugpy, but it's not a requirement. A workspace file, [debugpy.code-workspace], is provided for the convenience of VSCode users, and sets it up to use the other tools listed above properly.

Tools that are Python packages should be installed via pip corresponding to the Python 3 installation. On Windows:
```
...> py -m pip install black flake8 tox
```
On Linux or macOS:
```
...$ python3 -m pip install black flake8 tox
```

## Linting
We use Flake8 for linting. It should be run from the root of the repository, where [.flake8](.flake8) with project-specific linting settings is located. On Windows:
```
...\debugpy> py -m flake8
```
On Linux or macOS:
```
.../debugpy$ python3 -m flake8
```

## Formatting
We use Black for formatting. All new code files, and all code files that were edited, should be reformatted before submitting a PR. On Windows:
```
...\debugpy> py -m black
```
On Linux or macOS:
```
.../debugpy$ python3 -m black
```

## Running tests

We use tox to run tests in an isolated environment. This ensures that debugpy is first built as a package, and tox also takes care of installing all the test prerequisites into the environment. On Windows:
```
...\debugpy> py -m tox
```
On Linux or macOS:
```
.../debugpy$ python3 -m tox
```
This will perform a full run with the default settings. A full run will run tests on Python 2.7 and 3.5-3.8, and requires all of those to be installed. If some versions are missing, or it is desired to skip them for a particular run, tox can be directed to only run tests on specific versions with `-e`. In addition, the `--develop` option can be used to skip the packaging step, running tests directly against the source code in `src/debugpy`. This should only be used when iterating on the code, and a proper run should be performed before submitting a PR. On Windows:
```
...\debugpy> py -m tox -e py27,py37 --develop
```
On Linux or macOS:
```
.../debugpy$ python3 -m tox -e py27,py37 --develop
```

You can run all tests in a single file using a specified python version, like this:
```
...\debugpy> py -m tox --develop -e py312 -- ".\tests\debugpy\server\test_cli.py"
```

You can also specify a single test, like this:
```
...\debugpy> py -m tox --develop -e py312 -- ".\tests\debugpy\server\test_cli.py::test_duplicate_switch"
```

The tests are run concurrently, and the default number of workers is 8. You can force a single worker by using the `-n0` flag, like this:
```
...\debugpy> py -m tox --develop -e py312 -- -n0 ".\tests\debugpy\server\test_cli.py"
```

### Running tests without tox

While tox is the recommended way to run the test suite, pytest can also be invoked directly from the root of the repository. This requires packages in tests/requirements.txt to be installed first.

#### Keeping logs on test success

There's an internal setting `debugpy_log_passed` that if set to true will not erase the logs after a successful test run. Just search for this in the code and remove the code that deletes the logs on success.

#### Adding logging

Using `pydevd_log.debug` you can add logging just about anywhere in the pydevd code. However this code won't be called if CYTHON support is enabled without recreating the Cython output. To temporarily disable CYTHON support, look for `CYTHON_SUPPORTED` and make sure it's set to False

## Updating pydevd

Pydevd (at src/debugpy/_vendored/pydevd) is a subrepo of https://github.com/fabioz/PyDev.Debugger. We use the [subrepo](https://github.com/ingydotnet/git-subrepo) to have a copy of pydevd inside of debugpy

In order to update the source, you would:
- git checkout -b "branch name"
- python subrepo.py pull
- git push
- Fix any debugpy tests that are failing as a result of the pull
- Create a PR from your branch

You might need to regenerate the Cython modules after any changes. This can be done by:

- Install Python latest (3.14 as of this writing)
- pip install cython 'django>=1.9' 'setuptools>=0.9' 'wheel>0.21' twine
- On a windows machine:
  - set FORCE_PYDEVD_VC_VARS=C:\Program Files (x86)\Microsoft Visual Studio\2017\BuildTools\VC\Auxiliary\Build\vcvars64.bat
  - in the pydevd folder: python .\build_tools\build.py

## Pushing pydevd back to PyDev.Debugger

If you've made changes to pydevd (at src/debugpy/_vendored/pydevd), you'll want to push back changes to pydevd so as Fabio makes changes to pydevd we can continue to share updates.

To do this, you would:

- Create a fork of https://github.com/fabioz/PyDev.Debugger
- Switch back to your debugpy clone
- python subrepo.py branch -m "pydevd branch you want to create"
- git push -f https://github.com/"your fork"/PyDev.Debugger subrepo/src/debugpy/_vendored/pydevd:$(pydevd branch you want to create)
- Create a PR from that branch
- Get Fabio's buyoff on the changes

### Setting up pydevd to be testable

Follow these steps to get pydevd testable:

- create an environment to test. The list of stuff in your environment is outlined [here](https://github.com/fabioz/PyDev.Debugger/blob/6cd4d431e6a794448f33a73857d479149041500a/.github/workflows/pydevd-tests-python.yml#L83).
- set PYTHONPATH=. (make sure you don't forget this part, otherwise a lot of tests will fail)

### Testing pydevd and fixing test failures

Pydevd has a lot more tests on execution than debugpy. They reside in all of the `test` folders under the root. The majority of the execution tests are in the `tests_python` folder.

You run all of the tests with (from the root folder):

- python -m pytest -n auto -rfE

That will run all of the tests in parallel and output any failures.

If you want to just see failures you can do this:

- python -m pytest -n auto -q

That should generate output that just lists the tests which failed.

```
=============================================== short test summary info ===============================================
FAILED tests_python/test_debugger.py::test_path_translation[True] - AssertionError: TimeoutError (note: error trying to dump threads on timeout).
FAILED tests_python/test_debugger.py::test_remote_debugger_multi_proc[False] - AssertionError: TimeoutError
FAILED tests_python/test_debugger.py::test_path_translation[False] - AssertionError: TimeoutError (note: error trying to dump threads on timeout).
======================== 3 failed, 661 passed, 169 skipped, 77 warnings in 319.05s (0:05:19) =========================
```
With that you can then run individual tests like so:

- python -m pytest -n auto tests_python/test_debugger.py::test_path_translation[False]

That will generate a log from the test run.

Logging the test output can be tricky so here's some information on how to debug the tests.

#### Running pydevd tests inside of VS code

You can also run the pydevd tests inside of VS code using the test explorer (and debug the pytest code). To do so, set PYTHONPATH=. and open the `src/debugpy/_vendored/pydevd` folder in VS code. The test explorer should find all of the pydevd tests.

#### How to add more logging

The pydevd tests log everything to the console and to a text file during the test. If you scroll up in the console, it should show the log file it read the logs from:

```
Log on failure:
-------------------- C:\Users\rchiodo\AppData\Local\Temp\pytest-of-rchiodo\pytest-77\popen-gw3\test_path_translation_and_sour0\pydevd_debug_file_23524.32540.txt ------------------
```

If you want to add more logging in order to investigate something that isn't working, you simply add a line like so in the code:

```python
    pydevd_log.debug("Some test logging", frame, etc)
```

Make sure if you add this in a module that gets `cythonized`, that you turn off `Cython` support as listed above. Otherwise you'll have to regen the C code or you won't actually see your new log output.

#### How to use logs to debug failures

Investigating log failures can be done in multiple ways.

If you have an existing test failing, you can investigate it by running the test with the main branch and comparing the results. To do so you would:

- Clone the repo a second time
- Change the code in `tests_python/debugger_unittest.py` so that the test prints out logs on success too (by default it only logs the output on a failure)
- Run the failing test in the second clone
- Run the failing test in your original clone (with the --capture=tee-sys so that it outputs the log)
- Diff the results by finding the log file name in the output and diffing those two files
- Add more logging around where the differences first appear
- Repeat running and diffing

If you're adding a new test or just trying to figure out what the expected log output is, you would look at the failing test to see what steps are expected in the output. Here's an example:

```python
def test_case_double_remove_breakpoint(case_setup):
    with case_setup.test_file("_debugger_case_remove_breakpoint.py") as writer:
        breakpoint_id = writer.write_add_breakpoint(writer.get_line_index_with_content("break here"))
        writer.write_make_initial_run()

        hit = writer.wait_for_breakpoint_hit()
        writer.write_remove_breakpoint(breakpoint_id)
        writer.write_remove_breakpoint(breakpoint_id)  # Double-remove (just check that we don't have an error).
        writer.write_run_thread(hit.thread_id)

        writer.finished_ok = True
```

That test would have events correlating to:

- Initialization (all debug sessions have this)
- Setting breakpoints on a specific line
- Breakpoint event being hit
- Setting breakpoints to empty
- Setting breakpoints to empty
- Continue event

Those would show up in the log like so:

Breakpoint command
```
0.00s - Received command: CMD_SET_BREAK 111     3       1       python-line     C:\Users\rchiodo\source\repos\PyDev.Debugger\tests_python\resources\_debugger_case_remove_breakpoint.py 7       None    None    None
```

In order to investigate a failure you'd look for the CMDs you expect and then see where the CMDs deviate. At that point you'd add logging around what might have happened next.

## Using modified debugpy in Visual Studio Code
To test integration between debugpy and Visual Studio Code, the latter can be directed to use a custom version of debugpy in lieu of the one bundled with the Python extension. This is done by specifying `"debugAdapterPath"` in `launch.json` - it must point at the root directory of the *package*, which is `src/debugpy` inside the repository:

```json5
{
    "type": "python",
    "debugAdapterPath": ".../debugpy/src/debugpy/adapter",
    ...
}
```

## Enabling logging in VS code
See the directions here:
https://github.com/microsoft/debugpy/wiki/Enable-debugger-logs

## Debugging native code (Windows)

To debug the native components of `debugpy`, such as `attach.cpp`, you can use Visual Studio's native debugging feature.

Follow these steps to set up native debugging in Visual Studio:

1. Open Visual Studio and go to `Debug` > `Options` > `Symbols`.
2. Check the option **Search for all module symbols unless excluded**. This ensures that Visual Studio loads the necessary symbols (PDB files) for all modules, including dynamically loaded ones.
3. Click **OK** to close the options dialog.
4. Run your Python script from the command line, for example: `python ./main.py`
5. In Visual Studio, go to `Debug` > `Attach to Process`.
6. From the list of processes, select the appropriate Python process. Be sure to choose the correct process, especially if you're using a virtual environment. You can verify this by checking the command line associated with each process in the **Task Manager**.
7. Under **Attach to**, choose either **Automatic: Native code** or explicitly select **Native** to attach as a native debugger.
8. Click **Attach**.
9. Open the native source file you want to debug, such as `attach.cpp`, and set breakpoints where necessary (e.g., at `DoAttach`).
10. Trigger the loading of the DLL, such as by attaching `debugpy` to the Python process (refer to `Attach: PID` in `debugpy`'s `launch.json` for more details on attaching to the process).
11. Once the DLL is loaded, Visual Studio will automatically load the associated PDB files, and your breakpoints should become active.
12. When the breakpoint is hit, you can debug the native code as you would in any debug session.

If you need to step into the Python code during the debug session, you can download the Python source code from [python.org](https://www.python.org/downloads/source/). Unzip it to a folder, and when Visual Studio prompts for the source location, point it to the folder where you extracted the Python source. Ensure that the Python version matches the interpreter used to run your script (e.g., `python ./main.py`).