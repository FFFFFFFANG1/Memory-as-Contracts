def evaluate(trace):
    import re
    final = (trace.get('final_response') or '')
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found to assess cross-verification.', 'evidence_refs': []}
    distinct = {c.get('name') for c in calls if c.get('name')}
    multi_tool = len(distinct) >= 2 or len(calls) >= 2
    low = final.lower()
    has_appendix = bool(re.search(r'append(ix|dix)', low))
    mentions_discrepancy = bool(re.search(r'discrepan|conflict|disagree|mismatch|no discrepanc', low))
    if multi_tool and has_appendix and mentions_discrepancy:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Multiple tool invocations present and final response includes an appendix addressing discrepancies.', 'evidence_refs': [{'type':'tool_calls','count':len(calls),'distinct':list(distinct)}]}
    if not multi_tool:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Fewer than two distinct tool invocations; claims not independently corroborated.', 'evidence_refs': [{'distinct_tools': list(distinct)}]}
    if not (has_appendix and mentions_discrepancy):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No appendix logging discrepancies found in final response.', 'evidence_refs': []}
    return {'observed_followed': None, 'confidence': 'low', 'reason': 'Insufficient evidence.', 'evidence_refs': []}
