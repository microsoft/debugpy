import contextlib
from io import StringIO, BytesIO
import sys

from . import noop


if sys.version_info < (3,):
    Buffer = BytesIO
else:
    Buffer = StringIO


@contextlib.contextmanager
def captured_stdio(out=None, err=None):
    if out is None and err is None:
        out = err = Buffer()
    else:
        if out is True:
            out = Buffer()
        elif out is False:
            out = None
        if err is True:
            err = Buffer()
        elif err is False:
            err = None

    orig = sys.stdout, sys.stderr
    if out is not None:
        sys.stdout = out
    if err is not None:
        sys.stderr = err
    try:
        yield out, err
    finally:
        sys.stdout, sys.stderr = orig


def iter_lines(read, sep=b'\n', stop=noop):
    """Yield each sep-delimited line.

    If EOF is hit, the loop is stopped, or read() returns b'' then
    EOFError is raised with exc.remainder set to any bytes left in the
    buffer.
    """
    first = sep[0]
    line = b''
    while True:
        try:
            if stop():
                raise EOFError()
            c = read(1)
            if not c:
                raise EOFError()
        except EOFError as exc:
            exc.buffered = line
            raise
        line += c
        if c != first:
            continue

        for want in sep[1:]:
            try:
                if stop():
                    raise EOFError()
                c = read(1)
                if not c:
                    raise EOFError()
            except EOFError as exc:
                exc.buffered = line
                raise
            line += c
            if c != want:
                break
        else:
            # EOL
            yield line
            line = b''


def iter_lines_buffered(read, sep=b'\n', initial=b'', stop=noop):
    """Yield (line, remainder) for each sep-delimited line.

    If EOF is hit, the loop is stopped, or read() returns b'' then
    EOFError is raised with exc.remainder set to any bytes left in the
    buffer.
    """
    gap = len(sep)
    # TODO: Use a bytearray?
    buf = b''
    data = initial
    while True:
        try:
            line = data[:data.index(sep)]
        except ValueError:
            buf += data
            try:
                if stop():
                    raise EOFError()
                # ConnectionResetError (errno 104) likely means the
                # client was never able to establish a connection.
                # TODO: Handle ConnectionResetError gracefully.
                data = read(1024)
                if not data:
                    raise EOFError()
            except EOFError as exc:
                exc.remainder = buf
                raise
        else:
            # EOL
            data = data[len(line) + gap:]
            yield buf + line, data
            buf = b''


def read_buffered(read, numbytes, initial=b'', stop=noop):
    """Return (data, remainder) with read().

    If EOF is hit, the loop is stopped, or read() returns b'' then
    EOFError is raised with exc.buffered set to any bytes left in the
    buffer.
    """
    # TODO: Use a bytearray?
    buf = initial
    while len(buf) < numbytes:
        try:
            if stop():
                raise EOFError()
            data = read(1024)
            if not data:
                raise EOFError()
        except EOFError as exc:
            exc.buffered = buf
            raise
        buf += data
    return buf[:numbytes], buf[numbytes:]


def write_all(write, data, stop=noop):
    """Keep writing until all the data is written."""
    while data and not stop():
        sent = write(data)
        data = data[sent:]
