def evaluate(trace):
    import re
    tcs = trace.get('tool_calls') or []
    required = ['space_mission_info_retriever','astronomical_discovery_finder']
    if not tcs:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls','evidence_refs':[]}
    names = [t.get('name') for t in tcs]
    # find first occurrences
    first_idx = {}
    for i,n in enumerate(names):
        if n not in first_idx:
            first_idx[n] = i
    for r in required:
        if r not in first_idx:
            return {'observed_followed': False, 'confidence':'high','reason': f'{r} not called','evidence_refs': names}
    last_required_pos = max(first_idx[r] for r in required)
    # any non-required tool must come after both required tools' first calls
    for i,n in enumerate(names[:last_required_pos+1]):
        if n not in required:
            return {'observed_followed': False,'confidence':'high','reason': f'{n} called before both required tools','evidence_refs': names}
    final = (trace.get('final_response') or '').strip()
    if not final:
        return {'observed_followed': None,'confidence':'unknown','reason':'no final response','evidence_refs': names}
    # mission identifier prefix: look for an identifier-like token at start
    # accept patterns like Apollo 11, STS-1, Voyager 1, etc., or any alnum/code token
    m = re.match(r'^[\[\(\*\s"\']*([A-Z][A-Za-z0-9\-]*(?:[\s\-][A-Za-z0-9\-]+){0,3})', final)
    if not m:
        return {'observed_followed': False,'confidence':'medium','reason':'no mission identifier prefix detected','evidence_refs':[final[:80]]}
    return {'observed_followed': True,'confidence':'medium','reason':'required tools first and identifier-like prefix present','evidence_refs':[names, final[:80]]}
