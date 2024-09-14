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
This will perform a full run with the default settings. A full run will run tests on Python 2.7 and 3.5-3.8, and requires all of those to be installed. If some versions are missing, or it is desired to skip them for a particular run, tox can be directed to only run tests on specific versions with `-e`. In addition, the `--developer` option can be used to skip the packaging step, running tests directly against the source code in `src/debugpy`. This should only be used when iterating on the code, and a proper run should be performed before submitting a PR. On Windows:
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

Pydevd (at src/debugpy/_vendored/pydevd) is a copy of https://github.com/fabioz/PyDev.Debugger. We do not use a git submodule but instead just copy the source. 

In order to update the source, you would:
- Sync to the appropriate commit in a pydevd repo
- Diff this against the src/debugpy/_vendored/pydevd folder, being careful to not remove the edits made in the debugpy version
- Run our tests
- Make any fixes to get the tests to pass (see logging on how to debug)

You might need to regenerate the Cython modules after any changes. This can be done by:

- Install Python latest (3.12 as of this writing)
- pip install cython, django>=1.9, setuptools>=0.9, wheel>0.21, twine
- On a windows machine:
  - set FORCE_PYDEVD_VC_VARS=C:\Program Files (x86)\Microsoft Visual Studio\2017\BuildTools\VC\Auxiliary\Build\vcvars64.bat
  - set PYDEVD_FORCE_BUILD_ALL=True
  - in the pydevd folder: python .\build_tools\build.py

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
