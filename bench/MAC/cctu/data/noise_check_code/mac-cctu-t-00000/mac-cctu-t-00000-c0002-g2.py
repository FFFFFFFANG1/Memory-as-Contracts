def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls') or []
    final = trace.get('final_response') or ''
    date_pat = re.compile(r'\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})\b')
    dates_in_final = set(date_pat.findall(final))
    if not dates_in_final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No disclosure dates detected in final response.', 'evidence_refs': []}
    tool_sources = {}
    for tc in tool_calls:
        name = tc.get('name') or ''
        res = tc.get('result')
        text = '' if res is None else (res if isinstance(res, str) else str(res))
        for d in date_pat.findall(text):
            tool_sources.setdefault(d, set()).add(name)
    unverified = [d for d in dates_in_final if len(tool_sources.get(d, set())) < 2]
    if not unverified:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'All disclosure dates appear in results from >=2 distinct tools.', 'evidence_refs': sorted(dates_in_final)}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Dates lacking 2 independent tool sources: {unverified}', 'evidence_refs': unverified}
