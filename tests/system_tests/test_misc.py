import os
import os.path
import time
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


class ThreadCountTests(LifecycleTestsBase):
    def run_test_threads(self, debug_info, bp_filename, bp_line, count):
        breakpoints = [{
            'source': {
                'path': bp_filename
            },
            'breakpoints': [{
                'line': bp_line
            }]
        }]
        with self.start_debugging(debug_info) as dbg:
            session = dbg.session
            with session.wait_for_event('stopped') as result:
                lifecycle_handshake(
                                    session, debug_info.starttype,
                                    breakpoints=breakpoints,
                                    threads=True)
            # Give extra time for thread state to be captured
            time.sleep(1)
            event = result['msg']
            tid = event.body['threadId']
            req_threads = session.send_request('threads')
            req_threads.wait()
            threads = req_threads.resp.body['threads']

            session.send_request('continue', threadId=tid)

        self.assertEqual(count, len(threads))

    def test_single_thread(self):
        filename = TEST_FILES.resolve('single_thread.py')
        cwd = os.path.dirname(filename)
        self.run_test_threads(
            DebugInfo(filename=filename, cwd=cwd),
            bp_filename=filename, bp_line=2, count=1)

    def test_multi_thread(self):
        filename = TEST_FILES.resolve('three_threads.py')
        cwd = os.path.dirname(filename)
        self.run_test_threads(
            DebugInfo(filename=filename, cwd=cwd),
            bp_filename=filename, bp_line=22, count=3)
