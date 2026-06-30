def evaluate(trace):
    import re
    final = trace.get('final_response','') or ''
    tool_calls = trace.get('tool_calls',[]) or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'no tool calls to record', 'evidence_refs':[]}
    lines = final.splitlines()
    bullet_re = re.compile(r'^\s*([-*+\u2022]|\d+[.)])\s+')
    bullets = [l for l in lines if bullet_re.match(l)]
    if not bullets:
        return {'observed_followed': False, 'confidence':'high', 'reason':'no bullet list of hops found', 'evidence_refs':[]}
    # Determine the leading bullet block (before any narrative prose)
    leading = []
    started = False
    for l in lines:
        if bullet_re.match(l):
            started = True
            leading.append(l)
        elif started and l.strip()=='':
            leading.append(l)
        elif started and l.strip():
            # narrative line after bullets begin - allowed only after hops listed
            break
        else:
            # pre-bullet content
            if l.strip():
                # narrative prose before bullets
                return {'observed_followed': False, 'confidence':'medium', 'reason':'narrative prose appears before bullet hop list', 'evidence_refs':[l[:120]]}
    bullet_text = '\n'.join(leading).lower()
    # Check each tool call name and a query/value appears
    missing = []
    for tc in tool_calls:
        name = (tc.get('name') or '').lower()
        if name and name not in bullet_text:
            missing.append(name)
    if missing:
        return {'observed_followed': False, 'confidence':'medium', 'reason':f'tool names not recorded in bullets: {missing[:5]}', 'evidence_refs':[]}
    # Heuristic: each bullet should mention something resembling query/value (contain ':' or '->' or '=')
    sep_count = sum(1 for b in leading if bullet_re.match(b) and re.search(r'[:\-\u2192=]', b))
    if sep_count < len(tool_calls):
        return {'observed_followed': False, 'confidence':'low', 'reason':'bullets lack tool/query/value structure', 'evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'medium', 'reason':'hops recorded as bullets before any narrative', 'evidence_refs':[]}
