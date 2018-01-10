import io
from textwrap import dedent
import unittest

from .helpers import StubOpener
from debugger_protocol.schema.file import SchemaFileError
from debugger_protocol.schema.metadata import MetadataError
from debugger_protocol.schema.vendored import (
        SchemaFileMismatchError, check_local, check_upstream)


class CheckLocalTests(unittest.TestCase):

    def test_match(self):
        metafile = io.StringIO(dedent("""
                upstream:   https://x.y.z/schema.json
                revision:   abcdef0123456789
                checksum:   e778c3751f9d0bceaf8d5aa81e2c659f
                downloaded: 2018-01-09 13:10:59 (UTC)
                """))
        schemafile = io.BytesIO(b'<a schema>')
        opener = StubOpener(metafile, schemafile)

        # This does not fail.
        check_local('schema.json', _open=opener.open)

    def test_mismatch(self):
        metafile = io.StringIO(dedent("""
                upstream:   https://x.y.z/schema.json
                revision:   abcdef0123456789
                checksum:   abc2
                downloaded: 2018-01-09 13:10:59 (UTC)
                """))
        schemafile = io.BytesIO(b'<a schema>')
        opener = StubOpener(metafile, schemafile)

        with self.assertRaises(SchemaFileMismatchError) as cm:
            check_local('schema.json', _open=opener.open)
        self.assertEqual(str(cm.exception),
                         ('schema file \'schema.json\' does not match '
                          'metadata file (checksum mismatch: '
                          '\'e778c3751f9d0bceaf8d5aa81e2c659f\' != \'abc2\')'))

    def test_metafile_missing(self):
        metafile = None
        schemafile = io.BytesIO(b'<a schema>')
        opener = StubOpener(metafile, schemafile)

        with self.assertRaises(MetadataError):
            check_local('schema.json', _open=opener.open)

    def test_metafile_invalid(self):
        metafile = io.StringIO('<bogus>')
        metafile.name = '/x/y/z/UPSTREAM'
        schemafile = io.BytesIO(b'<a schema>')
        opener = StubOpener(metafile, schemafile)

        with self.assertRaises(MetadataError):
            check_local('schema.json', _open=opener.open)

    def test_schemafile_missing(self):
        metafile = io.StringIO(dedent("""
                upstream:   https://x.y.z/schema.json
                revision:   abcdef0123456789
                checksum:   e778c3751f9d0bceaf8d5aa81e2c659f
                downloaded: 2018-01-09 13:10:59 (UTC)
                """))
        schemafile = None
        opener = StubOpener(metafile, schemafile)

        with self.assertRaises(SchemaFileError):
            check_local('schema.json', _open=opener.open)


class CheckUpstream(unittest.TestCase):

    def test_match(self):
        metafile = io.StringIO(dedent("""
                upstream:   https://github.com/x/y/raw/master/z
                revision:   fc2395ca3564fb2afded8d90ddbe38dad1bf86f1
                checksum:   e778c3751f9d0bceaf8d5aa81e2c659f
                downloaded: 2018-01-09 13:10:59 (UTC)
                """))
        schemafile = io.BytesIO(b'<a schema>')
        buf = io.BytesIO(
                b'{"sha": "fc2395ca3564fb2afded8d90ddbe38dad1bf86f1"}')
        opener = StubOpener(metafile, schemafile, buf)

        # This does not fail.
        check_upstream('schema.json',
                       _open=opener.open, _open_url=opener.open)

    def test_revision_mismatch(self):
        metafile = io.StringIO(dedent("""
                upstream:   https://github.com/x/y/raw/master/z
                revision:   abc2
                checksum:   e778c3751f9d0bceaf8d5aa81e2c659f
                downloaded: 2018-01-09 13:10:59 (UTC)
                """))
        schemafile = io.BytesIO(b'<a schema>')
        buf = io.BytesIO(
                b'{"sha": "fc2395ca3564fb2afded8d90ddbe38dad1bf86f1"}')
        opener = StubOpener(metafile, schemafile, buf)

        with self.assertRaises(SchemaFileMismatchError) as cm:
            check_upstream('schema.json',
                           _open=opener.open, _open_url=opener.open)
        self.assertEqual(str(cm.exception),
                         ('local schema file \'schema.json\' does not match '
                          'upstream \'https://github.com/x/y/raw/master/z\' '
                          '(revision mismatch: \'abc2\' != \'fc2395ca3564fb2afded8d90ddbe38dad1bf86f1\')'))  # noqa

    def test_checksum_mismatch(self):
        metafile = io.StringIO(dedent("""
                upstream:   https://github.com/x/y/raw/master/z
                revision:   fc2395ca3564fb2afded8d90ddbe38dad1bf86f1
                checksum:   abc2
                downloaded: 2018-01-09 13:10:59 (UTC)
                """))
        schemafile = io.BytesIO(b'<a schema>')
        buf = io.BytesIO(
                b'{"sha": "fc2395ca3564fb2afded8d90ddbe38dad1bf86f1"}')
        opener = StubOpener(metafile, schemafile, buf)

        with self.assertRaises(SchemaFileMismatchError) as cm:
            check_upstream('schema.json',
                           _open=opener.open, _open_url=opener.open)
        self.assertEqual(str(cm.exception),
                         ('local schema file \'schema.json\' does not match '
                          'upstream \'https://github.com/x/y/raw/master/z\' '
                          '(checksum mismatch: \'abc2\' != \'e778c3751f9d0bceaf8d5aa81e2c659f\')'))  # noqa

    def test_metafile_missing(self):
        ...

    def test_url_resource_missing(self):
        ...
