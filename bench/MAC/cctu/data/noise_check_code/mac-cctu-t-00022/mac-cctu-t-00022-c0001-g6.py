def evaluate(trace):
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no tool calls observed for exploratory scoping', 'evidence_refs': []}
    scoping_tools = {'political_term_tracker', 'election_result_finder'}
    scoping_calls = [c for c in tool_calls if str(c.get('name') or '') in scoping_tools]
    total = len(tool_calls)
    scoping_count = len(scoping_calls)
    if scoping_count == 0:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no calls to political_term_tracker or election_result_finder during scoping', 'evidence_refs': []}
    if scoping_count > 5:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'{scoping_count} scoping calls exceed cap of 5', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'{scoping_count} scoping call(s) to allowed tools within cap of 5', 'evidence_refs': []}
