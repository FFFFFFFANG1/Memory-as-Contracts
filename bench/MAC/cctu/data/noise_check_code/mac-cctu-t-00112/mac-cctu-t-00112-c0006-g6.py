def evaluate(trace):
    import re
    allowed = 'historical_event_retriever'
    calls = trace.get('tool_calls') or []
    bad_tools = [c.get('name') for c in calls if c.get('name') and c.get('name') != allowed]
    if bad_tools:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Used disallowed tools: {sorted(set(bad_tools))}', 'evidence_refs': []}
    text = (trace.get('final_response') or '')
    low = text.lower()
    agg_patterns = [
        r'\btotal(?:ling|ed|s)?\b', r'\bsum(?:med|ming|s)?\b', r'\baggregat',
        r'\bcombined\b', r'\bcumulative\b', r'\boverall total\b',
        r'\bin total\b', r'\baltogether\b', r'\bgrand total\b',
        r'\baverage(?:d|s)?\b', r'\bmean of\b', r'\bacross (?:all|the) events\b'
    ]
    hits = []
    for p in agg_patterns:
        m = re.search(p, low)
        if m:
            hits.append(m.group(0))
    if hits:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Narrative appears to aggregate/sum across events: {hits}', 'evidence_refs': []}
    if not text.strip() and not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No response or tool calls to evaluate', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Only historical_event_retriever used (if any) and no aggregation language detected', 'evidence_refs': []}
