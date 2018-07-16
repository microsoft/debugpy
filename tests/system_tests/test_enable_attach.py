import unittest

from ptvsd.socket import Address
from tests import PROJECT_ROOT
from tests.helpers.debugadapter import DebugAdapter
from tests.helpers.debugclient import EasyDebugClient as DebugClient
from tests.helpers.lock import LockTimeoutError
from tests.helpers.script import set_lock, set_release, find_line
from . import LifecycleTestsBase, PORT, lifecycle_handshake


class EnableAttachTests(LifecycleTestsBase, unittest.TestCase):

    def test_does_not_block(self):
        addr = Address('localhost', PORT)
        filename = self.write_script('spam.py', """
            import sys
            sys.path.insert(0, {!r})
            import ptvsd
            ptvsd.enable_attach({}, redirect_output=False)
            # <ready>
            """.format(PROJECT_ROOT, tuple(addr)),
        )
        lockfile = self.workspace.lockfile()
        _, wait = set_release(filename, lockfile, 'ready')

        #DebugAdapter.VERBOSE = True
        adapter = DebugAdapter.start_embedded(addr, filename)
        with adapter:
            wait(timeout=3)
            adapter.wait()

    @unittest.skip('fails due to "stopped" event never happening')
    def test_never_call_wait_for_attach(self):
        addr = Address('localhost', PORT)
        filename = self.write_script('spam.py', """
            import sys
            import threading
            import time

            sys.path.insert(0, {!r})
            import ptvsd
            ptvsd.enable_attach({}, redirect_output=False)
            # <ready>
            print('== ready ==')

            # Allow tracing to be triggered.
            def wait():
                # <wait>
                pass
            t = threading.Thread(target=wait)
            t.start()
            for _ in range(100):  # 10 seconds
                print('-----')
                t.join(0.1)
                if not t.is_alive():
                    break
            t.join()

            print('== starting ==')
            # <bp>
            print('== done ==')
            """.format(PROJECT_ROOT, tuple(addr)),
        )
        lockfile1 = self.workspace.lockfile('ready.lock')
        _, wait = set_release(filename, lockfile1, 'ready')
        lockfile2 = self.workspace.lockfile('wait.log')
        done, script = set_lock(filename, lockfile2, 'wait')

        bp = find_line(script, 'bp')
        breakpoints = [{
            'source': {'path': filename},
            'breakpoints': [
                {'line': bp},
            ],
        }]

        #DebugAdapter.VERBOSE = True
        #DebugClient.SESSION.VERBOSE = True
        adapter = DebugAdapter.start_embedded(addr, filename)
        with adapter:
            # Wait longer that WAIT_TIMEOUT, so that debugging isn't
            # immediately enabled in the script's thread.
            wait(timeout=3.0)

            with DebugClient() as editor:
                session = editor.attach_socket(addr, adapter, timeout=1)
                with session.wait_for_event('thread') as result:
                    lifecycle_handshake(session, 'attach',
                                        breakpoints=breakpoints,
                                        threads=True)
                event = result['msg']
                tid = event.body['threadId']

                with session.wait_for_event('stopped'):
                    done()
                session.send_request('continue', threadId=tid)

                adapter.wait()
        out = str(adapter.output)

        self.assertIn('== ready ==', out)
        self.assertIn('== starting ==', out)

    def test_wait_for_attach(self):
        addr = Address('localhost', PORT)
        filename = self.write_script('spam.py', """
            import sys
            sys.path.insert(0, {!r})
            import ptvsd
            ptvsd.enable_attach({}, redirect_output=False)

            ptvsd.wait_for_attach()
            # <ready>
            # <wait>
            """.format(PROJECT_ROOT, tuple(addr)),
        )
        lockfile1 = self.workspace.lockfile()
        _, wait = set_release(filename, lockfile1, 'ready')
        lockfile2 = self.workspace.lockfile()
        done, _ = set_lock(filename, lockfile2, 'wait')

        adapter = DebugAdapter.start_embedded(addr, filename)
        with adapter:
            with DebugClient() as editor:
                session = editor.attach_socket(addr, adapter, timeout=1)
                # Ensure that it really does wait.
                with self.assertRaises(LockTimeoutError):
                    wait(timeout=0.5)

                lifecycle_handshake(session, 'attach')
                wait(timeout=1)
                done()
                adapter.wait()
