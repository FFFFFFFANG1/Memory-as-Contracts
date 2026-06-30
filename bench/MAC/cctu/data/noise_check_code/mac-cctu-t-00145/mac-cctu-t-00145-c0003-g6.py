def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    # Strip optional yaml code fence
    fence = re.match(r'^```(?:ya?ml)?\s*\n(.*?)\n```$', text, re.DOTALL|re.IGNORECASE)
    body = fence.group(1) if fence else text
    lines = [l for l in body.splitlines() if l.strip()]
    if not lines:
        return {'observed_followed': False, 'confidence':'medium','reason':'empty body','evidence_refs':[]}
    # YAML-ish: top-level keys followed by ':' and list/mapping items
    yaml_like = True
    has_group = False
    for l in lines:
        s = l.rstrip()
        if re.match(r'^[A-Za-z0-9_][\w \-/]*:\s*$', s):
            has_group = True
            continue
        if re.match(r'^\s+-\s+.+', s):
            continue
        if re.match(r'^\s*[A-Za-z0-9_][\w \-/]*:\s+.+', s):
            continue
        if re.match(r'^[A-Za-z0-9_][\w \-/]*:\s+.+', s):
            continue
        yaml_like = False
        break
    if not yaml_like or not has_group:
        return {'observed_followed': False, 'confidence':'medium','reason':'content not a YAML grouping block','evidence_refs':[]}
    # Check no prose surrounding: if no fence, entire text must be yaml (already checked).
    # If fenced, ensure nothing outside fence (already enforced by regex anchors).
    return {'observed_followed': True, 'confidence':'medium','reason':'YAML block with grouped keys and no surrounding prose','evidence_refs':[]}
