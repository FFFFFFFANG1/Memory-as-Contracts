def evaluate(trace):
    import re
    final = (trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    used = []
    seen = set()
    for tc in tool_calls:
        n = tc.get('name')
        if n and n not in seen:
            seen.add(n)
            used.append(n)
    if not final.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    if not used:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls to disclaim','evidence_refs':[]}
    low = final.lower()
    reliability_terms = ['reliab','limitation','caveat','accuracy','may be','might be','not guaranteed','disclaim','uncertain','incomplete','approximat','source','verify']
    has_reliability = any(t in low for t in reliability_terms)
    missing_tools = []
    for t in used:
        variants = [t.lower(), t.lower().replace('_',' '), t.lower().replace('_','-')]
        if not any(v in low for v in variants):
            missing_tools.append(t)
    # Check for paragraph-like disclaimer (a chunk of text mentioning tools+reliability)
    followed = (not missing_tools) and has_reliability
    reason = ''
    if missing_tools:
        reason = 'final response does not name these tools: ' + ', '.join(missing_tools)
    elif not has_reliability:
        reason = 'no reliability/limitation language found in final response'
    else:
        reason = 'final response names all used tools and discusses reliability limitations'
    return {'observed_followed': bool(followed), 'confidence': 'medium', 'reason': reason, 'evidence_refs': []}
