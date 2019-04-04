import sys
from _pydevd_bundle.pydevd_constants import int_types
from _pydevd_bundle.pydevd_resolver import MAX_ITEMS_TO_HANDLE


def get_frame():
    var1 = 1
    var2 = [var1]
    var3 = {33: [var1]}
    return sys._getframe()


def check_vars_dict_expected(as_dict, expected):
    assert as_dict == expected


def test_suspended_frames_manager():
    from _pydevd_bundle.pydevd_suspended_frames import SuspendedFramesManager
    suspended_frames_manager = SuspendedFramesManager()
    py_db = None
    with suspended_frames_manager.track_frames(py_db) as tracker:
        # : :type tracker: _FramesTracker
        thread_id = 'thread1'
        frame = get_frame()
        tracker.track(thread_id, frame, frame_id_to_lineno={})

        assert suspended_frames_manager.get_thread_id_for_variable_reference(id(frame)) == thread_id

        variable = suspended_frames_manager.get_variable(id(frame))

        # Should be properly sorted.
        assert ['var1', 'var2', 'var3'] == [x.get_name()for x in variable.get_children_variables()]

        as_dict = dict((x.get_name(), x.get_var_data()) for x in variable.get_children_variables())
        var_reference = as_dict['var2'].pop('variablesReference')
        assert isinstance(var_reference, int_types)  # The variable reference is always a new int.
        assert isinstance(as_dict['var3'].pop('variablesReference'), int_types)  # The variable reference is always a new int.

        check_vars_dict_expected(as_dict, {
            'var1': {'name': 'var1', 'value': '1', 'type': 'int', 'evaluateName': 'var1'},
            'var2': {'name': 'var2', 'value': '[1]', 'type': 'list', 'evaluateName': 'var2'},
            'var3': {'name': 'var3', 'value': '{33: [1]}', 'type': 'dict', 'evaluateName': 'var3'}
        })

        # Now, same thing with a different format.
        as_dict = dict((x.get_name(), x.get_var_data(fmt={'hex': True})) for x in variable.get_children_variables())
        var_reference = as_dict['var2'].pop('variablesReference')
        assert isinstance(var_reference, int_types)  # The variable reference is always a new int.
        assert isinstance(as_dict['var3'].pop('variablesReference'), int_types)  # The variable reference is always a new int.

        check_vars_dict_expected(as_dict, {
            'var1': {'name': 'var1', 'value': '0x1', 'type': 'int', 'evaluateName': 'var1'},
            'var2': {'name': 'var2', 'value': '[0x1]', 'type': 'list', 'evaluateName': 'var2'},
            'var3': {'name': 'var3', 'value': '{0x21: [0x1]}', 'type': 'dict', 'evaluateName': 'var3'}
        })

        var2 = dict((x.get_name(), x) for x in variable.get_children_variables())['var2']
        children_vars = var2.get_children_variables()
        as_dict = (dict([x.get_name(), x.get_var_data()] for x in children_vars))
        assert as_dict == {
            '0': {'name': '0', 'value': '1', 'type': 'int', 'evaluateName': 'var2[0]' },
            '__len__': {'name': '__len__', 'value': '1', 'type': 'int', 'evaluateName': 'len(var2)'},
        }

        var3 = dict((x.get_name(), x) for x in variable.get_children_variables())['var3']
        children_vars = var3.get_children_variables()
        as_dict = (dict([x.get_name(), x.get_var_data()] for x in children_vars))
        assert isinstance(as_dict['33'].pop('variablesReference'), int_types)  # The variable reference is always a new int.

        check_vars_dict_expected(as_dict, {
            '33': {'name': '33', 'value': "[1]", 'type': 'list', 'evaluateName': 'var3[33]'},
            '__len__': {'name': '__len__', 'value': '1', 'type': 'int', 'evaluateName': 'len(var3)'}
        })


def get_large_frame():
    lst = {}
    for idx in range(0, MAX_ITEMS_TO_HANDLE + 1):
        lst[idx] = (1)
    return sys._getframe()

def test_get_child_variables():
    from _pydevd_bundle.pydevd_suspended_frames import SuspendedFramesManager
    suspended_frames_manager = SuspendedFramesManager()
    py_db = None
    with suspended_frames_manager.track_frames(py_db) as tracker:
        # : :type tracker: _FramesTracker
        thread_id = 'thread1'
        frame = get_large_frame()
        tracker.track(thread_id, frame, frame_id_to_lineno={})

        assert suspended_frames_manager.get_thread_id_for_variable_reference(id(frame)) == thread_id

        variable = suspended_frames_manager.get_variable(id(frame))

        for x in variable.get_children_variables():
            try:
                x.get_children_variables()
            except:
                raise AssertionError()