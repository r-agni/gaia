from agents.output_parser import parse_llm_actions, parse_llm_output


def test_parse_guess_with_lat_lon_aliases():
    text = '{"action_type":"guess","lat":37.7749,"lon":-122.4194,"reasoning":"city grid + bay"}'
    action = parse_llm_output(text)
    assert action.action_type == "guess"
    assert action.guess_lat == 37.7749
    assert action.guess_lon == -122.4194


def test_parse_guess_missing_coords_falls_back_to_centroid():
    text = '{"action_type":"guess","reasoning":"I think Europe"}'
    action = parse_llm_output(text)
    assert action.action_type == "guess"
    assert action.guess_lat == 20.0
    assert action.guess_lon == 15.0


def test_parse_tool_call_with_nested_tool_params():
    text = (
        '{"action_type":"tool_call","tool_name":"street_view",'
        '"tool_params":{"heading":120,"meta":{"zoom":2}},"reasoning":"check signs"}'
    )
    actions = parse_llm_actions(text)
    assert len(actions) == 1
    assert actions[0].action_type == "tool_call"
    assert actions[0].tool_name == "street_view"
    assert actions[0].tool_params == {"heading": 120, "meta": {"zoom": 2}}
