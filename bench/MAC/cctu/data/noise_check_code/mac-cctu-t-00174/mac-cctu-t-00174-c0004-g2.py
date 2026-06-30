def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no trajectory','evidence_refs':[]}
    enumerated = False
    enum_step_idx = None
    for i, step in enumerate(traj):
        content = (step.get('content') or '').strip()
        tcs = step.get('tool_calls') or []
        if content:
            lines = [l.strip() for l in content.splitlines() if l.strip()]
            numbered = [l for l in lines if re.match(r'^\(?\d+[\.\)]\s+\S', l)]
            if len(numbered) >= 2:
                enumerated = True
                enum_step_idx = i
                if tcs:
                    return {'observed_followed': False,'confidence':'high','reason':'tool calls present in enumeration step','evidence_refs':[f'step {i}']}
                break
        if tcs:
            return {'observed_followed': False,'confidence':'high','reason':'tool invoked before any numbered enumeration','evidence_refs':[f'step {i}']}
    if not enumerated:
        # check if any tool was called at all
        any_tool = any((s.get('tool_calls') or []) for s in traj)
        if not any_tool:
            return {'observed_followed': None,'confidence':'low','reason':'no enumeration and no tools used','evidence_refs':[]}
        return {'observed_followed': False,'confidence':'medium','reason':'no numbered enumeration found before tool use','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'high','reason':'numbered enumeration preceded tool calls','evidence_refs':[f'step {enum_step_idx}']}
