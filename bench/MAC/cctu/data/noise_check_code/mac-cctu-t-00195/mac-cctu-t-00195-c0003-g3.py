def evaluate(trace):
    import re
    final = trace.get('final_response') or ''
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls to cite', 'evidence_refs': []}
    if not final.strip():
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no final response to contain footer', 'evidence_refs': []}
    lines = final.splitlines()
    numbered = [l for l in lines if re.match(r'^\s*\[?\d+[\.\)\]]\s+', l)]
    if len(numbered) < len(tool_calls):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'found {len(numbered)} numbered items, expected >= {len(tool_calls)}', 'evidence_refs': []}
    tail = '\n'.join(lines[-(len(tool_calls)+6):])
    names_in_order = [tc.get('name','') for tc in tool_calls]
    pos = 0
    order_ok = True
    for n in names_in_order:
        idx = tail.find(n, pos)
        if idx < 0:
            order_ok = False
            break
        pos = idx + len(n)
    ts_pattern = re.compile(r'(\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2}(:\d{2})?|\d{4}/\d{2}/\d{2}|T\d{2}:\d{2}|timestamp|retriev)', re.I)
    ts_count = len(ts_pattern.findall(tail))
    has_ts = ts_count >= len(tool_calls)
    if order_ok and has_ts:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'numbered footer lists tools in order with timestamps', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'order_ok={order_ok}, timestamps_found={ts_count}/{len(tool_calls)}', 'evidence_refs': []}
