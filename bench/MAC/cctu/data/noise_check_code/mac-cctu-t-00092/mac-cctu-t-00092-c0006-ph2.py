def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    # Collect intermediate assistant content (exclude final response)
    final = (trace.get('final_response') or '').strip()
    intermediate_texts = []
    for step in traj:
        content = step.get('content') if isinstance(step, dict) else None
        if not content or not isinstance(content, str):
            continue
        if final and content.strip() == final:
            continue
        intermediate_texts.append(content)
    if not intermediate_texts:
        return {'observed_followed': None, 'confidence':'unknown','reason':'No intermediate assistant content found to evaluate.','evidence_refs':[]}
    bracket_pat = re.compile(r'\[[^\[\]]*(sport|football|soccer|basketball|baseball|cricket|rugby|hockey|tennis|volleyball|golf)[^\[\]]*\]', re.IGNORECASE)
    offenders = []
    prose_ok = True
    for idx, txt in enumerate(intermediate_texts):
        m = bracket_pat.search(txt)
        if m:
            offenders.append({'index': idx, 'match': m.group(0)})
        # crude prose check: must contain at least one sentence-like structure
        if not re.search(r'[A-Za-z].*[\.\!\?]', txt):
            prose_ok = False
    if offenders:
        return {'observed_followed': False, 'confidence':'high','reason':'Intermediate content contains a bracketed sport identifier.','evidence_refs': offenders}
    if not prose_ok:
        return {'observed_followed': None, 'confidence':'low','reason':'Intermediate content present but does not clearly read as prose audit trail.','evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'medium','reason':'Intermediate content reads as prose and lacks bracketed sport identifier.','evidence_refs':[]}
