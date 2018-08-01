import ptvsd
import sys
ptvsd.enable_attach((sys.argv[1], sys.argv[2]))
ptvsd.wait_for_attach()


def main():
    try:
        raise ArithmeticError('Hello')
    except Exception:
        pass
    sys.stdout.write('end')


main()
