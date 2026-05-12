def test_on_scopes_request_with_valid_frame_id():
    from _pydevd_bundle._debug_adapter import pydevd_schema, pydevd_base_schema
    from _pydevd_bundle.pydevd_process_net_command_json import PyDevJsonCommandProcessor

    processor = PyDevJsonCommandProcessor(pydevd_base_schema.from_json)
    request = pydevd_schema.ScopesRequest(pydevd_schema.ScopesArguments(frameId=1))

    result = processor.on_scopes_request(None, request)
    response = result.as_dict

    assert response["success"] is True
    scopes = response["body"]["scopes"]
    assert len(scopes) == 2
    assert scopes[0]["name"] == "Locals"
    assert scopes[0]["presentationHint"] == "locals"
    assert scopes[1]["name"] == "Globals"


def test_on_scopes_request_with_invalid_frame_id():
    from _pydevd_bundle._debug_adapter import pydevd_schema, pydevd_base_schema
    from _pydevd_bundle.pydevd_process_net_command_json import PyDevJsonCommandProcessor

    processor = PyDevJsonCommandProcessor(pydevd_base_schema.from_json)
    request = pydevd_schema.ScopesRequest(
        pydevd_schema.ScopesArguments(frameId="not_a_number")
    )

    result = processor.on_scopes_request(None, request)
    response = result.as_dict

    assert response["success"] is True
    assert response["body"]["scopes"] == []
