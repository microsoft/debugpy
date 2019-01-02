from _pydevd_bundle._debug_adapter.pydevd_schema_log import debug_exception


class BaseSchema(object):

    def to_json(self):
        import json
        return json.dumps(self.to_dict())


_requests_to_types = {}
_responses_to_types = {}
_event_to_types = {}
_all_messages = {}


def register(cls):
    _all_messages[cls.__name__] = cls
    return cls


def register_request(command):

    def do_register(cls):
        _requests_to_types[command] = cls
        return cls

    return do_register


def register_response(command):

    def do_register(cls):
        _responses_to_types[command] = cls
        return cls

    return do_register


def register_event(event):

    def do_register(cls):
        _event_to_types[event] = cls
        return cls

    return do_register


def from_dict(dct):
    msg_type = dct.get('type')
    if msg_type is None:
        raise ValueError('Unable to make sense of message: %s' % (dct,))

    if msg_type == 'request':
        to_type = _requests_to_types
        use = dct['command']

    elif msg_type == 'response':
        to_type = _responses_to_types
        use = dct['command']

    else:
        to_type = _event_to_types
        use = dct['event']

    cls = to_type.get(use)
    if cls is None:
        raise ValueError('Unable to create message from dict: %s. %s not in %s' % (dct, use, sorted(to_type.keys())))
    try:
        return cls(**dct)
    except:
        msg = 'Error creating %s from %s' % (cls, dct)
        debug_exception(msg)
        raise ValueError(msg)

    raise ValueError('Unable to create message from dict: %s' % (dct,))


def from_json(json_msg):
    if isinstance(json_msg, bytes):
        json_msg = json_msg.decode('utf-8')
    import json
    return from_dict(json.loads(json_msg))


def build_response(request, kwargs=None):
    if kwargs is None:
        kwargs = {}
    response_class = _responses_to_types[request.command]
    kwargs.setdefault('seq', -1)  # To be overwritten before sending
    return response_class(command=request.command, request_seq=request.seq, success=True, **kwargs)
