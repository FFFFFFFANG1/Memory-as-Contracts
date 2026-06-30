def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    n = len(calls)
    final = trace.get('final_response') or ''
    md_patterns = [r'^#{1,6}\s', r'\*\*[^*]+\*\*', r'(^|\s)\*[^*]+\*', r'`[^`]+`', r'^\s*[-*+]\s+', r'^\s*\d+\.\s+', r'\[[^\]]+\]\([^)]+\)', r'^>\s', r'^```']
    has_md = False
    for p in md_patterns:
        if re.search(p, final, re.MULTILINE):
            has_md = True
            break
    if n > 15:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'{n} tool calls exceed cap of 15', 'evidence_refs': []}
    if has_md:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Markdown formatting detected in final response', 'evidence_refs': []}
    if not final.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response to inspect', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'{n} tool calls (<=15) and plain text final response', 'evidence_refs': []}
