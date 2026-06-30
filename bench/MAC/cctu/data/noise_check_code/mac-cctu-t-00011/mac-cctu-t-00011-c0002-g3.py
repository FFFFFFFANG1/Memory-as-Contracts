def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls', []) or []
    final = trace.get('final_response', '') or ''
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found.', 'evidence_refs': []}
    hes_calls = [tc for tc in tool_calls if tc.get('name') == 'historical_event_search']
    if not hes_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'historical_event_search was never invoked, so dates cannot be corroborated by it.', 'evidence_refs': []}
    date_pat = re.compile(r'\b(1[5-9]\d{2}|20\d{2}|21\d{2})\b')
    def payload_text(tc):
        return str(tc.get('result', '')) 
    hes_text = ' '.join(payload_text(tc) for tc in hes_calls)
    other_texts = {tc.get('name'): '' for tc in tool_calls if tc.get('name') != 'historical_event_search'}
    for tc in tool_calls:
        n = tc.get('name')
        if n != 'historical_event_search':
            other_texts[n] = other_texts.get(n, '') + ' ' + payload_text(tc)
    final_dates = set(date_pat.findall(final))
    if not final_dates:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'No year-like dates found in final response to verify cross-referencing.', 'evidence_refs': []}
    uncorroborated = []
    for d in final_dates:
        in_hes = d in hes_text
        other_hits = sum(1 for t in other_texts.values() if d in t)
        if not in_hes:
            uncorroborated.append((d, 'missing from historical_event_search'))
        elif other_hits < 1:
            uncorroborated.append((d, 'only in historical_event_search, no independent corroboration'))
    if uncorroborated:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Dates not cross-referenced across >=2 independent payloads incl. historical_event_search: {uncorroborated}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'All final dates appear in historical_event_search and at least one other tool payload.', 'evidence_refs': []}
