import argparse
import os.path
import sys

from . import (UPSTREAM, VENDORED, METADATA,
               upstream)
from ._util import open_url


COMMANDS = {}


def as_command(name):
    def decorator(f):
        COMMANDS[name] = f
        return f
    return decorator


@as_command('download')
def handle_download(source=UPSTREAM, target=VENDORED):
    # Download the schema file.
    with open_url(source) as infile:
        with open(target, 'wb') as outfile:
            meta = upstream.download(source, infile, outfile)

    # Save the metadata.
    filename = os.path.join(os.path.dirname(target),
                            os.path.basename(METADATA))
    with open(filename, 'w') as metafile:
        metafile.write(
                meta.format())


#############################
# the script

def parse_args(argv=sys.argv[1:], prog=None):
    if prog is None:
        if __name__ == '__main__':
            module = __spec__.name
            pkg, _, mod = module.rpartition('.')
            if not pkg:
                module = mod
            elif mod == '__main__':
                module = pkg
            prog = 'python3 -m {}'.format(module)
        else:
            prog = sys.argv[0]

    parser = argparse.ArgumentParser(
            prog=prog,
            description='Manage the vendored VSC debugger protocol schema.',
            )
    subs = parser.add_subparsers(dest='command')

    download = subs.add_parser('download')
    download.add_argument('--source', default=UPSTREAM)
    download.add_argument('--target', default=VENDORED)

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        parser.exit()
    return args


def main(command, **kwargs):
    handle_command = COMMANDS[command]
    return handle_command(**kwargs)


if __name__ == '__main__':
    args = parse_args()
    main(**(vars(args)))
