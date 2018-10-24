from datetime import datetime
import io
import urllib.error

from ._util import open_url, get_revision, get_checksum
from .file import SchemaFileError
from .metadata import Metadata


URL = 'https://github.com/Microsoft/vscode-debugadapter-node/raw/master/debugProtocol.json'  # noqa


def download(source, infile, outfile, *,
             _now=datetime.utcnow, _open_url=open_url):
    """Return the corresponding metadata after downloading the schema file."""
    timestamp = _now()
    revision = get_revision(source, _open_url=_open_url)

    data = infile.read()
    checksum = get_checksum(data)
    outfile.write(data)

    return Metadata(source, revision, checksum, timestamp)


def read(url, *, _open_url=open_url):
    """Return (data, metadata) for the given upstream URL."""
    outfile = io.BytesIO()
    try:
        infile = _open_url(url)
    except (FileNotFoundError, urllib.error.HTTPError):
        # TODO: Ensure it's a 404 error?
        raise SchemaFileError('schema file at {!r} not found'.format(url))
    with infile:
        upstream = download(url, infile, outfile, _open_url=_open_url)
    return outfile.getvalue(), upstream
