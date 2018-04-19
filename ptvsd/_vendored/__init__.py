import contextlib
from importlib import import_module
import os
import os.path
import sys


VENDORED_ROOT = os.path.dirname(__file__)
# TODO: Move the "pydevd" git submodule to the ptvsd/_vendored directory
# and then drop the following fallback.
if 'pydevd' not in os.listdir(VENDORED_ROOT):
    VENDORED_ROOT = os.path.dirname(os.path.dirname(__file__))


def project_root(project):
    """Return the path the root dir of the vendored project."""
    return os.path.join(VENDORED_ROOT, project)


def prefix_matcher(*prefixes):
    """Return a module match func that matches any of the given prefixes."""
    assert prefixes

    def match(name, module):
        for prefix in prefixes:
            if name.startswith(prefix):
                return True
        else:
            return False
    return match


def check_modules(project, match, root=None):
    """Verify that only vendored modules have been imported."""
    if root is None:
        root = project_root(project)
    extensions = []
    unvendored = {}
    for modname, mod in sys.modules.items():
        if not match(modname, mod):
            continue
        if not hasattr(mod, '__file__'):  # extension module
            extensions.append(modname)
        elif not mod.__file__.startswith(root):
            unvendored[modname] = mod.__file__
    return unvendored, extensions


@contextlib.contextmanager
def vendored(project, root=None):
    """A context manager under which the vendored project will be imported."""
    if root is None:
        root = project_root(project)
    # Add the vendored project directory, so that it gets tried first.
    sys.path.insert(0, root)
    try:
        yield root
    finally:
        #del sys.path[0]
        sys.path.remove(root)


def preimport(project, modules, **kwargs):
    """Import each of the named modules out of the vendored project."""
    with vendored(project, **kwargs):
        for name in modules:
            import_module(name)
