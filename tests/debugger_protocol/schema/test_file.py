import io
import unittest

from .helpers import StubOpener
from debugger_protocol.schema.file import SchemaFileError, read_schema


class ReadSchemaTests(unittest.TestCase):

    def test_success(self):
        schemafile = io.BytesIO(b'<a schema>')
        opener = StubOpener(schemafile)

        data = read_schema('schema.json', _open=opener.open)

        self.assertEqual(data, b'<a schema>')

    def test_file_missing(self):
        opener = StubOpener(None)

        with self.assertRaises(SchemaFileError):
            read_schema('schema.json', _open=opener.open)
