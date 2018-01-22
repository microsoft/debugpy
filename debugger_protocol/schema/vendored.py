import os.path

from . import DATA_DIR, upstream
from ._util import open_url, get_checksum
from .file import SchemaFileError, read_schema
from .metadata import MetadataError, read_metadata


FILENAME = os.path.join(DATA_DIR, 'debugProtocol.json')
METADATA = os.path.join(DATA_DIR, 'UPSTREAM')


class SchemaFileMismatchError(SchemaFileError, MetadataError):
    """The schema file does not match expectations."""

    @classmethod
    def _build_message(cls, filename, actual, expected, upstream):
        if upstream:
            msg = ('local schema file {!r} does not match upstream {!r}'
                   ).format(filename, expected.upstream)
        else:
            msg = ('schema file {!r} does not match metadata file'
                   ).format(filename)

        for field in actual._fields:
            value = getattr(actual, field)
            other = getattr(expected, field)
            if value != other:
                msg += (' ({} mismatch: {!r} != {!r})'
                        ).format(field, value, other)
                break

        return msg

    def __init__(self, filename, actual, expected, *, upstream=False):
        super().__init__(
            self._build_message(filename, actual, expected, upstream))
        self.filename = filename
        self.actual = actual
        self.expected = expected
        self.upstream = upstream


def check_local(filename, *, _open=open):
    """Ensure that the local schema file matches the local metadata file."""
    # Get the vendored metadata and data.
    meta, _ = read_metadata(filename, _open=_open)
    data = read_schema(filename, _open=_open)

    # Only worry about the checksum matching.
    actual = meta._replace(
        checksum=get_checksum(data))
    if actual != meta:
        raise SchemaFileMismatchError(filename, actual, meta)


def check_upstream(filename, url=None, *, _open=open, _open_url=open_url):
    """Ensure that the local metadata file matches the upstream schema file."""
    # Get the vendored and upstream metadata.
    meta, _ = read_metadata(filename, _open=_open)
    if url is None:
        url = meta.upstream
    _, upmeta = upstream.read(url, _open_url=_open_url)

    # Make sure the revision and checksum match.
    if meta.revision != upmeta.revision:
        raise SchemaFileMismatchError(filename, meta, upmeta, upstream=True)
    if meta.checksum != upmeta.checksum:
        raise SchemaFileMismatchError(filename, meta, upmeta, upstream=True)
