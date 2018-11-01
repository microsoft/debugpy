from . import noop
from ._io import write_all, read_buffered
from .header import read_one as read_header, write_one as write_header


def raw_read_all(read, initial=b'', stop=noop):
    """Yield (msg, headers, remainder) for each message read."""
    headers = {}
    remainder = initial
    while not stop():
        header, remainder = read_header(read, initial=remainder, stop=stop)
        if header is not None:
            name, value = header
            headers[name] = value
            continue

        # end-of-headers
        numbytes = int(headers['Content-Length'])
        data, remainder = read_buffered(read, numbytes, initial=remainder,
                                        stop=stop)
        msg = data.decode('utf-8', 'replace')
        yield msg, headers, remainder
        headers = {}


def raw_write_one(write, body, stop=noop, **headers):
    """Write the message."""
    body = body.encode('utf-8')
    headers.setdefault('Content-Length', len(body))
    for name, value in headers.items():
        write_header(write, name, value, stop=stop)
    write_all(write, b'\r\n')
    write_all(write, body)


def assert_messages_equal(received, expected):
    if received != expected:
        try:
            from itertools import zip_longest
        except ImportError:
            from itertools import izip_longest as zip_longest

        msg = ['']
        msg.append('Received:')
        for r in received:
            msg.append(str(r))
        msg.append('')

        msg.append('Expected:')
        for r in expected:
            msg.append(str(r))
        msg.append('')

        msg.append('Diff by line')
        for i, (a, b) in enumerate(
            zip_longest(received, expected, fillvalue=None)):
            if a == b:
                msg.append(' %2d:  %s' % (i, a,))
            else:
                msg.append('!%2d: %s != %s' % (i, a, b))

        raise AssertionError('\n'.join(msg))


def assert_contains_messages(received, expected):
    error_message = ['']
    received_copy = list(msg._replace(seq=0) for msg in received)
    expected_copy = list(msg._replace(seq=0) for msg in expected)
    received_messages = '\nReceived:\n' + \
                        '\n'.join(str(msg) for msg in received_copy)
    for msg in expected_copy:
        if msg in received_copy:
            del received_copy[received_copy.index(msg)]
        else:
            error_message.append('Not found:')
            error_message.append(str(msg))

    if len(error_message) > 1:
        expected_messages = '\nExpected:\n' + \
                            '\n'.join(str(msg) for msg in expected_copy)
        raise AssertionError('\n'.join(error_message) +
                             received_messages +
                             expected_messages)


def assert_is_subset(received_message, expected_message):
    message = [
        'Subset comparison failed',
        'Received: {}'.format(received_message),
        'Expected: {}'.format(expected_message),
    ]

    def assert_is_subset(received, expected, current_path=''):
        try:
            if received == expected:
                return
            elif type(expected) is dict:
                try:
                    iterator = expected.iteritems()
                except AttributeError:
                    iterator = expected.items()
                parent_path = current_path
                for pkey, pvalue in iterator:
                    current_path = '{}.{}'.format(parent_path, pkey)
                    assert_is_subset(received[pkey], pvalue, current_path)
            elif type(expected) is list:
                parent_path = current_path
                for i, pvalue in enumerate(expected):
                    current_path = '{}[{}]'.format(parent_path, i)
                    assert_is_subset(received[i], pvalue, current_path)
            else:
                if received != expected:
                    raise ValueError
                return True
        except ValueError:
            message.append('Path: body{}'.format(current_path))
            message.append('Received:{}'.format(received))
            message.append('Expected:{}'.format(expected))
            raise AssertionError('\n'.join(message))
        except KeyError:
            message.append('Key not found: body{}'.format(current_path))
            raise AssertionError('\n'.join(message))
        except IndexError:
            message.append('Index not found: body'.format(current_path))
            raise AssertionError('\n'.join(message))

    received = received_message.body if hasattr(received_message, 'body') else received_message # noqa
    expected = expected_message.body if hasattr(expected_message, 'body') else expected_message # noqa
    assert_is_subset(received, expected)
