import os
import sys
import time
import ptvsd

if os.getenv('PTVSD_ENABLE_ATTACH', None) is not None:
    ptvsd.enable_attach((sys.argv[1], sys.argv[2]))

if os.getenv('PTVSD_WAIT_FOR_ATTACH', None) is not None:
    print('waiting for attach')
    ptvsd.wait_for_attach()
elif os.getenv('PTVSD_IS_ATTACHED', None) is not None:
    print('checking is attached')
    while not ptvsd.is_attached():
        time.sleep(0.1)


def main():
    count = 0
    while count < 50:
        print(count)
        time.sleep(0.3)
        if os.getenv('PTVSD_BREAK_INTO_DEBUGGER', None) is not None:
            ptvsd.break_into_debugger()
        count += 1
    path = os.getenv('PTVSD_TARGET_FILE', None)
    if path is not None:
        with open(path, 'a') as f:
            print('HERE :)', file=f)


main()
