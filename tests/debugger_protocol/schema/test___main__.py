import contextlib
import io
from textwrap import dedent
import unittest

from .helpers import StubOpener
from debugger_protocol.schema.vendored import FILENAME as VENDORED, METADATA
from debugger_protocol.schema.__main__ import (
        COMMANDS, handle_download, handle_check)


class Outfile:

    def __init__(self, initial):
        self.written = initial

    def write(self, data):
        self.written += data
        return len(data)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class CommandRegistryTests(unittest.TestCase):

    def test_commands(self):
        self.assertEqual(set(COMMANDS), {
            'download',
            'check',
            })


class HandleDownloadTests(unittest.TestCase):

    def test_default_args(self):
        schemafile = io.BytesIO(b'<a schema>')
        outfile = Outfile(b'')
        buf = io.BytesIO(
                b'{"sha": "fc2395ca3564fb2afded8d90ddbe38dad1bf86f1"}')
        metafile = Outfile('')
        opener = StubOpener(schemafile, outfile, buf, metafile)

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with contextlib.redirect_stderr(stdout):
                handle_download(
                        _open=opener.open, _open_url=opener.open)
        metadata = '\n'.join(line
                             for line in metafile.written.splitlines()
                             if not line.startswith('downloaded: '))

        self.assertEqual(outfile.written, b'<a schema>')
        self.assertEqual(metadata, dedent("""
                upstream:   https://github.com/Microsoft/vscode-debugadapter-node/raw/master/debugProtocol.json
                revision:   fc2395ca3564fb2afded8d90ddbe38dad1bf86f1
                checksum:   e778c3751f9d0bceaf8d5aa81e2c659f
                """).strip())  # noqa
        self.assertEqual(stdout.getvalue(), dedent("""\
                downloading the schema file from https://github.com/Microsoft/vscode-debugadapter-node/raw/master/debugProtocol.json...
                ...schema file written to {}.
                saving the schema metadata...
                ...metadata written to {}.
                """).format(VENDORED, METADATA))  # noqa


class HandleCheckTests(unittest.TestCase):

    def test_default_args(self):
        metadata = dedent("""
                upstream:   https://github.com/x/y/raw/master/z
                revision:   fc2395ca3564fb2afded8d90ddbe38dad1bf86f1
                checksum:   e778c3751f9d0bceaf8d5aa81e2c659f
                downloaded: 2018-01-09 13:10:59 (UTC)
                """)
        opener = StubOpener(
                io.StringIO(metadata),
                io.BytesIO(b'<a schema>'),  # local
                io.StringIO(metadata),
                io.BytesIO(b'<a schema>'),  # upstream
                io.BytesIO(
                    b'{"sha": "fc2395ca3564fb2afded8d90ddbe38dad1bf86f1"}'),
                )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with contextlib.redirect_stderr(stdout):
                handle_check(
                        _open=opener.open, _open_url=opener.open)

        self.assertEqual(stdout.getvalue(), dedent("""\
            checking local schema file...
            comparing with upstream schema file...
            schema file okay
            """))
