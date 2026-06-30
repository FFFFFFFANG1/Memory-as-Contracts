def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    allowed = 'infrastructure_info_retriever'
    bad = [c.get('name') for c in calls if c.get('name') and c.get('name') != allowed]
    final = (trace.get('final_response') or '').strip()
    if not final and not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No response or tool calls present.', 'evidence_refs': []}
    if bad:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Disallowed tools used: {sorted(set(bad))}', 'evidence_refs': [{'type':'tool_calls','names':bad}]}
    # Check YAML-ish asset inventory rendering
    text = final
    # Strip code fences if present
    fence = re.search(r'```(?:yaml|yml)?\s*\n(.*?)```', text, re.S|re.I)
    body = fence.group(1) if fence else text
    lines = [l for l in body.splitlines() if l.strip()]
    if not lines:
        return {'observed_followed': False, 'confidence':'high','reason':'Empty response body.','evidence_refs':[]}
    # YAML heuristics: key: value lines or list items '- '
    yaml_like = sum(1 for l in lines if re.match(r'^\s*-\s+', l) or re.match(r'^\s*[A-Za-z0-9_\-]+\s*:(\s|$)', l))
    if yaml_like < max(2, len(lines)//2):
        return {'observed_followed': False, 'confidence':'medium','reason':'Response does not appear to be YAML-formatted.','evidence_refs':[{'sample':lines[:5]}]}
    # Look for asset inventory cues
    cues = re.search(r'asset|inventory|infrastructure|resource|component|host|server|service', body, re.I)
    if not cues:
        return {'observed_followed': False, 'confidence':'low','reason':'YAML present but no asset inventory cues found.','evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'high','reason':'Only infrastructure_info_retriever used (or none) and output is YAML-like asset inventory.','evidence_refs':[{'yaml_lines':yaml_like,'total_lines':len(lines)}]}
