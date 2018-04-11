import os
import os.path
import shutil
import sys
import tempfile
from textwrap import dedent

from .lock import Lockfile


# Warning: We use an "internal" stdlib function here.  While the
# risk of breakage is low, it is possible...
_NAMES = tempfile._get_candidate_names()


def _random_name(prefix='', suffix=''):
    # We do not expect to ever hit StopIteration here.
    name = next(_NAMES)
    return prefix + name + suffix


def _touch(filename):
    with open(filename, 'w'):
        pass


class Workspace(object):
    """File operations relative to some root directory ("workspace")."""

    PREFIX = 'workspace-'

    @classmethod
    def _new_root(cls):
        return tempfile.mkdtemp(prefix=cls.PREFIX)

    def __init__(self, root=None):
        if root is not None:
            self._root = root
        self._owned = False

    @property
    def root(self):
        try:
            return self._root
        except AttributeError:
            self._root = self._new_root()
            self._owned = True
            return self._root

    def cleanup(self):
        """Release and destroy the workspace."""
        if self._owned:
            shutil.rmtree(self._root)
            self._owned = False
            self._root = None

    def resolve(self, *path):
        """Return the absolute path (relative to the workspace)."""
        return os.path.join(self.root, *path)

    def random(self, *dirpath, **kwargs):
        """Return a random filename resolved to the given directory."""
        dirname = self.resolve(*dirpath)
        name = _random_name(**kwargs)
        return os.path.join(dirname, name)

    def ensure_dir(self, *dirpath, **kwargs):
        dirname = self.resolve(*dirpath)
        if not os.path.exists(dirname):
            os.makedirs(dirname, **kwargs)
        return dirname

    def write(self, *path, **kwargs):
        return self._write(path, **kwargs)

    def write_script(self, *path, **kwargs):
        return self._write_script(path, **kwargs)

    def write_python_script(self, *path, **kwargs):
        return self._write_script(path, executable=sys.executable, **kwargs)

    def lockfile(self, filename=None):
        """Return a lockfile in the workspace."""
        filename = self._resolve_lock(filename)
        return Lockfile(filename)

    # internal methods

    def _write(self, path, content='', fixup=True):
        if fixup:
            content = dedent(content)
        filename = self.resolve(*path)
        with open(filename, 'w') as outfile:
            outfile.write(content)
        return filename

    def _write_script(self, path, executable, mode='0755', content='',
                      fixup=True):
        if isinstance(mode, str):
            mode = int(mode, base=8)
        if fixup:
            content = dedent(content)
        content = '#!/usr/bin/env {}\n'.format(executable) + content
        filename = self._write(path, content, fixup=False)
        os.chmod(filename, mode)
        return filename

    def _get_locksdir(self):
        try:
            return self._locksdir
        except AttributeError:
            self._locksdir = '.locks'
            self.ensure_dir(self._locksdir)
            return self._locksdir

    def _resolve_lock(self, name=None):
        if not name:
            name = _random_name(suffix='.lock')
        return self.resolve(self._get_locksdir(), name)


class PathEntry(Workspace):

    def __init__(self, root=None):
        super(PathEntry, self).__init__(root)
        self._syspath = None

    def cleanup(self):
        self.uninstall()
        super(PathEntry, self).cleanup()

    def install(self):
        if self._syspath is not None:
            return
        if sys.path[0] in ('', '.'):
            self._syspath = 1
        else:
            self._syspath = 0
        sys.path.insert(self._syspath, self.root)

    def uninstall(self):
        if self._syspath is None:
            return
        del sys.path[self._syspath]
        self._syspath = None

    def resolve_module(self, name):
        parts = (name + '.py').split('.')
        return self.resolve(*parts)

    def write_module(self, name, content=''):
        parent, sep, name = name.rpartition('.')
        filename = name + '.py'
        if sep:
            dirname = self._ensure_package(parent)
            filename = os.path.join(dirname, filename)
        return self.write(filename, content=content)

    # internal methods

    def _ensure_package(self, name, root=None):
        parent, sep, name = name.rpartition('.')
        if sep:
            dirname = self._ensure_package(parent, root)
        else:
            if root is None:
                root = self.root
            dirname = root
        dirname = os.path.join(dirname, name)

        initpy = os.path.join(dirname, '__init__.py')
        if not os.path.exists(initpy):
            os.mkdirs(dirname)
            with open(initpy, 'w'):
                pass

        return dirname
