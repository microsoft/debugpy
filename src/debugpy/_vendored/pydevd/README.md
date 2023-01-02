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

`pydevd` is compatible with Python 3.6 onwards.

For `Python 2` please keep using `pydevd 2.8.0`.

`pydevd` is tested both with CPython as well as PyPy.

Recent versions contain speedup modules using Cython, which are generated with a few changes in the regular files
to `cythonize` the files. To update and compile the cython sources (and generate some other auto-generated files),
`build_tools/build.py` should be run -- note that the resulting .pyx and .c files should be commited.
