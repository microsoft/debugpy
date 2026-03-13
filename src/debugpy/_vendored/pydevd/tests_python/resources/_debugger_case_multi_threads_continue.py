"""
Test for verifying that continuing from a breakpoint resumes all threads,
not just the thread that hit the breakpoint.

When a specific threadId is sent in the ContinueRequest without singleThread=True,
all threads should be resumed per the DAP spec.
"""
import threading

stop_event = threading.Event()


def thread_func():
    stop_event.wait()  # Thread 2 line - wait until signaled
    print("Thread finished")


if __name__ == "__main__":
    t = threading.Thread(target=thread_func)
    t.start()

    stop_event.set()  # Break here - breakpoint on this line

    t.join()
    print("TEST SUCEEDED!")  # end
