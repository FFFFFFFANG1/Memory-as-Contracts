def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No tool calls; cannot cross-reference facts.', 'evidence_refs': []}
    names = [c.get('name') for c in calls if c.get('name')]
    distinct = set(names)
    successful = [c for c in calls if c.get('result') not in (None, '', {}, [])]
    distinct_success = set(c.get('name') for c in successful if c.get('name'))
    final = (trace.get('final_response') or '').strip()
    if len(distinct_success) < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Only {len(distinct_success)} distinct tool(s) produced output; cannot cross-reference against two independent sources.', 'evidence_refs': [{'tools_used': sorted(distinct)}]}
    # Heuristic: with >=2 distinct successful tool outputs prior to final response, cross-referencing is plausible but not verifiable from trace alone.
    if not final:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'Multiple tool outputs present but no final response to assess cross-referencing.', 'evidence_refs': [{'tools_used': sorted(distinct_success)}]}
    return {'observed_followed': None, 'confidence': 'low', 'reason': 'At least two independent tool outputs exist before final response; whether every fact was cross-referenced is semantic and not directly verifiable.', 'evidence_refs': [{'tools_used': sorted(distinct_success), 'total_calls': len(calls)}]}
