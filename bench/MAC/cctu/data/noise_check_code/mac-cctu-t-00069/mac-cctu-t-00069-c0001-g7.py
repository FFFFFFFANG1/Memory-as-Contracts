def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    tool_names = [c.get('name') for c in calls if c.get('name')]
    final = (trace.get('final_response') or '').strip()
    if not tool_names and not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no evidence', 'evidence_refs': []}
    bad_tools = [t for t in tool_names if t != 'event_host_locator']
    if bad_tools:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'used non-allowed tools: {bad_tools}', 'evidence_refs': tool_names}
    md_patterns = [r'\*\*[^*]+\*\*', r'(^|\s)\*[^*]+\*', r'`[^`]+`', r'^#{1,6}\s', r'^\s*[-*+]\s', r'\[[^\]]+\]\([^)]+\)']
    for pat in md_patterns:
        if re.search(pat, final, re.MULTILINE):
            return {'observed_followed': False, 'confidence': 'high', 'reason': f'markdown detected: {pat}', 'evidence_refs': [final[:120]]}
    # one sentence check
    stripped = final.rstrip()
    # count sentence terminators not at end
    inner = stripped[:-1] if stripped and stripped[-1] in '.!?' else stripped
    terminators = re.findall(r'[.!?](?=\s|$)', inner)
    if len(terminators) > 0:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'response appears to contain more than one sentence', 'evidence_refs': [final[:200]]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'only event_host_locator used, one sentence, no markdown', 'evidence_refs': tool_names}
