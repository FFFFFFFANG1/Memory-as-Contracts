def evaluate(trace):
    import re
    final = (trace.get('final_response') or '').strip()
    if not final:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    # find last user message containing a clarification request (question)
    traj = trace.get('trajectory') or []
    user_msgs = []
    for step in traj:
        role = step.get('role') if isinstance(step, dict) else None
        if role == 'user':
            c = step.get('content') or ''
            if isinstance(c, list):
                c = ' '.join([p.get('text','') for p in c if isinstance(p,dict)])
            user_msgs.append(c)
    clarif = None
    for m in reversed(user_msgs):
        if '?' in m:
            clarif = m.strip()
            break
    # sentence count check
    # strip code/quotes for counting
    sentences = re.split(r'(?<=[.!?])\s+', final)
    sentences = [s for s in sentences if s.strip()]
    sent_ok = len(sentences) <= 2
    # verbatim restatement check: the clarification question text must appear verbatim at start
    verbatim_ok = None
    if clarif:
        # extract the question sentence from clarif
        qmatch = re.findall(r'[^.!?]*\?', clarif)
        q = qmatch[-1].strip() if qmatch else clarif
        verbatim_ok = q in final and final.find(q) < 50
    if clarif is None:
        return {'observed_followed': None,'confidence':'unknown','reason':'no clarification request found in user turns','evidence_refs':[]}
    followed = bool(sent_ok and verbatim_ok)
    return {'observed_followed': followed,'confidence':'medium','reason': f'sentences={len(sentences)} sent_ok={sent_ok} verbatim_ok={verbatim_ok}','evidence_refs':[]}
