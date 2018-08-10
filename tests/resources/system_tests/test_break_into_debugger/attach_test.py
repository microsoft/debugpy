import sys
import ptvsd
import os
import time

ptvsd.enable_attach((sys.argv[1], sys.argv[2]))


loopy = False
if os.getenv('PTVSD_WAIT_FOR_ATTACH', None) is not None:
    print('waiting for attach')
    ptvsd.wait_for_attach()
elif os.getenv('PTVSD_IS_ATTACHED', None) is not None:
    print('checking is attached')
    while not ptvsd.is_attached():
        time.sleep(0.1)
else:
    loopy = True


def main():
    if loopy:
        count = 0
        while count < 50:
            print('one')
            ptvsd.break_into_debugger()
            time.sleep(0.1)
            print('two')
            count += 1
    else:
        print('one')
        ptvsd.break_into_debugger()
        print('two')


main()
