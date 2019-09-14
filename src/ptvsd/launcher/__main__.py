# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

__all__ = ["main"]

import locale
import os
import sys

# WARNING: ptvsd and submodules must not be imported on top level in this module,
# and should be imported locally inside main() instead.

# Force absolute path on Python 2.
__file__ = os.path.abspath(__file__)


def main():
    from ptvsd.common import log
    from ptvsd.launcher import adapter, debuggee

    log.to_file(prefix="ptvsd.launcher")
    log.describe_environment("ptvsd.launcher startup environment:")

    def option(name, type, *args):
        try:
            return type(os.environ.pop(name, *args))
        except Exception:
            raise log.exception("Error parsing {0!r}:", name)

    session_id = option("PTVSD_SESSION_ID", int)
    launcher_port = option("PTVSD_LAUNCHER_PORT", int)

    adapter.connect(session_id, launcher_port)
    adapter.channel.wait()

    if debuggee.process is not None:
        sys.exit(debuggee.process.returncode)


if __name__ == "__main__":
    # ptvsd can also be invoked directly rather than via -m. In this case, the first
    # entry on sys.path is the one added automatically by Python for the directory
    # containing this file. This means that import ptvsd will not work, since we need
    # the parent directory of ptvsd/ to be in sys.path, rather than ptvsd/launcher/.
    #
    # The other issue is that many other absolute imports will break, because they
    # will be resolved relative to ptvsd/launcher/ - e.g. `import state` will then try
    # to import ptvsd/launcher/state.py.
    #
    # To fix both, we need to replace the automatically added entry such that it points
    # at parent directory of ptvsd/ instead of ptvsd/launcher, import ptvsd with that
    # in sys.path, and then remove the first entry entry altogether, so that it doesn't
    # affect any further imports we might do. For example, suppose the user did:
    #
    #   python /foo/bar/ptvsd/launcher ...
    #
    # At the beginning of this script, sys.path will contain "/foo/bar/ptvsd/launcher"
    # as the first entry. What we want is to replace it with "/foo/bar', then import
    # ptvsd with that in effect, and then remove the replaced entry before any more
    # code runs. The imported ptvsd module will remain in sys.modules, and thus all
    # future imports of it or its submodules will resolve accordingly.
    if "ptvsd" not in sys.modules:
        # Do not use dirname() to walk up - this can be a relative path, e.g. ".".
        sys.path[0] = sys.path[0] + "/../../"
        __import__("ptvsd")
        del sys.path[0]

    # Load locale settings.
    locale.setlocale(locale.LC_ALL, "")

    main()
