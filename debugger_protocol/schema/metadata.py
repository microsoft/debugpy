from collections import namedtuple
from datetime import datetime
import os.path
from textwrap import dedent

from ._util import github_url_replace_ref


class MetadataError(Exception):
    """A metadata-related operation failed."""


def open_metadata(schemafile, mode='r', *, _open=open):
    """Return a file object for the metadata of the given schema file.

    Also return the metadata file's filename.
    """
    from .vendored import METADATA  # Here due to a circular import.
    filename = os.path.join(os.path.dirname(schemafile),
                            os.path.basename(METADATA))
    try:
        return _open(filename, mode), filename
    except FileNotFoundError:
        raise MetadataError(
                'metadata file for {!r} not found'.format(schemafile))


def read_metadata(schemafile, *, _open=open):
    """Return the metadata corresponding to the schema file.

    Also return the path to the metadata file.
    """
    metafile, filename = open_metadata(schemafile, _open=_open)
    with metafile:
        data = metafile.read()

    try:
        meta = Metadata.parse(data)
    except Exception as exc:
        raise MetadataError(
                'metadata file {!r} not valid: {}'.format(filename, exc))

    return meta, filename


class Metadata(
        namedtuple('Metadata', 'upstream revision checksum downloaded')):
    """Info about the local copy of the upstream schema file."""

    TIMESTAMP = '%Y-%m-%d %H:%M:%S (UTC)'

    FORMAT = dedent("""\
            upstream:   {}
            revision:   {}
            checksum:   {}
            downloaded: {:%s}
            """) % TIMESTAMP

    @classmethod
    def parse(cls, data):
        """Return an instance based on the given metadata string."""
        lines = data.splitlines()

        kwargs = {}
        for line in lines:
            line = line.strip()
            if line.startswith('#'):
                continue
            if not line:
                continue
            field, _, value = line.partition(':')
            kwargs[field] = value.strip()
        self = cls(**kwargs)
        return self

    def __new__(cls, upstream, revision, checksum, downloaded):
        # coercion
        upstream = str(upstream) if upstream else None
        revision = str(revision) if revision else None
        checksum = str(checksum) if checksum else None
        if not downloaded:
            downloaded = None
        elif isinstance(downloaded, str):
            downloaded = datetime.strptime(downloaded, cls.TIMESTAMP)
        elif downloaded.tzinfo is not None:
            downloaded -= downloaded.utcoffset()

        self = super().__new__(cls, upstream, revision, checksum, downloaded)
        return self

    def __init__(self, *args, **kwargs):
        # validation

        if not self.upstream:
            raise ValueError('missing upstream URL')
        # TODO ensure upstream is URL?

        if not self.revision:
            raise ValueError('missing upstream revision')
        # TODO ensure revision is a hash?

        if not self.checksum:
            raise ValueError('missing checksum')
        # TODO ensure checksum is a MD5 hash?

        if not self.downloaded:
            raise ValueError('missing downloaded')

    @property
    def url(self):
        if self.upstream.startswith('https://github.com/'):
            return github_url_replace_ref(self.upstream, self.revision)
        else:
            raise NotImplementedError

    def format(self):
        """Return a string containing the formatted metadata."""
        return self.FORMAT.format(*self)
