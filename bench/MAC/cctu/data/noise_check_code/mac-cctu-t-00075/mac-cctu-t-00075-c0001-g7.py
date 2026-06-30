def evaluate(trace):
    import re
    final = (trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    n_calls = len(tool_calls)
    if not final.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'No final response','evidence_refs':[]}
    # Find a references-like header near the end
    header_re = re.compile(r'(?im)^\s*(?:#+\s*)?(references|bibliography|works cited|citations)\b.*$')
    matches = list(header_re.finditer(final))
    if not matches:
        return {'observed_followed': False,'confidence':'high','reason':'No references/bibliography section header found','evidence_refs':[]}
    last = matches[-1]
    tail = final[last.end():]
    # Ensure header is in last portion of response
    if last.start() < len(final) * 0.4 and len(matches) == 1:
        # still acceptable if section is at end, check tail has content but nothing significant after
        pass
    # Count numbered entries in tail like '1.' '2)' '[1]'
    entries = re.findall(r'(?m)^\s*(?:\[\d+\]|\d+[\.)])\s+\S', tail)
    n_entries = len(entries)
    if n_entries == 0:
        return {'observed_followed': False,'confidence':'high','reason':'References section has no numbered entries','evidence_refs':[tail[:200]]}
    if n_calls > 0 and n_entries < n_calls:
        return {'observed_followed': False,'confidence':'medium','reason': f'Found {n_entries} numbered entries but {n_calls} tool calls','evidence_refs':[tail[:300]]}
    return {'observed_followed': True,'confidence':'high','reason': f'Found references section with {n_entries} numbered entries (tool calls={n_calls})','evidence_refs':[tail[:200]]}
