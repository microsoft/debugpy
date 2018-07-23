import ptvsd
import sys
ptvsd.enable_attach((sys.argv[1], sys.argv[2]))
ptvsd.wait_for_attach()

raise ArithmeticError('Hello')
sys.stdout.write('end')
