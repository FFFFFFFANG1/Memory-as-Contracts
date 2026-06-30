def evaluate(trace):
    import re
    resp = trace.get('final_response') or ''
    tcs = trace.get('tool_calls') or []
    if not resp.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    tail = resp[-2000:] if len(resp) > 2000 else resp
    # Look for a citation-like block near the end
    header_pat = re.compile(r'(citations?|sources?|tool (invocations?|calls?)|references?|appendix)', re.IGNORECASE)
    has_header = bool(header_pat.search(tail))
    if not tcs:
        return {'observed_followed': None, 'confidence':'low','reason':'no tool calls recorded; cannot verify listing','evidence_refs':[]}
    names = [tc.get('name','') for tc in tcs if tc.get('name')]
    listed = 0
    for n in names:
        if n and n in resp:
            listed += 1
    # Check payloads referenced
    payload_hits = 0
    for tc in tcs:
        res = tc.get('result')
        if res is None:
            continue
        s = str(res)
        # take a distinctive substring
        snippet = s.strip()[:40]
        if snippet and snippet in resp:
            payload_hits += 1
    all_names_listed = listed == len(names) and len(names) > 0
    payloads_ok = payload_hits >= max(1, len(tcs)//2)
    followed = has_header and all_names_listed and payloads_ok
    conf = 'high' if followed else ('medium' if has_header or all_names_listed else 'medium')
    reason = f'header={has_header}, names_listed={listed}/{len(names)}, payload_hits={payload_hits}/{len(tcs)}'
    return {'observed_followed': bool(followed), 'confidence': conf, 'reason': reason, 'evidence_refs': []}
