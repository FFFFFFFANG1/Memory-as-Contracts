def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    tool_names = [str(c.get('name') or '') for c in tool_calls if c.get('name')]
    if not response.strip() and not tool_names:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    called = set(tool_names)
    if 'event_host_locator' not in called:
        reasons.append('required tool event_host_locator not called')
    other = sorted(n for n in called if n and n != 'event_host_locator')
    if other:
        reasons.append('forbidden tools used: ' + ', '.join(other[:5]))
    text = response.strip()
    if text:
        md_patterns = [r'\*\*[^*]+\*\*', r'(?<!\*)\*(?!\s)[^*\n]+\*', r'__[^_]+__', r'(?m)^\s*#{1,6}\s', r'(?m)^\s*[-*+]\s+\S', r'`[^`]+`', r'```', r'\[[^\]]+\]\([^)]+\)']
        for pat in md_patterns:
            if re.search(pat, text):
                reasons.append('markdown formatting detected: ' + pat)
                break
        stripped = text.rstrip()
        inner = re.sub(r'(?<=\b(?:Mr|Mrs|Ms|Dr|St|Jr|Sr|vs|etc|e\.g|i\.e))\.', '', stripped, flags=re.IGNORECASE)
        sentence_ends = re.findall(r'[.!?]+(?=\s+\S|$)', inner)
        if len(sentence_ends) == 0:
            reasons.append('no sentence terminator found')
        elif len(sentence_ends) > 1:
            reasons.append('more than one sentence detected (' + str(len(sentence_ends)) + ')')
    else:
        reasons.append('empty final response')
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'sole tool event_host_locator used; single sentence; no markdown', 'evidence_refs': []}
