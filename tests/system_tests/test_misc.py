import os
import os.path

from tests.helpers.resource import TestResources
from . import (lifecycle_handshake, LifecycleTestsBase, DebugInfo)

TEST_FILES = TestResources.from_module(__name__)


class NoOutputTests(LifecycleTestsBase):
    def run_test_with_no_output(self, debug_info):
        options = {'debugOptions': ['RedirectOutput']}
        with self.start_debugging(debug_info) as dbg:
            session = dbg.session
            lifecycle_handshake(session, debug_info.starttype,
                                options=options)
        out = dbg.adapter._proc.output.decode('utf-8')
        self.assertEqual(out, '')

    def test_with_no_output(self):
        filename = TEST_FILES.resolve('nooutput.py')
        cwd = os.path.dirname(filename)
        self.run_test_with_no_output(
            DebugInfo(filename=filename, cwd=cwd))
