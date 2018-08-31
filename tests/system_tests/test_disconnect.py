import os
import os.path
import random

from tests.helpers.resource import TestResources
from . import (
    lifecycle_handshake,
    LifecycleTestsBase, DebugInfo, PORT
)

TEST_FILES = TestResources.from_module(__name__)


class CheckFile(object):
    def __init__(self, root):
        self._root = root

    def __enter__(self):
        self._path = self._get_check_file_name(self._root)
        return self

    def __exit__(self, *args):
        if os.path.exists(self._path):
            os.remove(self._path)

    @property
    def filepath(self):
        return self._path

    def _get_check_file_name(self, root):
        name = 'test_%d.txt' % random.randint(10000, 99999)
        path = os.path.join(root, name)
        if os.path.exists(path):
            os.remove(path)
        return path


class ContinueOnDisconnectTests(LifecycleTestsBase):
    def _wait_for_output(self, session):
        count = 0
        while count < 3:
            events = self.find_events(session.received, 'output')
            for e in events:
                try:
                    # the test outputs a number when it reaches the
                    # right spot
                    int(e.body['output'])
                    return
                except ValueError:
                    pass
            count += 1
            try:
                outevent = session.get_awaiter_for_event('output')
                outevent.wait(timeout=3.0)
            except Exception:
                pass

    def run_test_attach_disconnect(self, debug_info, path_to_check,
                                   pause=False):
        options = {'debugOptions': ['RedirectOutput']}
        with self.start_debugging(debug_info) as dbg:
            session = dbg.session
            stopped = session.get_awaiter_for_event('stopped')
            (_, req_launch_attach, _, _, _, req_threads
             ) = lifecycle_handshake(
                 session, debug_info.starttype,
                 options=options, threads=True)
            req_launch_attach.wait(timeout=3.0)
            req_threads.wait(timeout=2.0)

            # ensure we see a output
            self._wait_for_output(session)

            if pause:
                req_pause = session.send_request('pause', threadId=0)
                req_pause.wait(timeout=3.0)

            stopped.wait(timeout=2.0)
            thread_id = stopped.event.body['threadId']
            self._set_var_to_end_loop(session, thread_id)

            session.send_request('disconnect', restart=False)

        if debug_info.starttype == 'launch':
            self.assertFalse(os.path.exists(path_to_check))
        else:
            self.assertTrue(os.path.exists(path_to_check))
            with open(path_to_check, 'r') as f:
                self.assertEqual('HERE :)\n', f.read())

    def _set_var_to_end_loop(self, session, thread_id):
        # Set count > 1000 to end the loop
        req_stacktrace = session.send_request(
            'stackTrace',
            threadId=thread_id,
        )
        req_stacktrace.wait()
        frames = req_stacktrace.resp.body['stackFrames']
        frame_id = frames[0]['id']
        req_scopes = session.send_request(
            'scopes',
            frameId=frame_id,
        )
        req_scopes.wait()
        scopes = req_scopes.resp.body['scopes']
        variables_reference = scopes[0]['variablesReference']
        req_setvar = session.send_request(
                'setVariable',
                variablesReference=variables_reference,
                name='count',
                value='1000'
            )
        req_setvar.wait()


class LaunchFileDisconnectLifecycleTests(ContinueOnDisconnectTests):
    def test_launch_pause_disconnect(self):
        filename = TEST_FILES.resolve('disconnect_test.py')
        cwd = os.path.dirname(filename)

        with CheckFile(cwd) as cf:
            debug_info = DebugInfo(
                filename=filename,
                cwd=cwd,
                env={
                    'PTVSD_TARGET_FILE': cf.filepath,
                },
            )
            self.run_test_attach_disconnect(
                debug_info, cf.filepath, pause=True)

    def test_launch_break_disconnect(self):
        filename = TEST_FILES.resolve('disconnect_test.py')
        cwd = os.path.dirname(filename)

        with CheckFile(cwd) as cf:
            debug_info = DebugInfo(
                filename=filename,
                cwd=cwd,
                env={
                    'PTVSD_TARGET_FILE': cf.filepath,
                    'PTVSD_BREAK_INTO_DEBUGGER': 'True',
                }
            )
            self.run_test_attach_disconnect(
                debug_info, cf.filepath)


class LaunchModuleDisconnectLifecycleTests(ContinueOnDisconnectTests):
    def test_launch_pause_disconnect(self):
        module_name = 'mypkg'
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.parent.root
        with CheckFile(cwd) as cf:
            env['PTVSD_TARGET_FILE'] = cf.filepath
            debug_info = DebugInfo(
                modulename=module_name,
                cwd=cwd,
                env=env
            )
            self.run_test_attach_disconnect(
                debug_info, cf.filepath, pause=True)

    def test_launch_break_disconnect(self):
        module_name = 'mypkg'
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.parent.root
        with CheckFile(cwd) as cf:
            env['PTVSD_TARGET_FILE'] = cf.filepath
            env['PTVSD_BREAK_INTO_DEBUGGER'] = 'True'
            debug_info = DebugInfo(
                modulename=module_name,
                cwd=cwd,
                env=env,
            )
            self.run_test_attach_disconnect(
                debug_info, cf.filepath)


class ServerAttachDisconnectLifecycleTests(ContinueOnDisconnectTests):
    def run_test(self, env, pause=False):
        filename = TEST_FILES.resolve('disconnect_test.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        with CheckFile(cwd) as cf:
            env['PTVSD_TARGET_FILE'] = cf.filepath
            debug_info = DebugInfo(
                filename=filename,
                cwd=cwd,
                argv=argv,
                env=env,
                starttype='attach',
            )
            self.run_test_attach_disconnect(
                debug_info, cf.filepath, pause=pause)

    def test_attach_pause_disconnect(self):
        env = {}
        self.run_test(env, pause=True)

    def test_attach_break_disconnect(self):
        env = {
            'PTVSD_BREAK_INTO_DEBUGGER': 'True',
            # this case should NOT use PTVSD_ENABLE_ATTACH
        }
        self.run_test(env)

    def test_attach_check_disconnect(self):
        env = {
            'PTVSD_BREAK_INTO_DEBUGGER': 'True',
            # this case should NOT use PTVSD_ENABLE_ATTACH
            'PTVSD_IS_ATTACHED': 'True',
        }
        self.run_test(env)


class PTVSDAttachDisconnectLifecycleTests(ContinueOnDisconnectTests):
    def run_test(self, env, pause=False):
        filename = TEST_FILES.resolve('disconnect_test.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        with CheckFile(cwd) as cf:
            env['PTVSD_TARGET_FILE'] = cf.filepath
            debug_info = DebugInfo(
                filename=filename,
                cwd=cwd,
                argv=argv,
                env=env,
                starttype='attach',
                attachtype='import',
            )
            self.run_test_attach_disconnect(
                debug_info, cf.filepath, pause=pause)

    def test_enable_attach_pause_disconnect(self):
        env = {
            'PTVSD_ENABLE_ATTACH': 'True',
        }
        self.run_test(env, pause=True)

    def test_enable_attach_break_disconnect(self):
        env = {
            'PTVSD_ENABLE_ATTACH': 'True',
            'PTVSD_BREAK_INTO_DEBUGGER': 'True',
        }
        self.run_test(env)

    def test_enable_attach_wait_disconnect(self):
        env = {
            'PTVSD_ENABLE_ATTACH': 'True',
            'PTVSD_WAIT_FOR_ATTACH': 'True',
            'PTVSD_BREAK_INTO_DEBUGGER': 'True',
        }
        self.run_test(env)

    def test_enable_attach_check_disconnect(self):
        env = {
            'PTVSD_ENABLE_ATTACH': 'True',
            'PTVSD_IS_ATTACHED': 'True',
            'PTVSD_BREAK_INTO_DEBUGGER': 'True',
        }
        self.run_test(env)


class PTVSDModuleAttachDisconnectLifecycleTests(ContinueOnDisconnectTests):
    def run_test(self, env, pause=False):
        module_name = 'mypkg'
        env.update(TEST_FILES.env_with_py_path())
        cwd = TEST_FILES.root
        argv = ['localhost', str(PORT)]
        with CheckFile(cwd) as cf:
            env['PTVSD_TARGET_FILE'] = cf.filepath
            debug_info = DebugInfo(
                modulename=module_name,
                cwd=cwd,
                argv=argv,
                env=env,
                starttype='attach',
                attachtype='import',
            )
            self.run_test_attach_disconnect(
                debug_info, cf.filepath, pause=pause)

    def test_enable_attach_pause_disconnect(self):
        env = {
            'PTVSD_ENABLE_ATTACH': 'True',
        }
        self.run_test(env, pause=True)

    def test_enable_attach_break_disconnect(self):
        env = {
            'PTVSD_ENABLE_ATTACH': 'True',
            'PTVSD_BREAK_INTO_DEBUGGER': 'True',
        }
        self.run_test(env)

    def test_enable_attach_wait_disconnect(self):
        env = {
            'PTVSD_ENABLE_ATTACH': 'True',
            'PTVSD_WAIT_FOR_ATTACH': 'True',
            'PTVSD_BREAK_INTO_DEBUGGER': 'True',
        }
        self.run_test(env)

    def test_enable_attach_check_disconnect(self):
        env = {
            'PTVSD_ENABLE_ATTACH': 'True',
            'PTVSD_IS_ATTACHED': 'True',
            'PTVSD_BREAK_INTO_DEBUGGER': 'True',
        }
        self.run_test(env)
