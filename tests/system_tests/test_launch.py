# import os
# import os.path
# from textwrap import dedent
# import unittest

# import ptvsd
# from ptvsd.wrapper import INITIALIZE_RESPONSE  # noqa
# from tests.helpers.debugclient import EasyDebugClient as DebugClient
# from tests.helpers.debugsession import Awaitable

# from . import (
#     _strip_newline_output_events,
#     lifecycle_handshake,
#     LifecycleTestsBase,
# )

# ROOT = os.path.dirname(os.path.dirname(ptvsd.__file__))
# PORT = 9876
# CONNECT_TIMEOUT = 3.0


# class FileLifecycleTests(LifecycleTestsBase):
#     IS_MODULE = False

#     def test_with_arguments(self):
#         source = dedent("""
#             import sys
#             print(len(sys.argv))
#             for arg in sys.argv:
#                 print(arg)
#             """)
#         options = {"debugOptions": ["RedirectOutput"]}
#         (filename, filepath, env, expected_module, argv,
#          cwd) = self.get_test_info(source)

#         with DebugClient(port=PORT, connecttimeout=CONNECT_TIMEOUT) as editor: # noqa
#             adapter, session = editor.host_local_debugger(
#                 argv=argv + ["1", "Hello", "World"], env=env,
#                 cwd=cwd, timeout=CONNECT_TIMEOUT)
#             terminated = session.get_awaiter_for_event('terminated')
#             thread_exit = session.get_awaiter_for_event('thread', lambda msg: msg.body.get("reason", "") == "exited") # noqa
#             with session.wait_for_event("exited"):
#                 with session.wait_for_event("thread"):
#                     (
#                         req_initialize,
#                         req_launch,
#                         req_config,
#                         _,
#                         _,
#                         _,
#                     ) = lifecycle_handshake(
#                         session, "launch", options=options)

#             adapter.wait()
#             Awaitable.wait_all(terminated, thread_exit)

#         # Skipping the 'thread exited' and 'terminated' messages which
#         # may appear randomly in the received list.
#         received = list(_strip_newline_output_events(session.received))
#         self.assert_contains(
#             received,
#             [
#                 self.new_version_event(session.received),
#                 self.new_response(req_initialize.req, **INITIALIZE_RESPONSE),
#                 self.new_event("initialized"),
#                 self.new_response(req_launch.req),
#                 self.new_response(req_config.req),
#                 self.new_event(
#                     "process", **{
#                         "isLocalProcess": True,
#                         "systemProcessId": adapter.pid,
#                         "startMethod": "launch",
#                         "name": expected_module,
#                     }),
#                 self.new_event("thread", reason="started", threadId=1),
#                 self.new_event("output", category="stdout", output="4"),
#                 self.new_event("output", category="stdout", output=expected_module), # noqa
#                 self.new_event("output", category="stdout", output="1"),
#                 self.new_event("output", category="stdout", output="Hello"),
#                 self.new_event("output", category="stdout", output="World"),
#             ],
#         )
