PyDev.Debugger
==============

The sources for the PyDev.Debugger may be seen at:

https://github.com/fabioz/PyDev.Debugger

In general, the debugger backend should **NOT** be installed separately if you're using an IDE which already
bundles it (such as PyDev, PyCharm or bundled through debugpy, which is the debug adapter used in 
VSCode Python and Visual Studio Python).

It is however available in PyPi so that it can be installed for doing remote debugging with `pip` -- so, when
debugging a process which runs in another machine, it's possible to `pip install pydevd` and in the code use
`pydevd.settrace(host='10.1.1.1')` to connect the debugger backend to the debugger UI running in the IDE
(whereas previously the sources had to be manually copied from the IDE installation).

It should be compatible with Python 2.7 onwards (as well as Jython 2.7, IronPython and PyPy -- and
any other variant which properly supports the Python structure for debuggers -- i.e.: sys.settrace/threading.settrace).

Recent versions contain speedup modules using Cython, which are generated with a few changes in the regular files
to `cythonize` the files. To update and compile the cython sources (and generate some other auto-generated files),
`build_tools/build.py` should be run -- note that the resulting .pyx and .c files should be commited.

To generate a distribution with the precompiled binaries for the IDE, `build_binaries_windows.py` should be run (
note that the environments must be pre-created as specified in that file).

To generate a distribution to upload to PyPi, `python setup.py sdist bdist_wheel` should be run for each python version
which should have a wheel and afterwards `twine upload -s dist/pydevd-*` should be run to actually upload the contents
to PyPi.

GitHub Actions (CI):

.. |github_actions| https://github.com/fabioz/PyDev.Debugger/workflows/PyDev.Debugger Tests/badge.svg
  :target: https://github.com/fabioz/PyDev.Debugger/workflows/PyDev.Debugger Tests/badge.svg

|github_actions|

