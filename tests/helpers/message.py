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
