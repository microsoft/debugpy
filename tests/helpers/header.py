from . import noop
from ._io import iter_lines_buffered, write_all


class HeaderError(Exception):
    """Some header-related problem."""


class HeaderLineError(HeaderError):
    """A problem with an encoded header line."""


class DecodeError(HeaderLineError):
    """Trouble decoding a header line."""


def decode(line):
    """Return (name, value) for the given encoded header line."""
    if line[-2:] == b'\r\n':
        line = line[:-2]
    if not line:
        return None, None
    line = line.decode('ascii', 'replace')
    name, sep, value = line.partition(':')
    if not sep:
        raise DecodeError(line)
    return name, value


def encode(name, value):
    """Return the encoded header line."""
    return '{}: {}\r\n'.format(name, value).encode('ascii')


def read_one(read, **kwargs):
    """Return ((name, value), remainder) for the next header from read()."""
    lines = iter_lines_buffered(read, sep=b'\r\n', **kwargs)
    for line, remainder in lines:
        if not line:
            return None, remainder
        return decode(line), remainder


def write_one(write, name, value, stop=noop):
    """Send the header."""
    line = encode(name, value)
    return write_all(write, line, stop=stop)


#def recv_header(sock, stop=(lambda: None), timeout=5.0):
#    """Return (name, value) for the next header."""
#    line = b''
#    with socket.timeout(sock, timeout):
#        while not stop():
#            c = sock.recv(1)
#            if c == b'\r':
#                c = sock.recv(1)
#                if c == b'\n':
#                    break
#                line += b'\r'
#                line += c
#            else:
#                line += c
#    line = line.decode('ascii', 'replace')
#    if not line:
#        return None, None
#    name, sep, value = line.partition(':')
#    if not sep:
#        raise ValueError('bad header line {!r}'.format(line))
#    return name, value
#
#
#def send_header(sock, name, value):
#    """Send the header."""
#    line = '{}: {}\r\n'.format(name, value).encode('ascii')
#    while line:
#        sent = sock.send(line)
#        line = line[sent:]
