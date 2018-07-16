import ptvsd
import sys
import time


ptvsd.enable_attach((sys.argv[1], sys.argv[2]))
ptvsd.wait_for_attach()


i = 0
while True:
    time.sleep(0.1)
    # <bp>
    print(i)
    i += 1
