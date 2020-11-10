# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import collections
import os


class DebugConfig(collections.MutableMapping):
    """Debug configuration for a session. Corresponds to bodies of DAP "launch" and
    "attach" requests, or launch.json in VSCode.

    It is a dict-like object that only allows keys that are valid debug configuration
    properties for debugpy. When a property is queried, but it's not explicitly set in
    the config, the default value (i.e. what debugpy will assume the property is set to)
    is returned.

    In addition, it exposes high-level wrappers over "env" and "debugOptions".
    """

    __slots__ = ["_dict", "_env", "_debug_options"]

    # Valid configuration properties. Keys are names, and values are defaults that
    # are assumed by the adapter and/or the server if the property is not specified.
    # If the property is required, or if the default is computed in such a way that
    # it cannot be predicted, the value is ().
    PROPERTIES = {
        # Common
        "breakOnSystemExitZero": False,
        "debugOptions": [],
        "django": False,
        "jinja": False,
        "justMyCode": False,
        "flask": False,
        "logToFile": False,
        "maxExceptionStackFrames": (),
        "name": (),
        "noDebug": False,
        "pathMappings": [],
        "postDebugTask": (),
        "preLaunchTask": (),
        "pyramid": False,
        "redirectOutput": False,
        "rules": [],
        "showReturnValue": True,
        "steppingResumesAllThreads": True,
        "subProcess": False,
        "successExitCodes": [0],
        "type": (),
        # Launch
        "args": [],
        "argsExpansion": "shell",
        "code": (),
        "console": "internal",
        "cwd": (),
        "debugLauncherPython": (),
        "env": {},
        "gevent": False,
        "internalConsoleOptions": "neverOpen",
        "module": (),
        "program": (),
        "python": (),
        "pythonArgs": [],
        "pythonPath": (),
        "stopOnEntry": False,
        "sudo": False,
        "waitOnNormalExit": False,
        "waitOnAbnormalExit": False,
        # Attach by socket
        "listen": (),
        "connect": (),
        # Attach by PID
        "processId": (),
        "variablePresentation": {
            "special": "group",
            "function": "group",
            "class_": "group",
            "protected": "inline",
        },
    }

    def __init__(self, *args, **kwargs):
        self._dict = dict(*args, **kwargs)
        self._env = self.Env(self)
        self._debug_options = self.DebugOptions(self)

    def __iter__(self):
        return iter(self._dict)

    def __len__(self):
        return len(self._dict)

    def __contains__(self, key):
        return key in self._dict

    def __getitem__(self, key):
        try:
            return self._dict[key]
        except KeyError:
            try:
                value = self.PROPERTIES[key]
            except KeyError:
                pass
            else:
                if value != ():
                    return value
            raise

    def __delitem__(self, key):
        del self._dict[key]

    def __setitem__(self, key, value):
        assert key in self.PROPERTIES
        self._dict[key] = value

    def __getstate__(self):
        return dict(self)

    def setdefault(self, key, default=None):
        if key not in self:
            self[key] = default
        return self[key]

    def setdefaults(self, defaults):
        """Like setdefault(), but sets multiple default values at once.
        """
        for k, v in defaults.items():
            self.setdefault(k, v)

    def normalize(self):
        """Normalizes the debug configuration by adding any derived properties, in
        the manner similar to what VSCode does to launch.json before submitting it
        to the adapter.
        """

        if self["showReturnValue"]:
            self.debug_options.add("ShowReturnValue")

        if self["redirectOutput"]:
            self.debug_options.add("RedirectOutput")

        if not self["justMyCode"]:
            self.debug_options.add("DebugStdLib")

        if self["django"]:
            self.debug_options.add("Django")

        if self["jinja"]:
            self.debug_options.add("Jinja")

        if self["flask"]:
            self.debug_options.add("Flask")

        if self["pyramid"]:
            self.debug_options.add("Pyramid")

        if self["subProcess"]:
            self.debug_options.add("Multiprocess")

        if self["breakOnSystemExitZero"]:
            self.debug_options.add("BreakOnSystemExitZero")

        if self["stopOnEntry"]:
            self.debug_options.add("StopOnEntry")

        if self["waitOnNormalExit"]:
            self.debug_options.add("WaitOnNormalExit")

        if self["waitOnAbnormalExit"]:
            self.debug_options.add("WaitOnAbnormalExit")

    @property
    def env(self):
        return self._env

    @property
    def debug_options(self):
        return self._debug_options

    class Env(collections.MutableMapping):
        """Wraps config["env"], automatically creating and destroying it as needed.
        """

        def __init__(self, config):
            self.config = config

        def __iter__(self):
            return iter(self.config["env"])

        def __len__(self):
            return len(self.config["env"])

        def __getitem__(self, key):
            return self.config["env"][key]

        def __delitem__(self, key):
            env = self.config.get("env", {})
            del env[key]
            if not len(env):
                del self.config["env"]

        def __setitem__(self, key, value):
            self.config.setdefault("env", {})[key] = value

        def __getstate__(self):
            return dict(self)

        def prepend_to(self, key, entry):
            """Prepends a new entry to a PATH-style environment variable, creating
            it if it doesn't exist already.
            """
            try:
                tail = os.path.pathsep + self[key]
            except KeyError:
                tail = ""
            self[key] = entry + tail

    class DebugOptions(collections.MutableSet):
        """Wraps config["debugOptions"], automatically creating and destroying it as
        needed, and providing set operations for it.
        """

        def __init__(self, config):
            self.config = config

        def __iter__(self):
            return iter(self.config["debugOptions"])

        def __len__(self):
            return len(self.config["env"])

        def __contains__(self, key):
            return key in self.config["debugOptions"]

        def add(self, key):
            opts = self.config.setdefault("debugOptions", [])
            if key not in opts:
                opts.append(key)

        def discard(self, key):
            opts = self.config.get("debugOptions", [])
            opts[:] = [x for x in opts if x != key]
