def evaluate(trace):
    import re
    resp = trace.get('final_response') or ''
    text = resp.strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    # Extract first sentence
    m = re.match(r'\s*(.+?[.!?])(\s|$)', text)
    first = m.group(1).strip() if m else text.split('\n')[0].strip()
    tool_calls = trace.get('tool_calls') or []
    tool_names = [tc.get('name','') for tc in tool_calls]
    lower = first.lower()
    # Check it references tool calls/usage
    keywords = ['tool', 'call', 'called', 'used', 'invoked', 'queried', 'retrieved', 'fetched', 'performed', 'executed', 'no tools']
    mentions = any(k in lower for k in keywords)
    # Or mentions a specific tool name
    name_mention = any(n and (n.lower() in lower or n.replace('_',' ').lower() in lower) for n in tool_names)
    if mentions or name_mention:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': f'First sentence summarizes tool activity: {first[:120]}', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'First sentence does not summarize tool calls: {first[:120]}', 'evidence_refs': []}
