import io
import unittest

from debugger_protocol.schema._util import get_revision, get_checksum


class GetRevisionTests(unittest.TestCase):

    def test_github(self):
        buf = io.BytesIO(
                b'[{"sha": "fc2395ca3564fb2afded8d90ddbe38dad1bf86f1"}]')
        revision = get_revision('https://github.com/x/y/raw/master/z',
                                _open_url=lambda _: buf)

        self.assertEqual(revision, 'fc2395ca3564fb2afded8d90ddbe38dad1bf86f1')

    def test_unrecognized_url(self):
        revision = get_revision('https://localhost/schema.json',
                                _open_url=lambda _: io.BytesIO())

        self.assertEqual(revision, '<unknown>')


class GetChecksumTests(unittest.TestCase):

    def test_checksums(self):
        checksums = {
                b'': 'd41d8cd98f00b204e9800998ecf8427e',
                b'spam': 'e09f6a7593f8ae3994ea57e1117f67ec',
                }
        for data, expected in checksums.items():
            with self.subTest(data):
                checksum = get_checksum(data)

                self.assertEqual(checksum, expected)
