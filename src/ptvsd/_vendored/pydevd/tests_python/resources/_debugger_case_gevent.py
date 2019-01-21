#!/usr/bin/env python
from gevent import monkey, sleep, threading as gevent_threading
monkey.patch_all()
import threading

called = []


class MyGreenletThread(threading.Thread):

    def run(self):
        for _i in range(5):
            called.append(self.name)  # break here
            sleep()

if __name__ == '__main__':
    t1 = MyGreenletThread()
    t1.name = 't1'
    t2 = MyGreenletThread()
    t2.name = 't2'

    if hasattr(gevent_threading, 'Thread'):
        # Only available in newer versions of gevent.
        assert isinstance(t1, gevent_threading.Thread)
        assert isinstance(t2, gevent_threading.Thread)

    t1.start()
    t2.start()

    for t1 in (t1, t2):
        t1.join()

    # With gevent it's always the same (gevent coroutine support makes thread
    # switching serial).
    assert called == ['t1', 't1', 't2', 't1', 't2', 't1', 't2', 't1', 't2', 't2']
    print('TEST SUCEEDED')
