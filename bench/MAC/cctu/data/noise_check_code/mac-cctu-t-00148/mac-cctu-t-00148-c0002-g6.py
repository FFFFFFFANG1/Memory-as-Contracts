def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    if re.fullmatch(r'-?\d+', resp):
        traj = trace.get('trajectory') or []
        assistant_turns = sum(1 for s in traj if (s.get('role')=='assistant' or 'content' in s))
        if assistant_turns and assistant_turns > 1:
            return {'observed_followed': False, 'confidence':'medium','reason':f'multiple assistant turns: {assistant_turns}','evidence_refs':[]}
        return {'observed_followed': True, 'confidence':'high','reason':'response is bare integer','evidence_refs':[]}
    return {'observed_followed': False, 'confidence':'high','reason':'response is not a bare integer','evidence_refs':[resp[:80]]}
