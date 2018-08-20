import os
import os.path
import time

from tests.helpers.debugsession import Awaitable
from tests.helpers.resource import TestResources
from . import (
    _strip_newline_output_events, lifecycle_handshake,
    LifecycleTestsBase, DebugInfo, PORT
)

TEST_FILES = TestResources.from_module(__name__)


class BreakIntoDebuggerTests(LifecycleTestsBase):
    def run_test_attach_or_launch(self, debug_info, end_loop=False):
        options = {'debugOptions': ['RedirectOutput']}
        with self.start_debugging(debug_info) as dbg:
            session = dbg.session
            stopped = session.get_awaiter_for_event('stopped')
            (_, req_launch_attach, _, _, _, _) = lifecycle_handshake(
                session,
                debug_info.starttype,
                options=options)
            Awaitable.wait_all(req_launch_attach, stopped)
            thread_id = stopped.event.body['threadId']
            if end_loop:
                self.set_var_to_end_loop(session, thread_id)
            session.send_request('continue', threadId=thread_id)

        received = list(_strip_newline_output_events(dbg.session.received))
        self.assert_contains(received, [
            self.new_event('output', category='stdout', output='one'),
            self.new_event('output', category='stdout', output='two'),
            self.new_event('continued', threadId=thread_id),
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
        ])

    def set_var_to_end_loop(self, session, thread_id):
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

    def run_test_reattach(self, debug_info):
        options = {'debugOptions': ['RedirectOutput']}
        with self.start_debugging(debug_info) as dbg:
            session = dbg.session
            stopped1 = session.get_awaiter_for_event('stopped')
            (_, req_launch_attach, _, _, _, _) = lifecycle_handshake(
                session,
                debug_info.starttype,
                options=options,
                threads=True)
            Awaitable.wait_all(req_launch_attach, stopped1)

            thread_id = stopped1.event.body['threadId']
            req_disconnect = session.send_request('disconnect', restart=False)
            req_disconnect.wait()

            time.sleep(1)
            (_, req_launch_attach, _, _, _, _) = lifecycle_handshake(
                session,
                debug_info.starttype,
                options=options,
                threads=True)
            Awaitable.wait_all(req_launch_attach)

            self.set_var_to_end_loop(session, thread_id)
            session.send_request('continue', threadId=thread_id)

        received = list(_strip_newline_output_events(session.received))
        self.assert_contains(received, [
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
        ])


class LaunchFileBreakIntoDebuggerTests(BreakIntoDebuggerTests):
    def test_launch_and_break(self):
        for filename in ('launch_test.py', 'launch_test_breakpoint.py'):
            filename = TEST_FILES.resolve(filename)
            cwd = os.path.dirname(filename)
            debug_info = DebugInfo(filename=filename, cwd=cwd)
            self.run_test_attach_or_launch(debug_info)


class LaunchModuleBreakIntoDebuggerTests(BreakIntoDebuggerTests):
    def test_launch_and_break(self):
        for module_name in ('mypkg_launch', 'mypkg_launch_breakpoint'):
            env = TEST_FILES.env_with_py_path()
            cwd = TEST_FILES.parent.root
            self.run_test_attach_or_launch(
                DebugInfo(modulename=module_name, env=env, cwd=cwd))


class ServerAttachBreakIntoDebuggerTests(BreakIntoDebuggerTests):
    def test_attach_and_break(self):
        filename = TEST_FILES.resolve('launch_test.py')
        cwd = os.path.dirname(filename)
        debug_info = DebugInfo(
            filename=filename,
            cwd=cwd,
            starttype='attach',
        )
        self.run_test_attach_or_launch(debug_info)


class ServerAttachModuleBreakIntoDebuggerTests(BreakIntoDebuggerTests):
    def test_attach_and_break(self):
        module_name = 'mypkg_launch'
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.root
        debug_info = DebugInfo(
            modulename=module_name,
            cwd=cwd,
            env=env,
            starttype='attach',
        )
        self.run_test_attach_or_launch(debug_info)


class PTVSDAttachBreakIntoDebuggerTests(BreakIntoDebuggerTests):
    def test_attach_enable_wait_and_break(self):
        # Uses enable_attach followed by wait_for_attach
        # before calling break_into_debugger
        filename = TEST_FILES.resolve('attach_test.py')
        cwd = os.path.dirname(filename)
        debug_info = DebugInfo(
            filename=filename,
            cwd=cwd,
            argv=['localhost', str(PORT)],
            env={'PTVSD_WAIT_FOR_ATTACH': 'True'},
            starttype='attach',
            attachtype='import',
            )
        self.run_test_attach_or_launch(debug_info)

    def test_attach_enable_check_and_break(self):
        # Uses enable_attach followed by a loop that checks if the
        # debugger is attached before calling break_into_debugger
        filename = TEST_FILES.resolve('attach_test.py')
        cwd = os.path.dirname(filename)
        debug_info = DebugInfo(
            filename=filename,
            cwd=cwd,
            argv=['localhost', str(PORT)],
            env={'PTVSD_IS_ATTACHED': 'True'},
            starttype='attach',
            attachtype='import',
            )
        self.run_test_attach_or_launch(debug_info)

    def test_attach_enable_and_break(self):
        # Uses enable_attach followed by break_into_debugger
        # not is_attached check or wait_for_debugger
        filename = TEST_FILES.resolve('attach_test.py')
        cwd = os.path.dirname(filename)
        debug_info = DebugInfo(
            filename=filename,
            cwd=cwd,
            argv=['localhost', str(PORT)],
            starttype='attach',
            attachtype='import',
            )
        self.run_test_attach_or_launch(debug_info, end_loop=True)

    def test_reattach_enable_wait_and_break(self):
        # Uses enable_attach followed by wait_for_attach
        # before calling break_into_debugger
        for filename in ('reattach_test.py', 'reattach_test_breakpoint.py'):
            filename = TEST_FILES.resolve(filename)
            cwd = os.path.dirname(filename)
            debug_info = DebugInfo(
                filename=filename,
                cwd=cwd,
                argv=['localhost', str(PORT)],
                env={'PTVSD_WAIT_FOR_ATTACH': 'True'},
                starttype='attach',
                attachtype='import',
                )
            self.run_test_reattach(debug_info)

    def test_reattach_enable_check_and_break(self):
        # Uses enable_attach followed by a loop that checks if the
        # debugger is attached before calling break_into_debugger
        filename = TEST_FILES.resolve('reattach_test.py')
        cwd = os.path.dirname(filename)
        debug_info = DebugInfo(
            filename=filename,
            cwd=cwd,
            argv=['localhost', str(PORT)],
            env={'PTVSD_IS_ATTACHED': 'True'},
            starttype='attach',
            attachtype='import',
            )
        self.run_test_reattach(debug_info)

    def test_reattach_enable_and_break(self):
        # Uses enable_attach followed by break_into_debugger
        # not is_attached check or wait_for_debugger
        filename = TEST_FILES.resolve('reattach_test.py')
        cwd = os.path.dirname(filename)
        debug_info = DebugInfo(
            filename=filename,
            cwd=cwd,
            argv=['localhost', str(PORT)],
            starttype='attach',
            attachtype='import',
            )
        self.run_test_reattach(debug_info)


class PTVSDAttachModuleBreakIntoDebuggerTests(BreakIntoDebuggerTests):
    def test_attach_enable_wait_and_break(self):
        # Uses enable_attach followed by wait_for_attach
        # before calling break_into_debugger
        module_name = 'mypkg_attach'
        env = TEST_FILES.env_with_py_path()
        env['PTVSD_WAIT_FOR_ATTACH'] = 'True'
        cwd = TEST_FILES.root
        debug_info = DebugInfo(
            modulename=module_name,
            env=env,
            cwd=cwd,
            argv=['localhost', str(PORT)],
            starttype='attach',
            attachtype='import',
            )
        self.run_test_attach_or_launch(debug_info)

    def test_attach_enable_check_and_break(self):
        # Uses enable_attach followed by a loop that checks if the
        # debugger is attached before calling break_into_debugger
        module_name = 'mypkg_attach'
        env = TEST_FILES.env_with_py_path()
        env['PTVSD_IS_ATTACHED'] = 'True'
        cwd = TEST_FILES.root
        debug_info = DebugInfo(
            modulename=module_name,
            env=env,
            cwd=cwd,
            argv=['localhost', str(PORT)],
            starttype='attach',
            attachtype='import',
            )
        self.run_test_attach_or_launch(debug_info)

    def test_attach_enable_and_break(self):
        # Uses enable_attach followed by break_into_debugger
        # not is_attached check or wait_for_debugger
        module_name = 'mypkg_attach'
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.root
        debug_info = DebugInfo(
            modulename=module_name,
            env=env,
            cwd=cwd,
            argv=['localhost', str(PORT)],
            starttype='attach',
            attachtype='import',
            )
        self.run_test_attach_or_launch(debug_info, end_loop=True)

    def test_reattach_enable_wait_and_break(self):
        # Uses enable_attach followed by wait_for_attach
        # before calling break_into_debugger
        module_name = 'mypkg_reattach'
        env = TEST_FILES.env_with_py_path()
        env['PTVSD_WAIT_FOR_ATTACH'] = 'True'
        cwd = TEST_FILES.root
        debug_info = DebugInfo(
            modulename=module_name,
            env=env,
            cwd=cwd,
            argv=['localhost', str(PORT)],
            starttype='attach',
            attachtype='import',
            )
        self.run_test_reattach(debug_info)

    def test_reattach_enable_check_and_break(self):
        # Uses enable_attach followed by a loop that checks if the
        # debugger is attached before calling break_into_debugger
        for module_name in ('mypkg_reattach', 'mypkg_reattach_breakpoint'):
            env = TEST_FILES.env_with_py_path()
            env['PTVSD_IS_ATTACHED'] = 'True'
            cwd = TEST_FILES.root
            debug_info = DebugInfo(
                modulename=module_name,
                env=env,
                cwd=cwd,
                argv=['localhost', str(PORT)],
                starttype='attach',
                attachtype='import',
                )
            self.run_test_reattach(debug_info)

    def test_reattach_enable_and_break(self):
        # Uses enable_attach followed by break_into_debugger
        # not is_attached check or wait_for_debugger
        module_name = 'mypkg_reattach'
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.root
        debug_info = DebugInfo(
            modulename=module_name,
            env=env,
            cwd=cwd,
            argv=['localhost', str(PORT)],
            starttype='attach',
            attachtype='import',
            )
        self.run_test_reattach(debug_info)
