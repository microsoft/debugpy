import sys

try:
    raise ArithmeticError('Hello')
except Exception:
    pass
sys.stdout.write('end')
