# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys

# Force absolute path on Python 2.
__file__ = os.path.abspath(__file__)


if __name__ == "__main__":
    # ptvsd can also be invoked directly rather than via -m. In this case, the first
    # entry on sys.path is the one added automatically by Python for the directory
    # containing this file. This means that import ptvsd will not work, since we need
    # the parent directory of ptvsd/ to be in sys.path, rather than ptvsd/ itself.
    #
    # The other issue is that many other absolute imports will break, because they
    # will be resolved relative to ptvsd/ - e.g. `import debugger` will then try
    # to import ptvsd/debugger.py.
    #
    # To fix both, we need to replace the automatically added entry such that it points
    # at parent directory of ptvsd/ instead of ptvsd/ itself, import ptvsd with that
    # in sys.path, and then remove the first entry entry altogether, so that it doesn't
    # affect any further imports we might do. For example, suppose the user did:
    #
    #   python /foo/bar/ptvsd ...
    #
    # At the beginning of this script, sys.path will contain "/foo/bar/ptvsd" as the
    # first entry. What we want is to replace it with "/foo/bar', then import ptvsd
    # with that in effect, and then remove the replaced entry before any more
    # code runs. The imported ptvsd module will remain in sys.modules, and thus all
    # future imports of it or its submodules will resolve accordingly.
    if "ptvsd" not in sys.modules:
        # Do not use dirname() to walk up - this can be a relative path, e.g. ".".
        sys.path[0] = sys.path[0] + "/../"
        import ptvsd  # noqa

        del sys.path[0]

    from ptvsd.server import cli

    cli.main()
