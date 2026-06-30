def evaluate(trace):
    import re
    traj = trace.get('trajectory', []) or []
    final = trace.get('final_response', '') or ''
    # Look for a phase marker indicating Earthquake-Mountain Linkage Reporting
    phase_pat = re.compile(r'earthquake[- ]mountain linkage report', re.I)
    # Collect assistant content in order
    contents = []
    for step in traj:
        c = step.get('content') or ''
        if c:
            contents.append(c)
    if final and (not contents or contents[-1] != final):
        contents.append(final)
    if not contents:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no assistant content','evidence_refs':[]}
    # Find first index where phase entered
    phase_idx = None
    for i, c in enumerate(contents):
        if phase_pat.search(c):
            phase_idx = i
            break
    # Patterns for conclusive identification of a mountain or epicenter
    concl_pat = re.compile(r'(the (mountain|epicenter) (is|was)|identified (mountain|epicenter)|epicenter (is|was|located)|final answer)', re.I)
    early_hits = []
    end = phase_idx if phase_idx is not None else len(contents)
    for i in range(end):
        if concl_pat.search(contents[i]):
            early_hits.append(i)
    if phase_idx is None:
        # No explicit phase marker; if conclusive identification appears anywhere, likely violated
        if early_hits:
            return {'observed_followed': False, 'confidence':'low','reason':'conclusive identification without phase marker','evidence_refs':early_hits}
        return {'observed_followed': None,'confidence':'unknown','reason':'no phase marker and no conclusive identification detected','evidence_refs':[]}
    if early_hits:
        return {'observed_followed': False,'confidence':'medium','reason':'conclusive identification issued before linkage reporting phase','evidence_refs':early_hits}
    return {'observed_followed': True,'confidence':'medium','reason':'no premature conclusive identification before phase entry','evidence_refs':[phase_idx]}
