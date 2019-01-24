import threading
from _pydevd_bundle.pydevd_comm import pydevd_find_thread_by_id


def test_is_main_thread():
    from _pydevd_bundle.pydevd_utils import is_current_thread_main_thread
    assert is_current_thread_main_thread()

    class NonMainThread(threading.Thread):

        def run(self):
            self.is_main_thread = is_current_thread_main_thread()

    non_main_thread = NonMainThread()
    non_main_thread.start()
    non_main_thread.join()
    assert not non_main_thread.is_main_thread


def test_find_thread():
    from _pydevd_bundle.pydevd_constants import get_current_thread_id
    assert pydevd_find_thread_by_id('123') is None

    assert pydevd_find_thread_by_id(
        get_current_thread_id(threading.current_thread())) is threading.current_thread()
