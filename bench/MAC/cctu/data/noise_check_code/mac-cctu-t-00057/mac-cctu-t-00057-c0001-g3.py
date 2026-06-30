def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls', []) or []
    trajectory = trace.get('trajectory', []) or []
    final = trace.get('final_response', '') or ''
    # Look for any mention/creation of trace_outline.md in tool args or assistant content
    outline_mentions = []
    for tc in tool_calls:
        args = tc.get('arguments', {})
        text = ''
        try:
            text = str(args)
        except Exception:
            text = ''
        if 'trace_outline.md' in text.lower():
            outline_mentions.append(tc)
    content_mentions = []
    for step in trajectory:
        c = step.get('content', '') or ''
        if 'trace_outline.md' in c.lower():
            content_mentions.append(c)
    if not outline_mentions and not content_mentions:
        return {
            'observed_followed': False,
            'confidence': 'medium',
            'reason': 'No scratchpad note titled trace_outline.md was created or referenced before answer composition.',
            'evidence_refs': []
        }
    # If mentioned, check that it enumerates hops (look for numbered list or multiple hop entries)
    combined = '\n'.join(content_mentions) + '\n' + str([tc.get('arguments') for tc in outline_mentions])
    hop_pattern = re.findall(r'(?:hop\s*\d+|^\s*\d+[\.)])', combined, re.IGNORECASE | re.MULTILINE)
    if len(hop_pattern) >= 2:
        return {
            'observed_followed': True,
            'confidence': 'medium',
            'reason': 'trace_outline.md referenced with enumerated hops.',
            'evidence_refs': []
        }
    return {
        'observed_followed': False,
        'confidence': 'low',
        'reason': 'trace_outline.md mentioned but hops not clearly enumerated.',
        'evidence_refs': []
    }
