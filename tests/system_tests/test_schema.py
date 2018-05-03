import contextlib
import io
import os.path
import subprocess
import sys
import tempfile
from textwrap import dedent
import unittest

from tests import skip_py2
skip_py2()  # noqa
from tests.helpers import http
from debugger_protocol.schema.__main__ import handle_check


class VendoredSchemaTests(unittest.TestCase):
    """Tests to make sure our vendored schema is up-to-date."""

    @unittest.skipUnless(os.environ.get('HAS_NETWORK'), 'no network')
    def test_matches_upstream(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with contextlib.redirect_stderr(stdout):
                try:
                    handle_check()
                except Exception as exc:
                    self.fail(str(exc))


class DownloadCommandTests(unittest.TestCase):

    CMD = '{python} -m debugger_protocol.schema download'

    def setUp(self):
        super().setUp()
        self._tempdir = tempfile.TemporaryDirectory(prefix='ptvsd-test-')
        self.dirname = self._tempdir.name
        self.schemafile = os.path.join(self.dirname, 'schema.json')
        self.metadata = os.path.join(self.dirname, 'UPSTREAM')

        self.cmd = self.CMD.format(python=sys.executable)
        self.args = self.cmd.split() + [
            '--target', self.schemafile,
        ]

    def tearDown(self):
        self._tempdir.cleanup()
        super().tearDown()

    def get_expected_stdout(self, lines):
        with io.StringIO() as txt:
            for line in lines:
                txt.write(line)
                txt.write(os.linesep)
            txt.flush()
            return txt.getvalue()

    @unittest.skipUnless(os.environ.get('HAS_NETWORK'), 'no network')
    def test_default_source(self):
        res = subprocess.run(self.args,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)

        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout.decode(), self.get_expected_stdout([
            'downloading the schema file from https://github.com/Microsoft/vscode-debugadapter-node/raw/master/debugProtocol.json...',  # noqa
            '...schema file written to {}.'.format(self.schemafile),
            'saving the schema metadata...',
            '...metadata written to {}.'.format(self.metadata)]))
        self.assertEqual(res.stderr, b'')

    def test_custom_source(self):
        handler = http.json_file_handler(b'<a schema>')
        with http.Server(handler) as srv:
            upstream = 'http://{}/schema.json'.format(srv.address)
            res = subprocess.run(self.args + ['--source', upstream],
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
        stdout = res.stdout.decode() if res.stdout else ''
        stderr = res.stderr.decode() if res.stderr else ''

        # Check the command result.
        self.assertEqual(res.returncode, 0)
        self.assertEqual(stdout, self.get_expected_stdout([
            'downloading the schema file from http://localhost:8000/schema.json...',  # noqa
            '...schema file written to {}.'.format(self.schemafile),
            'saving the schema metadata...',
            '...metadata written to {}.'.format(self.metadata)]))
        self.assertEqual(stderr, '')

        # Check the downloaded files.
        with open(self.schemafile) as schemafile:
            data = schemafile.read()
        with open(self.metadata) as metafile:
            metadata = metafile.read()
        orig = metadata
        metadata = '\n'.join(line
                             for line in metadata.split('\n')
                             if not line.startswith('downloaded: '))
        self.assertEqual(data, "<a schema>")
        self.assertEqual(metadata, dedent("""\
                upstream:   http://localhost:8000/schema.json
                revision:   <unknown>
                checksum:   e778c3751f9d0bceaf8d5aa81e2c659f
                """))
        self.assertNotEqual(metadata, orig)


class CheckCommandTests(unittest.TestCase):

    CMD = '{python} -m debugger_protocol.schema check'

    def setUp(self):
        super().setUp()
        self.tempdir = None
        self.cmd = self.CMD.format(python=sys.executable)
        self.args = self.cmd.split()

    def tearDown(self):
        if self.tempdir is not None:
            self.tempdir.cleanup()
        super().tearDown()

    def resolve_filename(self, name):
        if self.tempdir is None:
            self.tempdir = tempfile.TemporaryDirectory(prefix='ptvsd-test-')
        return os.path.join(self.tempdir.name, name)

    def add_file(self, name, content):
        filename = self.resolve_filename(name)
        with open(filename, 'w') as outfile:
            outfile.write(content)
        return filename

    def get_expected_stdout(self, lines):
        with io.StringIO() as txt:
            for line in lines:
                txt.write(line)
                txt.write(os.linesep)
            txt.flush()
            return txt.getvalue()

    def test_match(self):
        schemafile = self.add_file('schema.json', '<a schema>')
        self.add_file('UPSTREAM', dedent("""\
                upstream:   https://x.y.z/a/b/c/debugProtocol.json
                revision:   <unknown>
                checksum:   e778c3751f9d0bceaf8d5aa81e2c659f
                downloaded: 2018-01-09 13:10:59 (UTC)
                """))
        handler = http.json_file_handler(b'<a schema>')
        with http.Server(handler) as srv:
            upstream = 'http://{}/schema.json'.format(srv.address)
            args = self.args + [
                '--schemafile', schemafile,
                '--upstream', upstream,
            ]
            res = subprocess.run(args,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
        stdout = res.stdout.decode() if res.stdout else ''
        stderr = res.stderr.decode() if res.stderr else ''

        # Check the command result.
        self.assertEqual(res.returncode, 0)
        self.assertEqual(stdout, self.get_expected_stdout([
            'checking local schema file...',
            'comparing with upstream schema file...',
            'schema file okay']))
        self.assertEqual(stderr, '')

    def test_schema_missing(self):
        schemafile = self.resolve_filename('schema.json')
        self.add_file('UPSTREAM', dedent("""\
                upstream:   https://x.y.z/a/b/c/debugProtocol.json
                revision:   <unknown>
                checksum:   e778c3751f9d0bceaf8d5aa81e2c659f
                downloaded: 2018-01-09 13:10:59 (UTC)
                """))
        args = self.args + [
            '--schemafile', schemafile,
            '--upstream', '<a URL>',
        ]
        res = subprocess.run(args,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        stdout = res.stdout.decode() if res.stdout else ''
        stderr = res.stderr.decode() if res.stderr else ''

        # Check the command result.
        self.assertEqual(res.returncode, 1)
        self.assertEqual(stdout, self.get_expected_stdout([
            'checking local schema file...']))
        self.assertRegex(stderr.strip(), r"ERROR: schema file '[^']*schema.json' not found")  # noqa

    def test_metadata_missing(self):
        schemafile = self.add_file('schema.json', '<a schema>')
        args = self.args + [
            '--schemafile', schemafile,
            '--upstream', '<a URL>',
        ]
        res = subprocess.run(args,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        stdout = res.stdout.decode() if res.stdout else ''
        stderr = res.stderr.decode() if res.stderr else ''

        # Check the command result.
        self.assertEqual(res.returncode, 1)
        self.assertEqual(stdout, self.get_expected_stdout([
            'checking local schema file...']))
        self.assertRegex(stderr.strip(), r"ERROR: metadata file for '[^']*schema.json' not found")  # noqa

    def test_metadata_mismatch(self):
        schemafile = self.add_file('schema.json', '<other schema>')
        self.add_file('UPSTREAM', dedent("""\
                upstream:   https://x.y.z/a/b/c/debugProtocol.json
                revision:   <unknown>
                checksum:   e778c3751f9d0bceaf8d5aa81e2c659f
                downloaded: 2018-01-09 13:10:59 (UTC)
                """))
        args = self.args + [
            '--schemafile', schemafile,
            '--upstream', '<a URL>',
        ]
        res = subprocess.run(args,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        stdout = res.stdout.decode() if res.stdout else ''
        stderr = res.stderr.decode() if res.stderr else ''

        # Check the command result.
        self.assertEqual(res.returncode, 1)
        self.assertEqual(stdout, self.get_expected_stdout([
            'checking local schema file...']))
        self.assertRegex(stderr.strip(), r"ERROR: schema file '[^']*schema.json' does not match metadata file .*")  # noqa

    def test_upstream_not_found(self):
        schemafile = self.add_file('schema.json', '<a schema>')
        self.add_file('UPSTREAM', dedent("""\
                upstream:   https://x.y.z/a/b/c/debugProtocol.json
                revision:   <unknown>
                checksum:   e778c3751f9d0bceaf8d5aa81e2c659f
                downloaded: 2018-01-09 13:10:59 (UTC)
                """))
        handler = http.error_handler(404, 'schema not found')
        with http.Server(handler) as srv:
            upstream = 'http://{}/schema.json'.format(srv.address)
            args = self.args + [
                '--schemafile', schemafile,
                '--upstream', upstream,
            ]
            res = subprocess.run(args,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
        stdout = res.stdout.decode() if res.stdout else ''
        stderr = res.stderr.decode() if res.stderr else ''

        # Check the command result.
        self.assertEqual(res.returncode, 1)
        self.assertEqual(stdout, self.get_expected_stdout([
                'checking local schema file...',
                'comparing with upstream schema file...']))
        self.assertEqual(stderr.strip(), "ERROR: schema file at 'http://localhost:8000/schema.json' not found")  # noqa

    def test_upstream_mismatch(self):
        schemafile = self.add_file('schema.json', '<a schema>')
        self.add_file('UPSTREAM', dedent("""\
                upstream:   https://x.y.z/a/b/c/debugProtocol.json
                revision:   <unknown>
                checksum:   e778c3751f9d0bceaf8d5aa81e2c659f
                downloaded: 2018-01-09 13:10:59 (UTC)
                """))
        handler = http.json_file_handler(b'<other schema>')
        with http.Server(handler) as srv:
            upstream = 'http://{}/schema.json'.format(srv.address)
            args = self.args + [
                '--schemafile', schemafile,
                '--upstream', upstream,
            ]
            res = subprocess.run(args,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
        stdout = res.stdout.decode() if res.stdout else ''
        stderr = res.stderr.decode() if res.stderr else ''

        # Check the command result.
        self.assertEqual(res.returncode, 1)
        self.assertEqual(stdout, self.get_expected_stdout([
                'checking local schema file...',
                'comparing with upstream schema file...']))
        self.assertRegex(stderr.strip(), r"ERROR: local schema file '[^']*schema.json' does not match upstream .*")  # noqa
