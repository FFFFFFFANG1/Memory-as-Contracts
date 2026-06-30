def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls', []) or []
    final = trace.get('final_response', '') or ''
    cgi_calls = [tc for tc in tool_calls if (tc.get('name') or '') == 'conflict_group_identifier']
    if not cgi_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'conflict_group_identifier was not invoked for any faction', 'evidence_refs': []}
    # Collect faction names referenced in cgi calls to cross-check enumeration
    factions = []
    for tc in cgi_calls:
        args = tc.get('arguments') or {}
        if isinstance(args, dict):
            for v in args.values():
                if isinstance(v, str) and v.strip():
                    factions.append(v.strip())
    if not final.strip():
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'No final response to inspect for enumeration', 'evidence_refs': []}
    # Need a comma-separated list of groups
    has_comma_list = ',' in final
    if not has_comma_list:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Final response does not contain a comma-separated list of groups', 'evidence_refs': []}
    # Check that faction names from tool calls appear in final response
    missing = [f for f in factions if f and f.lower() not in final.lower()]
    if missing:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Factions queried but not enumerated in answer: {missing[:5]}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'conflict_group_identifier invoked per faction and final answer enumerates groups in comma-separated list', 'evidence_refs': []}
