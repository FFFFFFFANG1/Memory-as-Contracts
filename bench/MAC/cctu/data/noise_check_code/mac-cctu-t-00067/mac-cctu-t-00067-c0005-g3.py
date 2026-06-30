def evaluate(trace):
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    trajectory = trace.get('trajectory') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    tool_names = [str(call.get('name') or '') for call in tool_calls if call.get('name')]
    called = {name for name in tool_names if name}
    required_tools = ['academic_founder_identifier', 'academic_institution_locator', 'biographical_info_retriever', 'cultural_artifact_identifier', 'geographer_identifier', 'institution_location_finder', 'river_locator', 'river_source_locator']
    missing = sorted(t for t in required_tools if t not in called)
    if missing:
        reasons.append('required tools not called: ' + ', '.join(missing[:5]))
    tool_count = len(tool_names)
    if tool_count > 10:
        reasons.append('tool call count {tool_count} above 10')
    round_count = len(trajectory)
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
