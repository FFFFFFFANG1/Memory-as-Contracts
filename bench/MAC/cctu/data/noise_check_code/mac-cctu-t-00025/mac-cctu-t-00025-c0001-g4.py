def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No tool calls; cross-verification impossible.', 'evidence_refs': []}
    names = [c.get('name') for c in calls if c.get('name')]
    distinct = set(names)
    if len(distinct) < 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Only {len(distinct)} distinct tool(s) used: {sorted(distinct)}. Cross-verification requires >=2 independent tools.', 'evidence_refs': list(distinct)}
    final = (trace.get('final_response') or '').strip()
    if not final:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'No final response to assess fact inclusion.', 'evidence_refs': sorted(distinct)}
    return {'observed_followed': None, 'confidence': 'low', 'reason': f'{len(distinct)} distinct tools were invoked ({sorted(distinct)}), but per-fact cross-verification cannot be confirmed automatically.', 'evidence_refs': sorted(distinct)}
