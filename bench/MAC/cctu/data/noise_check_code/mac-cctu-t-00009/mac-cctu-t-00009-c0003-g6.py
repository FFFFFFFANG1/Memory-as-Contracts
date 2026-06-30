import re
def evaluate(trace):
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls found', 'evidence_refs': []}
    date_pat = re.compile(r'\b(1[0-9]{3}|20[0-2][0-9])\b')
    date_to_tools = {}
    for tc in tool_calls:
        name = tc.get('name') or ''
        result = tc.get('result')
        if result is None:
            continue
        text = result if isinstance(result, str) else str(result)
        for d in set(date_pat.findall(text)):
            date_to_tools.setdefault(d, set()).add(name)
    final = trace.get('final_response') or ''
    final_dates = set(date_pat.findall(final))
    if not final_dates and not date_to_tools:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no historical dates detected', 'evidence_refs': []}
    relevant = final_dates if final_dates else set(date_to_tools.keys())
    unverified = []
    for d in relevant:
        tools = date_to_tools.get(d, set())
        if len(tools) < 2:
            unverified.append((d, sorted(tools)))
    if unverified:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'dates not cross-verified by >=2 tools: {unverified}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'all detected dates cross-verified by >=2 tools', 'evidence_refs': []}
