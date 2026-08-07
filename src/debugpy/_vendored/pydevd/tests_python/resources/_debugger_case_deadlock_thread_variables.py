"""
The idea here is that a secondary thread does the processing of instructions, and an object has a
property whose getter dispatches work to that secondary thread and blocks waiting for the result.

So, when all threads are stopped at a breakpoint, *expanding* that object in the variables view (which
evaluates its properties) would be locked until the secondary thread is allowed to run.

This mirrors real-world objects such as lancedb's ``LanceDBConnection``, whose property getters block
on a background asyncio event loop running in a daemon thread.
"""

import threading

try:
    from queue import Queue
except ImportError:
    from Queue import Queue


class EchoThread(threading.Thread):
    def __init__(self, queue):
        threading.Thread.__init__(self)
        self.daemon = True
        self._queue = queue
        self.started = threading.Event()

    def run(self):
        self.started.set()
        while True:
            obj = self._queue.get()
            if obj == "finish":
                break

            obj.result = obj.value + 1
            obj.event.set()  # Break here 2


class NotificationObject(object):
    def __init__(self, value):
        self.value = value
        self.result = None
        self.event = threading.Event()


class Connection(object):
    """
    Mimics a native-backed connection whose property getter dispatches to a background thread and
    blocks on the result (like lancedb's LanceDBConnection).
    """

    def __init__(self, queue):
        self._queue = queue
        self.storage_options = None

    @property
    def read_consistency_interval(self):
        obj = NotificationObject(41)
        self._queue.put(obj)
        assert obj.event.wait()  # Blocks until the (suspended) EchoThread processes the request.
        return obj.result

    def __repr__(self):
        return "Connection(read_consistency_interval=<computed lazily>)"


def main():
    queue = Queue()
    echo_thread = EchoThread(queue)
    processor = Connection(queue)
    echo_thread.start()
    echo_thread.started.wait()

    print("stop here")  # Break here 1

    queue.put("finish")


if __name__ == "__main__":
    main()
    print("TEST SUCEEDED!")
