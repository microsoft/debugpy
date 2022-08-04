# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import py
import os

from debugpy.common import json
from tests.patterns import some


class Target(object):
    """Describes Python code that gets run by a Runner."""

    def __init__(self, filename, args=()):
        if filename is not None and not isinstance(filename, py.path.local):
            filename = py.path.local(filename)

        self.filename = filename
        self.args = args

        if self.filename is None:
            self.code = None
        else:
            with open(self.filename.strpath, "rb") as f:
                self.code = f.read().decode("utf-8")

    def configure(self, session):
        """Configures the session to execute this target.

        This should only modify session.config, but gets access to the entire session
        to retrieve information about it.
        """

        raise NotImplementedError

    def cli(self, env):
        """Provides the command line arguments, suitable for passing to python or
        python -m debugpy, to execute this target.

        Returns command line arguments as a list, e.g. ["-m", "module"].

        If any environment variables are needed to properly interpret the command
        line - e.g. PYTHONPATH - the implementation should send them in env.
        """
        raise NotImplementedError

    @property
    def argslist(self):
        args = self.args
        if isinstance(args, str):
            return [args]
        else:
            return list(args)

    @property
    def co_filename(self):
        """co_filename of code objects created at runtime from the source that this
        Target describes, assuming no path mapping.
        """
        assert (
            self.filename is not None
        ), "co_filename requires Target created from filename"
        return self.filename.strpath

    @property
    def source(self):
        """DAP "source" JSON for this Target."""
        return some.dap.source(py.path.local(self.co_filename))

    @property
    def lines(self):
        """Same as self.filename.lines, if it is valid - e.g. for @pyfile objects."""
        assert (
            self.filename is not None
        ), "lines() requires Target created from filename"
        return self.filename.lines


class Program(Target):
    """
    A Python script, executed directly.

    By default executes a program through its absolute path with:
        python /full/path/to/foo.py

    If made relative through make_relative(cwd), the cwd is set and the
    launch is made relative to it.

        i.e.:
        Given a path such as /full/path/to/foo.py
        if make_relative('/full/path') is called,
        the cwd becomes `/full/path` and the launch is made as:
            python to/foo.py
    """

    pytest_id = "program"

    def __init__(self, filename, args=()):
        super().__init__(filename, args)
        self._cwd = ""

    def make_relative(self, cwd):
        if not cwd.endswith(("/", "\\")):
            cwd += os.path.sep
        assert self.filename.strpath.lower().startswith(cwd.lower())
        self._cwd = cwd

    def _get_relative_program(self):
        assert self._cwd
        relative_filename = self.filename.strpath[len(self._cwd) :]
        assert not relative_filename.startswith(("/", "\\"))
        return relative_filename

    def __repr__(self):
        if self._cwd:
            return f"program (relative) {json.repr(self._cwd)} / {json.repr(self._get_relative_program())}"
        else:
            return f"program {json.repr(self.filename.strpath)}"

    def configure(self, session):
        if self._cwd:
            session.config["cwd"] = self._cwd
            session.config["program"] = self._get_relative_program()
        else:
            session.config["program"] = self.filename.strpath

        session.config["args"] = self.args

    def cli(self, env):
        if self._cwd:
            cli = [self._get_relative_program()]
        else:
            cli = [self.filename.strpath]
        cli += self.argslist
        return cli


class Module(Target):
    """A Python module, executed by name: python -m foo.bar

    If created from a filename, the module name is the name of the file, and the
    Target will automatically add a PYTHONPATH entry.
    """

    pytest_id = "module"

    def __init__(self, filename=None, name=None, args=()):
        assert (filename is None) ^ (name is None)
        super().__init__(filename, args)
        self.name = name if name is not None else self.filename.purebasename

    def __repr__(self):
        return f"module {self.name}"

    def configure(self, session):
        session.config["module"] = self.name
        session.config["args"] = self.args

    def cli(self, env):
        if self.filename is not None:
            env.prepend_to("PYTHONPATH", self.filename.dirname)
        return ["-m", self.name] + self.argslist


class Code(Target):
    """A snippet of Python code: python -c "print('foo')"

    If created from a filename, the code is the contents of the file.
    """

    pytest_id = "code"

    def __init__(self, filename=None, code=None, args=()):
        assert (filename is None) ^ (code is None)
        super().__init__(filename, args)
        if code is not None:
            self.code = code

    def __repr__(self):
        lines = self.code.split("\n")
        return f"code: {json.repr(lines)}"

    def configure(self, session):
        session.config["code"] = self.code
        session.config["args"] = self.args

    def cli(self, env):
        return ["-c", self.code] + self.argslist

    @property
    def co_filename(self):
        return "<string>"

    @property
    def source(self):
        """DAP "source" JSON for this Target."""
        return some.dap.source("<string>")


all_named = [Program, Module]
"""All targets that produce uniquely named code objects at runtime, and thus can
have breakpoints set in them.
"""

all_unnamed = [Code]
"""All targets that produce unnamed code objects at runtime, and thus cannot have
breakpoints set in them.
"""

all = all_named + all_unnamed
