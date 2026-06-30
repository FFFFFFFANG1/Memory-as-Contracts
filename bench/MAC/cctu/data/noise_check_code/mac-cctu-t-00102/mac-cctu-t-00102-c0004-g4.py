def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    reasons = []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    tool_names = [str(c.get('name') or '') for c in tool_calls]
    hcount = sum(1 for n in tool_names if n == 'historical_event_info_retriever')
    if hcount > 2:
        reasons.append('historical_event_info_retriever called ' + str(hcount) + ' times (max 2)')
    text = response.strip()
    length = len(text)
    if length < 50 or length > 150:
        reasons.append('final response length ' + str(length) + ' not in [50,150]')
    pattern = re.compile(r'Pr[üu]m:\s*([0-9][0-9,\.]*)\s*;\s*Kemi:\s*([0-9][0-9,\.]*)\s*;\s*Total:\s*([0-9][0-9,\.]*)', re.IGNORECASE)
    m = pattern.search(text)
    if not m:
        reasons.append('final response does not contain required format "Prüm: X; Kemi: Y; Total: Z"')
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'format, length, and tool-call cap satisfied', 'evidence_refs': []}
