import json
from _pydev_bundle import pydev_log


class DebugOptions(object):

    __slots__ = [
        'just_my_code',
        'redirect_output',
        'show_return_value',
        'break_system_exit_zero',
        'django_debug',
        'flask_debug',
        'stop_on_entry',
        'max_exception_stack_frames',
    ]

    def __init__(self):
        self.just_my_code = True
        self.redirect_output = False
        self.show_return_value = False
        self.break_system_exit_zero = False
        self.django_debug = False
        self.flask_debug = False
        self.stop_on_entry = False
        self.max_exception_stack_frames = 0

    def to_json(self):
        dct = {}
        for s in self.__slots__:
            dct[s] = getattr(self, s)
        return json.dumps(dct)

    def update_from_args(self, args):

        if 'justMyCode' in args:
            self.just_my_code = bool_parser(args['justMyCode'])
        else:
            # i.e.: if justMyCode is provided, don't check the deprecated value
            if 'debugStdLib' in args:
                pydev_log.error_once('debugStdLib is deprecated. Use justMyCode=false instead.')
                self.just_my_code = not bool_parser(args['debugStdLib'])

        if 'redirectOutput' in args:
            self.redirect_output = bool_parser(args['redirectOutput'])

        if 'showReturnValue' in args:
            self.show_return_value = bool_parser(args['showReturnValue'])

        if 'breakOnSystemExitZero' in args:
            self.break_system_exit_zero = bool_parser(args['breakOnSystemExitZero'])

        if 'django' in args:
            self.django_debug = bool_parser(args['django'])

        if 'flask' in args:
            self.flask_debug = bool_parser(args['flask'])

        if 'jinja' in args:
            self.flask_debug = bool_parser(args['jinja'])

        if 'stopOnEntry' in args:
            self.stop_on_entry = bool_parser(args['stopOnEntry'])

        self.max_exception_stack_frames = int_parser(args.get('maxExceptionStackFrames', 0))


def int_parser(s, default_value=0):
    try:
        return int(s)
    except Exception:
        return default_value


def bool_parser(s):
    return s in ("True", "true", "1", True, 1)

