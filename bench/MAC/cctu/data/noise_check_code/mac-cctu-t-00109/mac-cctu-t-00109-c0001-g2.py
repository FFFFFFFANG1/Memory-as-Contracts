import re
def evaluate(trace):
    resp = (trace.get('final_response') or '').strip()
    tool_calls = trace.get('tool_calls') or []
    if not resp:
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    if not tool_calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls to cite','evidence_refs':[]}
    tool_names = set()
    for tc in tool_calls:
        n = tc.get('name')
        if n: tool_names.add(n)
    # citation patterns: [tool_name], (tool_name), [#1], [call_1], [tool:...], <ref ...>
    citation_patterns = [
        r'\[[^\]]*(?:' + '|'.join(re.escape(n) for n in tool_names) + r')[^\]]*\]' if tool_names else None,
        r'\[#?\d+\]',
        r'\[call[_\-]?\d+\]',
        r'\[tool[_\-:][^\]]+\]',
        r'\(source:[^)]+\)',
        r'\[ref[^\]]*\]',
    ]
    citation_patterns = [p for p in citation_patterns if p]
    citations_found = []
    for p in citation_patterns:
        citations_found.extend(re.findall(p, resp, flags=re.IGNORECASE))
    # split into sentences
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', resp) if s.strip()]
    if not sentences:
        return {'observed_followed': None,'confidence':'unknown','reason':'no sentences','evidence_refs':[]}
    cited = 0
    for s in sentences:
        if any(re.search(p, s, flags=re.IGNORECASE) for p in citation_patterns):
            cited += 1
    ratio = cited / len(sentences)
    if cited == 0:
        return {'observed_followed': False,'confidence':'high','reason':f'No inline citations found across {len(sentences)} sentences','evidence_refs':[]}
    if ratio >= 0.7:
        return {'observed_followed': True,'confidence':'medium','reason':f'{cited}/{len(sentences)} sentences carry citations','evidence_refs':citations_found[:5]}
    return {'observed_followed': False,'confidence':'medium','reason':f'Only {cited}/{len(sentences)} sentences carry citations','evidence_refs':citations_found[:5]}
