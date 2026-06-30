def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    tools = ['diplomatic_event_tracker','election_result_analyzer','historical_event_finder','historical_event_retriever','political_event_tracker','solar_event_finder']
    tool_calls = trace.get('tool_calls') or []
    used_tools = {tc.get('name') for tc in tool_calls if tc.get('name')}
    # Date regex patterns
    date_patterns = [
        r'\b\d{4}-\d{2}-\d{2}\b',
        r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',
        r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b',
        r'\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b',
        r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b',
        r'\b\d{4}\b'
    ]
    found = []
    for pat in date_patterns:
        for m in re.finditer(pat, text):
            # avoid year-only inside another date already captured: simple overlap check later
            found.append((m.start(), m.end(), m.group()))
    # dedupe overlaps: keep longest non-overlapping
    found.sort(key=lambda x:(x[0], -(x[1]-x[0])))
    filtered = []
    last_end = -1
    for s,e,g in found:
        if s >= last_end:
            filtered.append((s,e,g))
            last_end = e
    if not filtered:
        return {'observed_followed': None,'confidence':'unknown','reason':'no dates detected in response','evidence_refs':[]}
    failures = []
    successes = []
    for s,e,g in filtered:
        tail = text[e:e+200]
        m = re.match(r'\s*\(([^)]+)\)', tail)
        if not m:
            failures.append(g)
            continue
        inside = m.group(1).strip().lower()
        if any(t in inside for t in tools):
            successes.append((g, inside))
        else:
            failures.append(g)
    if failures:
        return {'observed_followed': False,'confidence':'high','reason': f'dates without tool citation: {failures[:5]}','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'high','reason': f'all {len(successes)} dates cite a tool','evidence_refs':[]}
