from textwrap import dedent
import os
import os.path
import shutil
import sys
import tempfile


class Workspace(object):

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
        if self._owned:
            shutil.rmtree(self._root)
            self._owned = False
            self._root = None

    def resolve(self, *path):
        return os.path.join(self.root, *path)

    def write(self, *path, **kwargs):
        return self._write(path, **kwargs)

    def _write(self, path, content='', fixup=True):
        if fixup:
            content = dedent(content)
        filename = self.resolve(*path)
        with open(filename, 'w') as outfile:
            outfile.write(content)
        return filename


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
