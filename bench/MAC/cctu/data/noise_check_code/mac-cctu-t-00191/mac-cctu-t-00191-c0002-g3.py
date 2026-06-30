def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls to evaluate cross-checking.', 'evidence_refs': []}
    names = [c.get('name') for c in calls if c.get('name')]
    distinct = set(names)
    if len(distinct) < 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Only one distinct tool used ({list(distinct)}); no alternative tool available for cross-checking.', 'evidence_refs': [{'tools_used': list(distinct)}]}
    # Check that for each tool whose result is used, another tool is also called
    # Heuristic: at least 2 distinct tools and total calls >= 2 per topic
    if len(calls) < 2 * len(distinct) - 1 and len(calls) < len(distinct) + 1:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'Multiple tools used but unclear whether each source was cross-checked.', 'evidence_refs': [{'call_count': len(calls), 'distinct': list(distinct)}]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'{len(distinct)} distinct tools invoked across {len(calls)} calls, consistent with cross-checking sources.', 'evidence_refs': [{'tools_used': list(distinct), 'call_count': len(calls)}]}
