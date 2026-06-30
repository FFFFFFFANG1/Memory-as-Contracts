def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls', 'evidence_refs': []}
    date_pat = re.compile(r'\b(?:\d{1,2}[\s\-/](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s\-/]\d{2,4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|\b(?:18|19|20)\d{2})\b', re.IGNORECASE)
    date_to_tools = {}
    for tc in tool_calls:
        name = tc.get('name','')
        result = tc.get('result')
        text = str(result) if result is not None else ''
        for m in set(date_pat.findall(text)):
            key = m.strip().lower()
            date_to_tools.setdefault(key, set()).add(name)
    if not date_to_tools:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'no dates retrieved from tools', 'evidence_refs': []}
    final = (trace.get('final_response') or '')
    final_dates = set(d.strip().lower() for d in date_pat.findall(final))
    unverified = []
    for d, tools in date_to_tools.items():
        if d in final_dates and len(tools) < 2:
            unverified.append((d, list(tools)))
    has_discrepancy_log = bool(re.search(r'discrepan|conflict|mismatch|differ', final, re.IGNORECASE))
    if unverified:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'dates used without 2 independent confirmations: {unverified[:3]}', 'evidence_refs': []}
    confirmed = [d for d,t in date_to_tools.items() if len(t) >= 2]
    if not confirmed and final_dates:
        return {'observed_followed': False, 'confidence': 'low', 'reason': 'final dates not cross-confirmed by 2 tools', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'{len(confirmed)} dates cross-confirmed; discrepancy_log={has_discrepancy_log}', 'evidence_refs': []}
