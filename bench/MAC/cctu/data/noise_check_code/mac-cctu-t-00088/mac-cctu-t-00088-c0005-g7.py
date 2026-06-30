def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty final response', 'evidence_refs': []}
    tools = ['app_popularity_analyzer','bridge_identifier','event_locator','infrastructure_info_retriever','landmark_city_locator','official_language_checker','olympic_history_retriever','sports_team_info_retriever','supply_chain_tracker']
    # split into sentences by terminal punctuation
    parts = re.split(r'(?<=[.!?])\s+', text)
    sentences = [p.strip() for p in parts if p.strip()]
    if not sentences:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no sentences detected', 'evidence_refs': []}
    bad = []
    for s in sentences:
        # citation marker should appear at end of sentence: e.g. [tool_name] or (tool_name) possibly before final punctuation
        tail = s[-80:]
        has_marker = False
        # check for bracket/paren containing a known tool name or 'source:' style
        for t in tools:
            if re.search(r'[\[\(][^\[\]\(\)]*' + re.escape(t) + r'[^\[\]\(\)]*[\]\)]\s*[.!?]?\s*$', tail):
                has_marker = True
                break
        if not has_marker:
            # generic citation pattern like [source: X] or [tool: X]
            if re.search(r'[\[\(](?:source|tool|cite|ref)\s*[:=][^\[\]\(\)]+[\]\)]\s*[.!?]?\s*$', tail, re.I):
                has_marker = True
        if not has_marker:
            bad.append(s[:120])
    if not bad:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'every sentence ends with a tool citation marker', 'evidence_refs': []}
    ratio = len(bad) / len(sentences)
    return {'observed_followed': False, 'confidence': 'high' if ratio > 0.3 else 'medium', 'reason': f'{len(bad)}/{len(sentences)} sentences lack citation marker; e.g. {bad[:2]}', 'evidence_refs': []}
