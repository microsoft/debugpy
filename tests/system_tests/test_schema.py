import contextlib
import io
import unittest

from debugger_protocol.schema.__main__ import handle_check


class VendoredSchemaTests(unittest.TestCase):

    def test_matches_upstream(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with contextlib.redirect_stderr(stdout):
                try:
                    handle_check()
                except Exception as exc:
                    self.fail(str(exc))
        result = stdout.getvalue().strip().splitlines()[-1]
        self.assertEqual(result, 'schema file okay')
