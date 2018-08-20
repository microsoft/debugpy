import sys
import ptvsd
import os
import time

ptvsd.enable_attach((sys.argv[1], sys.argv[2]))


def main():
    count = 0
    while count < 50:
        if os.getenv('PTVSD_WAIT_FOR_ATTACH', None) is not None:
            print('waiting for attach')
            ptvsd.wait_for_attach()
        elif os.getenv('PTVSD_IS_ATTACHED', None) is not None:
            print('checking is attached')
            while not ptvsd.is_attached():
                time.sleep(0.1)
        else:
            pass
        print('one')
        breakpoint()  # noqa
        time.sleep(0.5)
        print('two')
        count += 1


main()
