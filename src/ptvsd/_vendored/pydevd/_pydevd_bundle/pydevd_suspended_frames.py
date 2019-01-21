from contextlib import contextmanager
import sys

from _pydev_imps._pydev_saved_modules import threading
from _pydevd_bundle.pydevd_constants import get_frame
import traceback


class _FramesTracker(object):
    '''
    This is a helper class to be used to track frames when a thread becomes suspended.
    '''

    def __init__(self, suspended_frames_manager, py_db):
        self._suspended_frames_manager = suspended_frames_manager
        self.py_db = py_db
        self._frame_id_to_frame = {}

        # Note that a given frame may appear in multiple threads when we have custom
        # frames added, but as those are coroutines, this map will point to the actual
        # main thread (which is the one that needs to be suspended for us to get the
        # variables).
        self._frame_id_to_main_thread_id = {}

        # A map of the suspended thread id -> list(frames ids) -- note that
        # frame ids are kept in order (the first one is the suspended frame).
        self._thread_id_to_frame_ids = {}

        # A map of the lines where it's suspended (needed for exceptions where the frame
        # lineno is not correct).
        self._frame_id_to_lineno = {}

        # The main suspended thread (if this is a coroutine this isn't the id of the
        # coroutine thread, it's the id of the actual suspended thread).
        self._main_thread_id = None

        # Helper to know if it was already untracked.
        self._untracked = False

        # We need to be thread-safe!
        self._lock = threading.Lock()

    def track(self, thread_id, frame, frame_id_to_lineno, frame_custom_thread_id=None):
        '''
        :param thread_id:
            The thread id to be used for this frame.

        :param frame:
            The topmost frame which is suspended at the given thread.

        :param frame_id_to_lineno:
            If available, the line number for the frame will be gotten from this dict,
            otherwise frame.f_lineno will be used (needed for unhandled exceptions as
            the place where we report may be different from the place where it's raised).

        :param frame_custom_thread_id:
            If None this this is the id of the thread id for the custom frame (i.e.: coroutine).
        '''
        with self._lock:
            coroutine_or_main_thread_id = frame_custom_thread_id or thread_id

            if coroutine_or_main_thread_id in self._suspended_frames_manager.thread_id_to_tracker:
                sys.stderr.write('pydevd: Something is wrong. Tracker being added twice to the same thread id.\n')

            self._suspended_frames_manager.thread_id_to_tracker[coroutine_or_main_thread_id] = self
            self._main_thread_id = thread_id
            self._frame_id_to_lineno = frame_id_to_lineno

            frame_ids_from_thread = self._thread_id_to_frame_ids.setdefault(
                coroutine_or_main_thread_id, [])

            while frame is not None:
                frame_id = id(frame)
                self._frame_id_to_frame[frame_id] = frame
                frame_ids_from_thread.append(frame_id)

                self._frame_id_to_main_thread_id[frame_id] = thread_id

                frame = frame.f_back

    def untrack_all(self):
        with self._lock:
            if self._untracked:
                # Calling multiple times is expected for the set next statement.
                return
            self._untracked = True
            for thread_id in self._thread_id_to_frame_ids:
                self._suspended_frames_manager.thread_id_to_tracker.pop(thread_id, None)

            self._frame_id_to_frame.clear()
            self._frame_id_to_main_thread_id.clear()
            self._thread_id_to_frame_ids.clear()
            self._frame_id_to_lineno.clear()
            self._main_thread_id = None
            self._suspended_frames_manager = None

    def get_topmost_frame_and_frame_id_to_line(self, thread_id):
        with self._lock:
            frame_ids = self._thread_id_to_frame_ids.get(thread_id)
            if frame_ids is not None:
                frame_id = frame_ids[0]
                return self._frame_id_to_frame[frame_id], self._frame_id_to_lineno

    def find_frame(self, thread_id, frame_id):
        with self._lock:
            return self._frame_id_to_frame.get(frame_id)

    def create_thread_suspend_command(self, thread_id, stop_reason, message, suspend_type):
        with self._lock:
            frame_ids = self._thread_id_to_frame_ids[thread_id]

            # First one is topmost frame suspended.
            frame = self._frame_id_to_frame[frame_ids[0]]

            cmd = self.py_db.cmd_factory.make_thread_suspend_message(
                thread_id, frame, stop_reason, message, suspend_type, frame_id_to_lineno=self._frame_id_to_lineno)

            frame = None
            return cmd


class SuspendedFramesManager(object):

    def __init__(self):
        self._thread_id_to_fake_frames = {}
        self.thread_id_to_tracker = {}

    def get_topmost_frame_and_frame_id_to_line(self, thread_id):
        tracker = self.thread_id_to_tracker.get(thread_id)
        if tracker is None:
            return None
        return tracker.get_topmost_frame_and_frame_id_to_line(thread_id)

    @contextmanager
    def track_frames(self, py_db):
        tracker = _FramesTracker(self, py_db)
        try:
            yield tracker
        finally:
            tracker.untrack_all()

    def add_fake_frame(self, thread_id, frame_id, frame):
        self._thread_id_to_fake_frames.setdefault(thread_id, {})[int(frame_id)] = frame

    def find_frame(self, thread_id, frame_id):
        try:
            if frame_id == "*":
                return get_frame()  # any frame is specified with "*"
            frame_id = int(frame_id)

            fake_frames = self._thread_id_to_fake_frames.get(thread_id)
            if fake_frames is not None:
                frame = fake_frames.get(frame_id)
                if frame is not None:
                    return frame

            frames_tracker = self.thread_id_to_tracker.get(thread_id)
            if frames_tracker is not None:
                frame = frames_tracker.find_frame(thread_id, frame_id)
                if frame is not None:
                    return frame

            return None
        except:
            traceback.print_exc()
            return None
