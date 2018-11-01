def test_completions(debug_session, simple_hit_paused_on_break):
    hit = simple_hit_paused_on_break

    response = debug_session.send_request('completions', arguments={
        'frameId': hit.frame_id,
        'text': 'b.'
    }).wait_for_response()

    labels = set(target['label'] for target in response.body['targets'])
    assert labels.issuperset(['get', 'items', 'keys', 'setdefault', 'update', 'values'])

    response = debug_session.send_request('completions', arguments={
        'frameId': hit.frame_id,
        'text': 'not_there'
    }).wait_for_response()

    assert not response.body['targets']
