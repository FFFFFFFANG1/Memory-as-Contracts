def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no trajectory','evidence_refs':[]}
    retrieval_kw = 'retriev'
    outline_pat = re.compile(r'(outline|plan|steps?|first[,]?\s*i|then\s*i|will\s+(call|use|invoke)|i\s+will|tool\s*call)', re.I)
    outline_found_idx = None
    for i, step in enumerate(traj):
        content = (step.get('content') or '') if isinstance(step, dict) else ''
        tcs = (step.get('tool_calls') or []) if isinstance(step, dict) else []
        if outline_found_idx is None:
            if content and outline_pat.search(content) and len(content.strip()) > 40:
                if tcs:
                    return {'observed_followed': False, 'confidence':'high','reason':'outline step also invoked tools','evidence_refs':[f'step{i}']}
                outline_found_idx = i
                break
            if tcs:
                names = [ (tc.get('name') or tc.get('function',{}).get('name','')) for tc in tcs ]
                if any(retrieval_kw in (n or '').lower() for n in names):
                    return {'observed_followed': False, 'confidence':'high','reason':f'retrieval tool {names} called before outline','evidence_refs':[f'step{i}']}
                return {'observed_followed': False, 'confidence':'medium','reason':'tool invoked before any outline','evidence_refs':[f'step{i}']}
    if outline_found_idx is None:
        return {'observed_followed': False, 'confidence':'medium','reason':'no outline drafted before tool use','evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'medium','reason':'outline present before any tool call','evidence_refs':[f'step{outline_found_idx}']}
