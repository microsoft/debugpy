# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import argparse
import locale
import os
import sys

# WARNING: ptvsd and submodules must not be imported on top level in this module,
# and should be imported locally inside main() instead.

# Force absolute path on Python 2.
__file__ = os.path.abspath(__file__)


def main(args):
    from ptvsd.common import log, options as common_options
    from ptvsd.adapter import session, options as adapter_options

    if args.log_stderr:
        log.stderr_levels |= set(log.LEVELS)
        adapter_options.log_stderr = True
    if args.log_dir is not None:
        common_options.log_dir = args.log_dir

    log.to_file(prefix="ptvsd.adapter")
    log.describe_environment("ptvsd.adapter startup environment:")

    session = session.Session()
    if args.port is None:
        session.connect_to_ide()
    else:
        if args.for_server_on_port is not None:
            session.connect_to_server(("127.0.0.1", args.for_server_on_port))
        with session.accept_connection_from_ide((args.host, args.port)) as (_, port):
            if session.server:
                session.server.set_debugger_property({"adapterPort": port})
    session.wait_for_completion()


def _parse_argv(argv):
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--port",
        type=int,
        default=None,
        metavar="PORT",
        help="start the adapter in debugServer mode on the specified port",
    )

    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        metavar="HOST",
        help="start the adapter in debugServer mode on the specified host",
    )

    parser.add_argument(
        "--for-server-on-port",
        type=int,
        default=None,
        metavar="PORT",
        help=argparse.SUPPRESS
    )

    parser.add_argument(
        "--log-dir",
        type=str,
        metavar="DIR",
        help="enable logging and use DIR to save adapter logs",
    )

    parser.add_argument(
        "--log-stderr", action="store_true", help="enable logging to stderr"
    )

    args = parser.parse_args(argv[1:])
    if args.port is None and args.log_stderr:
        parser.error("--log-stderr can only be used with --port")
    return args


if __name__ == "__main__":
    # ptvsd can also be invoked directly rather than via -m. In this case, the first
    # entry on sys.path is the one added automatically by Python for the directory
    # containing this file. This means that import ptvsd will not work, since we need
    # the parent directory of ptvsd/ to be in sys.path, rather than ptvsd/adapter/.
    #
    # The other issue is that many other absolute imports will break, because they
    # will be resolved relative to ptvsd/adapter/ - e.g. `import state` will then try
    # to import ptvsd/adapter/state.py.
    #
    # To fix both, we need to replace the automatically added entry such that it points
    # at parent directory of ptvsd/ instead of ptvsd/adapter, import ptvsd with that
    # in sys.path, and then remove the first entry entry altogether, so that it doesn't
    # affect any further imports we might do. For example, suppose the user did:
    #
    #   python /foo/bar/ptvsd/adapter ...
    #
    # At the beginning of this script, sys.path will contain "/foo/bar/ptvsd/adapter"
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

    main(_parse_argv(sys.argv))
