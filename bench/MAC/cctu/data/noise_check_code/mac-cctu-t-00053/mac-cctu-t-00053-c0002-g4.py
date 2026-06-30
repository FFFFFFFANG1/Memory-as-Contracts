def evaluate(trace):
    import re
    calls = [c for c in trace.get('tool_calls', []) if c.get('name') == 'historical_population_retriever']
    if len(calls) < 4:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Only {len(calls)} historical_population_retriever calls (need >=4)', 'evidence_refs': []}
    decades = set()
    for c in calls:
        args = c.get('arguments', {}) or {}
        text = ' '.join(str(v) for v in args.values()) if isinstance(args, dict) else str(args)
        for y in re.findall(r'\b(1[5-9]\d{2}|20\d{2})\b', text):
            decades.add(int(y) // 10)
    if len(decades) < 4:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Found {len(decades)} distinct decades in tool args', 'evidence_refs': []}
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    lines = [l for l in resp.splitlines() if l.strip()]
    csv_lines = [l for l in lines if ',' in l]
    if len(csv_lines) >= 2 and len(csv_lines) >= len(lines) - 2:
        cols = [l.count(',') for l in csv_lines]
        if cols and max(cols) == min(cols):
            return {'observed_followed': True, 'confidence': 'high', 'reason': f'{len(calls)} calls over {len(decades)} decades; CSV table detected', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Response does not look like a CSV-formatted table', 'evidence_refs': []}
