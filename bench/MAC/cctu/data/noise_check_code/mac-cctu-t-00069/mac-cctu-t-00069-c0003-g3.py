def evaluate(trace):
    import re
    tcs = trace.get('tool_calls') or []
    final = (trace.get('final_response') or '').strip()
    if not tcs:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'no tool calls found', 'evidence_refs':[]}
    first = tcs[0].get('name')
    if first != 'artist_artwork_identifier':
        return {'observed_followed': False, 'confidence':'high', 'reason': f'first tool call was {first}', 'evidence_refs':[{'tool_index':0,'tool_name':first}]}
    if not final:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'no final response', 'evidence_refs':[]}
    md_patterns = [r'^#', r'\*\*', r'__', r'`', r'^\s*[-*]\s', r'\[[^\]]+\]\([^\)]+\)']
    for p in md_patterns:
        if re.search(p, final, flags=re.MULTILINE):
            return {'observed_followed': False, 'confidence':'high', 'reason': f'markdown pattern {p!r} found', 'evidence_refs':[]}
    if '\n' in final.strip():
        return {'observed_followed': False, 'confidence':'high', 'reason':'multi-line response', 'evidence_refs':[]}
    sentences = re.findall(r'[.!?]+(?:\s|$)', final)
    if len(sentences) > 1:
        return {'observed_followed': False, 'confidence':'medium', 'reason':'more than one sentence', 'evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'high', 'reason':'first tool ok and final is single plain sentence', 'evidence_refs':[{'tool_index':0,'tool_name':first}]}
