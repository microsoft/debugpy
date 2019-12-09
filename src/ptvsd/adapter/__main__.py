# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import argparse
import atexit
import codecs
import json
import locale
import os
import sys

# WARNING: ptvsd and submodules must not be imported on top level in this module,
# and should be imported locally inside main() instead.

# Force absolute path on Python 2.
__file__ = os.path.abspath(__file__)


def main(args):
    from ptvsd import adapter
    from ptvsd.common import compat, log
    from ptvsd.adapter import ide, servers, sessions

    if args.log_stderr:
        log.stderr.levels |= set(log.LEVELS)
    if args.log_dir is not None:
        log.log_dir = args.log_dir

    log.to_file(prefix="ptvsd.adapter")
    log.describe_environment("ptvsd.adapter startup environment:")

    if args.for_server and args.port is None:
        log.error("--for-server requires --port")
        sys.exit(64)

    servers.access_token = args.server_access_token
    if not args.for_server:
        adapter.access_token = compat.force_str(
            codecs.encode(os.urandom(32), "hex")
        )

    server_host, server_port = servers.listen()
    ide_host, ide_port = ide.listen(port=args.port)
    endpoints_info = {
        "ide": {"host": ide_host, "port": ide_port},
        "server": {"host": server_host, "port": server_port},
    }

    if args.for_server:
        log.info("Writing endpoints info to stdout:\n{0!r}", endpoints_info)
        print(json.dumps(endpoints_info))
        sys.stdout.flush()

    if args.port is None:
        ide.IDE("stdio")

    listener_file = os.getenv("PTVSD_ADAPTER_ENDPOINTS")
    if listener_file is not None:
        log.info(
            "Writing endpoints info to {0!r}:\n{1!r}", listener_file, endpoints_info
        )

        def delete_listener_file():
            log.info("Listener ports closed; deleting {0!r}", listener_file)
            try:
                os.remove(listener_file)
            except Exception:
                log.exception("Failed to delete {0!r}", listener_file, level="warning")

        with open(listener_file, "w") as f:
            atexit.register(delete_listener_file)
            print(json.dumps(endpoints_info), file=f)

    # These must be registered after the one above, to ensure that the listener sockets
    # are closed before the endpoint info file is deleted - this way, another process
    # can wait for the file to go away as a signal that the ports are no longer in use.
    atexit.register(servers.stop_listening)
    atexit.register(ide.stop_listening)

    servers.wait_until_disconnected()
    log.info("All debug servers disconnected; waiting for remaining sessions...")

    sessions.wait_until_ended()
    log.info("All debug sessions have ended; exiting.")


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
        "--server-access-token", type=str, help="access token expected by the server"
    )

    parser.add_argument("--for-server", action="store_true", help=argparse.SUPPRESS)

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
