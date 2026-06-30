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
    tool_count = len(tool_names)
    _count_political_successor_finder = sum(1 for name in tool_names if name == 'political_successor_finder')
    if _count_political_successor_finder > 1:
        reasons.append('political_successor_finder' + ' call count ' + str(_count_political_successor_finder) + ' above 1')
    round_count = len(trajectory)
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
