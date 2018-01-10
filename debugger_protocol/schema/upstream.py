from collections import namedtuple
from datetime import datetime
from textwrap import dedent

from . import UPSTREAM
from ._util import open_url, get_revision, get_checksum


def download(source, infile, outfile, *, _now=datetime.utcnow, _open=open_url):
    """Return the corresponding metadata after downloading the schema file."""
    date = _now()
    revision = get_revision(source, _open=_open)

    data = infile.read()
    checksum = get_checksum(data)
    outfile.write(data)

    return Metadata(source, revision, checksum, date)


class Metadata(namedtuple('Metadata', 'upstream revision checksum date')):
    """Info about the local copy of the upstream schema file."""

    TIMESTAMP = '%Y-%m-%d %H:%M:%S (UTC)'

    FORMAT = dedent("""\
            upstream: {}
            revision: {}
            checksum: {}
            date:     {:%s}
            """) % TIMESTAMP

    #@get_revision(upstream)
    #@download(upstream, revision=None)
    #validate_file(filename)
    #verify_remote()

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

    def __new__(cls, upstream, revision, checksum, date):
        # coercion
        upstream = str(upstream) if upstream else None
        revision = str(revision) if revision else None
        checksum = str(checksum) if checksum else None
        if not date:
            date = None
        elif isinstance(date, str):
            date = datetime.strptime(date, cls.TIMESTAMP)
        elif date.tzinfo is not None:
            date -= date.utcoffset()

        self = super().__new__(cls, upstream, revision, checksum, date)
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

        if not self.date:
            raise ValueError('missing date')

    @property
    def url(self):
        if self.upstream == UPSTREAM:
            return self.upstream.replace('master', self.revision)
        else:
            raise NotImplementedError

    def format(self):
        """Return a string containing the formatted metadata."""
        return self.FORMAT.format(*self)
