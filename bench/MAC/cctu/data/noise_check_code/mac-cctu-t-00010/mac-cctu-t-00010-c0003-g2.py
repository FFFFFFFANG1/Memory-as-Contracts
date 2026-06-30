def evaluate(trace):
    tcs = trace.get('tool_calls') or []
    final = (trace.get('final_response') or '').strip()
    if not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response to assess.', 'evidence_refs': []}
    successful = [t for t in tcs if t.get('result') is not None]
    if len(successful) < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Only {len(successful)} tool outputs; cross-referencing against >=2 independent sources is impossible.', 'evidence_refs': [t.get('name') for t in successful]}
    distinct_tools = {t.get('name') for t in successful}
    if len(distinct_tools) < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'All tool outputs come from a single tool; lacks independent cross-reference.', 'evidence_refs': list(distinct_tools)}
    return {'observed_followed': None, 'confidence': 'low', 'reason': 'Multiple distinct tool outputs exist, but per-fact cross-referencing cannot be verified automatically.', 'evidence_refs': list(distinct_tools)}
