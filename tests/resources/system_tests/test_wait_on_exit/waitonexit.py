import os
import sys

normal_exit = os.getenv('PTVSD_NORMAL_EXIT', None)
exit_code = 0 if normal_exit is not None else 20

print('Ready')
sys.exit(exit_code)
