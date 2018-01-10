from datetime import datetime
import io
import unittest

from .helpers import StubOpener
from debugger_protocol.schema.file import SchemaFileError
from debugger_protocol.schema.metadata import Metadata
from debugger_protocol.schema.upstream import (
        download, read)


class DownloadTests(unittest.TestCase):

    def test_success(self):
        now = datetime.utcnow()
        infile = io.BytesIO(b'<a schema>')
        outfile = io.BytesIO()
        buf = io.BytesIO(
                b'{"sha": "fc2395ca3564fb2afded8d90ddbe38dad1bf86f1"}')
        meta = download('https://github.com/x/y/raw/master/z',
                        infile,
                        outfile,
                        _now=(lambda: now),
                        _open=(lambda _: buf),
                        )
        rcvd = outfile.getvalue()

        self.assertEqual(meta, Metadata(
            'https://github.com/x/y/raw/master/z',
            'fc2395ca3564fb2afded8d90ddbe38dad1bf86f1',
            'e778c3751f9d0bceaf8d5aa81e2c659f',
            now,
            ))
        self.assertEqual(rcvd, b'<a schema>')


class ReadSchemaTests(unittest.TestCase):

    def test_success(self):
        schemafile = io.BytesIO(b'<a schema>')
        buf = io.BytesIO(
                b'{"sha": "fc2395ca3564fb2afded8d90ddbe38dad1bf86f1"}')
        opener = StubOpener(schemafile, buf)
        data, meta = read('https://github.com/x/y/raw/master/z',
                          _open_url=opener.open)

        self.assertEqual(data, b'<a schema>')
        self.assertEqual(meta, Metadata(
            'https://github.com/x/y/raw/master/z',
            'fc2395ca3564fb2afded8d90ddbe38dad1bf86f1',
            'e778c3751f9d0bceaf8d5aa81e2c659f',
            meta.date,
            ))

    def test_resource_missing(self):
        schemafile = None
        opener = StubOpener(schemafile)

        with self.assertRaises(SchemaFileError):
            read('schema.json', _open_url=opener.open)
