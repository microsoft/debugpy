
import argparse
import sys

from . import UPSTREAM, VENDORED


COMMANDS = {}

def as_command(name):
    def decorator(f):
        COMMANDS[name] = f
        return f
    return decorator


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
