def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    text = response.strip()
    n = len(text)
    if n < 50 or n > 150:
        reasons.append('length ' + str(n) + ' not in [50,150]')
    pattern = re.compile(r'Pr[üu]m:\s*(\d+)\s*;\s*Kemi:\s*(\d+)\s*;\s*Total:\s*(\d+)')
    m = pattern.search(text)
    if not m:
        reasons.append('missing required format "Prüm: X; Kemi: Y; Total: Z"')
    tool_names = [str(c.get('name') or '') for c in tool_calls]
    cnt = sum(1 for nm in tool_names if nm == 'historical_event_info_retriever')
    if cnt > 2:
        reasons.append('historical_event_info_retriever called ' + str(cnt) + ' times (>2)')
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'length, format, and tool-call cap all satisfied', 'evidence_refs': []}
