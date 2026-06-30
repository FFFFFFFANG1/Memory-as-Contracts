def evaluate(trace):
    import re
    final = (trace.get('final_response') or '')
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls to audit','evidence_refs':[]}
    ordered = sorted(calls, key=lambda c: (c.get('iteration',0), c.get('index',0)))
    lower = final.lower()
    # find an audit-like section near the end
    tail = final[-2000:] if len(final) > 2000 else final
    tail_l = tail.lower()
    has_audit_header = any(k in tail_l for k in ['audit', 'tool call', 'tools used', 'tool log', 'call log'])
    # check each tool name appears in tail in order
    positions = []
    missing = []
    cursor = 0
    for c in ordered:
        name = (c.get('name') or '').lower()
        if not name:
            continue
        idx = tail_l.find(name, cursor)
        if idx == -1:
            missing.append(name)
            positions.append(-1)
        else:
            positions.append(idx)
            cursor = idx + len(name)
    in_order = all(p != -1 for p in positions) and positions == sorted([p for p in positions if p!=-1])
    # check each retrieved value appears somewhere in tail
    value_missing = []
    for c in ordered:
        res = c.get('result')
        if res is None:
            continue
        s = str(res)
        # extract short tokens from result
        tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-']{2,}", s)
        if not tokens:
            continue
        # require at least one significant token from the result to appear in tail
        found = any(t.lower() in tail_l for t in tokens[:10])
        if not found:
            value_missing.append((c.get('name'), s[:40]))
    followed = has_audit_header and in_order and not missing and not value_missing
    reason = f'audit_header={has_audit_header}, in_order={in_order}, missing_names={missing}, missing_values={value_missing}'
    conf = 'high' if (has_audit_header and (followed or missing or value_missing)) else 'medium'
    return {'observed_followed': bool(followed), 'confidence': conf, 'reason': reason, 'evidence_refs': []}
