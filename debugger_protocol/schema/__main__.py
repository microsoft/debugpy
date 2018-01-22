import argparse
import sys

from ._util import open_url
from .metadata import open_metadata
from .upstream import URL as UPSTREAM, download
from .vendored import FILENAME as VENDORED, check_local, check_upstream


COMMANDS = {}


def as_command(name):
    def decorator(f):
        COMMANDS[name] = f
        return f
    return decorator


@as_command('download')
def handle_download(source=UPSTREAM, target=VENDORED, *,
                    _open=open, _open_url=open_url):
    # Download the schema file.
    print('downloading the schema file from {}...'.format(source))
    with _open_url(source) as infile:
        with _open(target, 'wb') as outfile:
            meta = download(source, infile, outfile,
                            _open_url=_open_url)
    print('...schema file written to {}.'.format(target))

    # Save the metadata.
    print('saving the schema metadata...')
    formatted = meta.format()
    metafile, filename = open_metadata(target, 'w',
                                       _open=_open)
    with metafile:
        metafile.write(formatted)
    print('...metadata written to {}.'.format(filename))


@as_command('check')
def handle_check(schemafile=VENDORED, upstream=None, *,
                 _open=open, _open_url=open_url):
    print('checking local schema file...')
    try:
        check_local(schemafile,
                    _open=_open)
    except Exception as exc:
        sys.exit('ERROR: {}'.format(exc))
    print('comparing with upstream schema file...')
    try:
        check_upstream(schemafile, url=upstream,
                       _open=_open, _open_url=_open_url)
    except Exception as exc:
        sys.exit('ERROR: {}'.format(exc))
    print('schema file okay')


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

    check = subs.add_parser('check')
    check.add_argument('--schemafile', default=VENDORED)
    check.add_argument('--upstream', default=None)

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
