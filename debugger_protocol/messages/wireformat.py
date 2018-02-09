import json

from . import look_up


def read(stream, look_up=look_up):
    """Return an instance based on the given bytes."""
    headers = {}
    for line in stream:
        if line == b'\r\n':
            break
        assert(line.endswith(b'\r\n'))
        line = line[:-2].decode('ascii')
        try:
            name, value = line.split(': ', 1)
        except ValueError:
            raise RuntimeError('invalid header line: {}'.format(line))
        headers[name] = value

    size = int(headers['Content-Length'])
    body = stream.read(size)

    data = json.loads(body.decode('utf-8'))

    cls = look_up(data)
    return cls.from_data(**data)


def write(stream, msg):
    """Serialize the message and write it to the stream."""
    raw = as_bytes(msg)
    stream.write(raw)


def as_bytes(msg):
    """Return the raw bytes for the message."""
    headers, body = _as_http_data(msg)
    headers = '\r\n'.join('{}: {}'.format(name, value)
                          for name, value in headers.items())
    return headers.encode('ascii') + b'\r\n\r\n' + body.encode('utf-8')


def _as_http_data(msg):
    payload = msg.as_data()
    body = json.dumps(payload)

    headers = {
        'Content-Length': len(body),
        'Content-Type': 'application/json',
    }
    return headers, body
