def evaluate(trace):
    import re
    final = trace.get('final_response') or ''
    traj = trace.get('trajectory') or []
    # find first user message
    user_q = None
    for step in traj:
        role = (step.get('role') or '').lower() if isinstance(step, dict) else ''
        if role == 'user':
            user_q = (step.get('content') or '').strip()
            break
    if user_q is None:
        # try top-level
        user_q = (trace.get('user_message') or trace.get('question') or '').strip() or None
    if not final.strip():
        return {'observed_followed': False, 'confidence':'high','reason':'empty final response','evidence_refs':[]}
    starts_ok = None
    if user_q:
        head = final.lstrip()
        starts_ok = head.startswith(user_q)
    # timestamp detection at end
    tail = final.rstrip().splitlines()[-3:] if final.strip() else []
    tail_text = '\n'.join(tail)
    ts_patterns = [r'\d{4}-\d{2}-\d{2}', r'\d{1,2}[:/]\d{2}', r'UTC|GMT|AM|PM', r'\d{4}/\d{2}/\d{2}']
    has_ts = any(re.search(p, tail_text) for p in ts_patterns)
    # signed: look for a name/signature line e.g. '— Name', 'Signed,', '-- ', 'Sincerely'
    sig_patterns = [r'(?im)^\s*(signed|sincerely|regards|—|--|by:)', r'(?im)signed[, ].+\d']
    has_sig = any(re.search(p, tail_text) for p in sig_patterns)
    if starts_ok is None:
        return {'observed_followed': None, 'confidence':'unknown','reason':'original user question not found in trace','evidence_refs':[]}
    followed = bool(starts_ok and has_ts and has_sig)
    reason = f'starts_with_question={starts_ok}, has_timestamp={has_ts}, has_signature={has_sig}'
    return {'observed_followed': followed, 'confidence':'medium','reason':reason,'evidence_refs':[]}
