import threading
import time


stop = False


def worker(tid, offset):
    i = 0
    global stop
    while not stop:
        time.sleep(0.01)
        i += 1


threads = []
for i in [111, 222]:
    thread = threading.Thread(target=worker, args=(i, len(threads)))
    threads.append(thread)
    thread.start()

print('check here')
stop = True
