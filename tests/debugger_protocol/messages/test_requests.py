import unittest

from debugger_protocol.messages import requests


class RequestsTests(unittest.TestCase):

    def test_implicit___all__(self):
        names = set(name
                    for name in vars(requests)
                    if not name.startswith('__'))

        self.assertEqual(names, {
            'ErrorResponse',
            'RunInTerminalRequest',
            'RunInTerminalResponse',
            'InitializeRequest',
            'InitializeResponse',
            'ConfigurationDoneRequest',
            'ConfigurationDoneResponse',
            'LaunchRequest',
            'LaunchResponse',
            'AttachRequest',
            'AttachResponse',
            'RestartRequest',
            'RestartResponse',
            'DisconnectRequest',
            'DisconnectResponse',
            'SetBreakpointsRequest',
            'SetBreakpointsResponse',
            'SetFunctionBreakpointsRequest',
            'SetFunctionBreakpointsResponse',
            'SetExceptionBreakpointsRequest',
            'SetExceptionBreakpointsResponse',
            'ContinueRequest',
            'ContinueResponse',
            'NextRequest',
            'NextResponse',
            'StepInRequest',
            'StepInResponse',
            'StepOutRequest',
            'StepOutResponse',
            'StepBackRequest',
            'StepBackResponse',
            'ReverseContinueRequest',
            'ReverseContinueResponse',
            'RestartFrameRequest',
            'RestartFrameResponse',
            'GotoRequest',
            'GotoResponse',
            'PauseRequest',
            'PauseResponse',
            'StackTraceRequest',
            'StackTraceResponse',
            'ScopesRequest',
            'ScopesResponse',
            'VariablesRequest',
            'VariablesResponse',
            'SetVariableRequest',
            'SetVariableResponse',
            'SourceRequest',
            'SourceResponse',
            'ThreadsRequest',
            'ThreadsResponse',
            'ModulesRequest',
            'ModulesResponse',
            'LoadedSourcesRequest',
            'LoadedSourcesResponse',
            'EvaluateRequest',
            'EvaluateResponse',
            'StepInTargetsRequest',
            'StepInTargetsResponse',
            'GotoTargetsRequest',
            'GotoTargetsResponse',
            'CompletionsRequest',
            'CompletionsResponse',
            'ExceptionInfoRequest',
            'ExceptionInfoResponse',
        })


# TODO: Add tests for every request/response type.

#class TestBase:
#
#    NAME = None
#    EVENT = None
#    BODY = None
#    BODY_MIN = None
#
#    def test_event_full(self):
#        event = self.EVENT(self.BODY, seq=9)
#
#        self.assertEqual(event.event, self.NAME)
#        self.assertEqual(event.body, self.BODY)
#
#    def test_event_minimal(self):
#        event = self.EVENT(self.BODY_MIN, seq=9)
#
#        self.assertEqual(event.body, self.BODY_MIN)
#
#    def test_event_empty_body(self):
#        if self.BODY_MIN:
#            with self.assertRaises(TypeError):
#                self.EVENT({}, seq=9)
#
#    def test_from_data(self):
#        event = self.EVENT.from_data(
#            type='event',
#            seq=9,
#            event=self.NAME,
#            body=self.BODY,
#        )
#
#        self.assertEqual(event.body, self.BODY)
#
#    def test_as_data(self):
#        event = self.EVENT(self.BODY, seq=9)
#        data = event.as_data()
#
#        self.assertEqual(data, {
#            'type': 'event',
#            'seq': 9,
#            'event': self.NAME,
#            'body': self.BODY,
#        })
