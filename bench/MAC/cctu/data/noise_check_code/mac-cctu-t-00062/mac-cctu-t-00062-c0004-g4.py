def evaluate(trace):
    import re
    final = (trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls to record','evidence_refs':[]}
    low = final.lower()
    if 'ledger' not in low and 'calibration' not in low:
        return {'observed_followed': False,'confidence':'high','reason':'no calibration ledger in response','evidence_refs':[]}
    # check for timestamp-like tokens
    ts_pat = re.compile(r'(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}|\d{2}:\d{2}:\d{2}|\d{10,})')
    timestamps = ts_pat.findall(final)
    size_pat = re.compile(r'(payload|size|bytes|chars|length)', re.I)
    size_hits = len(size_pat.findall(final))
    n = len(tool_calls)
    if len(timestamps) < n:
        return {'observed_followed': False,'confidence':'medium','reason':f'expected >={n} timestamps, found {len(timestamps)}','evidence_refs':[]}
    if size_hits < n:
        return {'observed_followed': False,'confidence':'medium','reason':f'insufficient payload-size entries (found {size_hits} of {n})','evidence_refs':[]}
    # check each tool name appears
    missing = [tc.get('name') for tc in tool_calls if tc.get('name') and tc.get('name') not in final]
    if missing:
        return {'observed_followed': False,'confidence':'medium','reason':f'tools missing from ledger: {missing}','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'medium','reason':'ledger appears to record each invocation with timestamp and size','evidence_refs':[]}
