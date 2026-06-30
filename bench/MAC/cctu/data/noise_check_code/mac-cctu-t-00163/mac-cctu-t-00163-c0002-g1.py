def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls') or []
    n = len(tool_calls)
    final = trace.get('final_response') or ''
    md_patterns = [r'(^|\n)#{1,6}\s', r'\*\*[^*]+\*\*', r'(^|\s)\*[^*\n]+\*', r'`[^`]+`', r'```', r'(^|\n)[-*+]\s+\S', r'(^|\n)\d+\.\s+\S', r'\[[^\]]+\]\([^)]+\)', r'(^|\n)>\s']
    md_hits = [p for p in md_patterns if re.search(p, final)]
    if n > 15:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'{n} tool calls exceeds cap of 15', 'evidence_refs': []}
    if md_hits:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Markdown formatting detected: {md_hits[:3]}', 'evidence_refs': []}
    if not final.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response to evaluate', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'{n}<=15 tool calls and no Markdown detected in final response', 'evidence_refs': []}
