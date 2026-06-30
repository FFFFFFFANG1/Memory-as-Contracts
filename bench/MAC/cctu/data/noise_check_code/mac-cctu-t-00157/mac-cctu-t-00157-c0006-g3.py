def evaluate(trace):
    import json
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    trajectory = trace.get('trajectory') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    parsed_json = None
    try:
        parsed_json = json.loads(response.strip())
    except Exception:
        parsed_json = None
    if not isinstance(parsed_json, dict):
        reasons.append('valid json object missing')
    tool_names = [str(call.get('name') or '') for call in tool_calls if call.get('name')]
    called = {name for name in tool_names if name}
    required_tools = ['historical_leader_infrastructure_finder', 'historical_road_length_calculator', 'literary_search_tool']
    missing = sorted(t for t in required_tools if t not in called)
    if missing:
        reasons.append('required tools not called: ' + ', '.join(missing[:5]))
    round_count = len(trajectory)
    if response.strip() and not response.rstrip().endswith('.'):
        reasons.append('response does not end with period')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
