def evaluate(trace):
    import re
    final = trace.get('final_response','') or ''
    traj = trace.get('trajectory',[]) or []
    tool_calls = trace.get('tool_calls',[]) or []
    if len(tool_calls) < 2:
        return {'observed_followed': None, 'confidence':'unknown','reason':'No comparative tool outputs to stage.','evidence_refs':[]}
    # Collect assistant text in order
    texts = []
    for step in traj:
        c = step.get('content','') or ''
        if c:
            texts.append(c)
    if final and (not texts or texts[-1] != final):
        texts.append(final)
    combined = '\n'.join(texts)
    if not combined.strip():
        return {'observed_followed': None,'confidence':'unknown','reason':'No assistant text to inspect.','evidence_refs':[]}
    # Detect YAML manifest: fenced ```yaml block or clear YAML key: value structure with multiple keys
    yaml_fence = re.search(r'```ya?ml\b', combined, re.IGNORECASE)
    yaml_like = None
    if not yaml_fence:
        # Heuristic: at least 3 lines matching 'key: value' pattern
        lines = combined.splitlines()
        kv = [l for l in lines if re.match(r'^[A-Za-z_][\w\- ]*:\s*(\S.*)?$', l.strip())]
        if len(kv) >= 3:
            yaml_like = True
    if not yaml_fence and not yaml_like:
        return {'observed_followed': False,'confidence':'medium','reason':'No YAML manifest detected before narrative.','evidence_refs':[]}
    # Find position of YAML block
    if yaml_fence:
        yaml_start = yaml_fence.start()
        yaml_end_match = re.search(r'```', combined[yaml_fence.end():])
        yaml_end = yaml_fence.end() + (yaml_end_match.start() if yaml_end_match else 0)
    else:
        # find first kv line index
        m = re.search(r'(?m)^[A-Za-z_][\w\- ]*:\s*\S', combined)
        yaml_start = m.start() if m else 0
        yaml_end = yaml_start + 200
    # Narrative = substantial prose (sentences with multiple words ending in period) BEFORE yaml_start
    before = combined[:yaml_start]
    sentences = re.findall(r'[A-Z][^.!?\n]{30,}[.!?]', before)
    if len(sentences) >= 2:
        return {'observed_followed': False,'confidence':'medium','reason':'Narrative composed before YAML manifest staging.','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'medium','reason':'YAML manifest appears before narrative composition.','evidence_refs':[]}
