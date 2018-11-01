import sys
import ptvsd
ptvsd.enable_attach((sys.argv[1], sys.argv[2]))
ptvsd.wait_for_attach()

def do_something():
    raise ArithmeticError('Hello')


do_something()
sys.stdout.write('end')
