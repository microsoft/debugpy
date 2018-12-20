from _pydevd_bundle._debug_adapter.pydevd_schema import InitializeRequest, \
    InitializeRequestArguments, InitializeResponse, Capabilities
from _pydevd_bundle._debug_adapter import pydevd_schema, pydevd_base_schema


def test_schema():
    
    json_msg = '''
{
    "arguments": {
        "adapterID": "pydevd",
        "clientID": "vscode", 
        "clientName": "Visual Studio Code", 
        "columnsStartAt1": true, 
        "linesStartAt1": true, 
        "locale": "en-us", 
        "pathFormat": "path", 
        "supportsRunInTerminalRequest": true, 
        "supportsVariablePaging": true, 
        "supportsVariableType": true
    }, 
    "command": "initialize", 
    "seq": 1, 
    "type": "request"
}'''
    
    initialize_request = pydevd_base_schema.from_json(json_msg)
    assert initialize_request.__class__ == InitializeRequest
    assert initialize_request.arguments.__class__ == InitializeRequestArguments
    assert initialize_request.arguments.adapterID == 'pydevd'
    assert initialize_request.command == 'initialize'
    assert initialize_request.type == 'request'
    assert initialize_request.seq == 1
    
    response = pydevd_base_schema.build_response(initialize_request)
    assert response.__class__ == InitializeResponse
    assert response.seq == -1  # Must be set before sending
    assert response.command == 'initialize'
    assert response.type == 'response'
    assert response.body.__class__ == Capabilities
    
    assert response.to_dict() == {
        "seq":-1,
        "type": "response",
        "request_seq": 1,
        "success": True,
        "command": "initialize",
        "body": {}
    } 
    
    capabilities = response.body  # : :type capabilities: Capabilities
    capabilities.supportsCompletionsRequest = True
    assert response.to_dict() == {
        "seq":-1,
        "type": "response",
        "request_seq": 1,
        "success": True,
        "command": "initialize",
        "body": {'supportsCompletionsRequest':True}
    } 

    initialize_event = pydevd_schema.InitializedEvent()
    assert initialize_event.to_dict() == {
        "seq": -1, 
        "type": "event", 
        "event": "initialized"
    }
