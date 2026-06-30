def evaluate(trace):
    calls = trace.get('tool_calls', []) or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls to assess cross-checking.', 'evidence_refs': []}
    if len(calls) < 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Only one tool call; no secondary tool result available for cross-check.', 'evidence_refs': [{'type': 'tool_calls', 'count': len(calls)}]}
    names = [c.get('name') for c in calls]
    unique = set(names)
    # Group tool calls by 'topic' approximated via overlapping argument values
    def args_values(c):
        a = c.get('arguments') or {}
        if isinstance(a, dict):
            return {str(v).lower() for v in a.values() if isinstance(v, (str, int, float))}
        return set()
    cross_checked = 0
    total = len(calls)
    for i, c in enumerate(calls):
        vi = args_values(c)
        ni = c.get('name')
        found = False
        for j, d in enumerate(calls):
            if i == j: continue
            if d.get('name') == ni: continue
            vj = args_values(d)
            if vi and vj and (vi & vj):
                found = True
                break
        if found:
            cross_checked += 1
    if total > 0 and cross_checked == total:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': f'All {total} tool calls share argument overlap with a call from a different tool, suggesting cross-checks.', 'evidence_refs': [{'type': 'tool_names', 'value': sorted(unique)}]}
    if cross_checked == 0:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No tool observation appears cross-checked by a secondary tool with overlapping arguments.', 'evidence_refs': [{'type': 'tool_names', 'value': sorted(unique)}]}
    return {'observed_followed': False, 'confidence': 'low', 'reason': f'Only {cross_checked} of {total} tool observations show cross-check overlap with a secondary tool.', 'evidence_refs': [{'type': 'tool_names', 'value': sorted(unique)}]}
