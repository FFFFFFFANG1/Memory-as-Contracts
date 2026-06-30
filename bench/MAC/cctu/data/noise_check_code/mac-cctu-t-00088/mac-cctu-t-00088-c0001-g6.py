def evaluate(trace):
    import re
    final = trace.get('final_response','') or ''
    calls = trace.get('tool_calls',[]) or []
    tool_names = []
    for c in calls:
        n = c.get('name')
        if n and n not in tool_names:
            tool_names.append(n)
    if not tool_names:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'no tool calls to cite', 'evidence_refs':[]}
    # Look at the tail of the response for a footer-like section
    tail = final[-1500:]
    missing = [t for t in tool_names if t not in tail]
    # Detect timestamp-like patterns near tool mentions
    ts_pattern = re.compile(r'(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}|\d{2}:\d{2}(:\d{2})?|\d{1,2}:\d{2}\s?(AM|PM|am|pm))')
    has_ts = bool(ts_pattern.search(tail))
    footer_markers = ['citation', 'footer', 'sources', 'references', 'tools used', 'tool calls', 'timestamp']
    has_marker = any(m in tail.lower() for m in footer_markers)
    if missing:
        return {'observed_followed': False, 'confidence':'high', 'reason': f'missing tool names in footer: {missing}', 'evidence_refs':[]}
    if not has_ts:
        return {'observed_followed': False, 'confidence':'medium', 'reason':'no timestamp pattern found near tool listing', 'evidence_refs':[]}
    if not has_marker:
        return {'observed_followed': False, 'confidence':'low', 'reason':'no clear citation/footer marker', 'evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'medium', 'reason':'footer lists tools with timestamps', 'evidence_refs':[]}
