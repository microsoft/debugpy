import sys
from _pydevd_bundle.pydevd_constants import EXCEPTION_TYPE_USER_UNHANDLED


def test_create_frames_list_from_traceback():

    def method():
        raise RuntimeError('first')

    def method1():
        try:
            method()
        except Exception as e:
            raise RuntimeError('second') from e

    def method2():
        try:
            method1()
        except Exception as e:
            raise RuntimeError('third') from e

    try:
        method2()
    except Exception as e:
        exc_type, exc_desc, trace_obj = sys.exc_info()
        frame = sys._getframe()

        from _pydevd_bundle.pydevd_frame_utils import create_frames_list_from_traceback
        frames_list = create_frames_list_from_traceback(trace_obj, frame, exc_type, exc_desc, exception_type=EXCEPTION_TYPE_USER_UNHANDLED)
        assert str(frames_list.exc_desc) == 'third'
        assert str(frames_list.chained_frames_list.exc_desc) == 'second'
        assert str(frames_list.chained_frames_list.chained_frames_list.exc_desc) == 'first'
        assert frames_list.chained_frames_list.chained_frames_list.chained_frames_list is None

