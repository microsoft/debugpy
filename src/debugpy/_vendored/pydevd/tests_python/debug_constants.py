import os
import sys
import platform

TEST_CYTHON = os.getenv("PYDEVD_USE_CYTHON", None) == "YES"
PYDEVD_TEST_VM = os.getenv("PYDEVD_TEST_VM", None)

IS_PY36_OR_GREATER = sys.version_info[0:2] >= (3, 6)
IS_PY311_OR_GREATER = sys.version_info[0:2] >= (3, 11)
IS_PY311 = sys.version_info[0:2] == (3, 11)
IS_PY312 = sys.version_info[0:2] == (3, 12)
IS_CPYTHON = platform.python_implementation() == "CPython"
IS_PYPY = platform.python_implementation() == "PyPy"

TODO_PY312 = IS_PY312  # Code which needs to be fixed in 3.12 should use this constant.
TODO_PYPY = IS_PYPY  # Code which needs to be fixed in pypy.

IS_PY36 = False
if sys.version_info[0] == 3 and sys.version_info[1] == 6:
    IS_PY36 = True

TEST_DJANGO = False
TEST_FLASK = False
TEST_CHERRYPY = False
TEST_GEVENT = False

try:
    import django

    TEST_DJANGO = True
except:
    pass

try:
    import flask

    TEST_FLASK = True
except:
    pass

try:
    import cherrypy

    TEST_CHERRYPY = True
except:
    pass

try:
    import gevent

    TEST_GEVENT = True
except:
    pass
