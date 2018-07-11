import sys
import ptvsd
ptvsd.enable_attach((('localhost', 9879)))
ptvsd.wait_for_attach()

try:
    raise ArithmeticError('Hello')
except Exception:
    pass
sys.stdout.write('end')
