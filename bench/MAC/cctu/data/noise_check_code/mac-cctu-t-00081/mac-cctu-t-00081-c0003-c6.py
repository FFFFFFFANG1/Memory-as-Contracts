def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    # Identify clarification turns: assistant messages that ask a question to user (contain '?') without tool calls being the response to a user query needing clarification
    # Heuristic: find assistant steps whose content ends with '?' and has no tool_calls -> clarification asked
    # But constraint is about answering clarification turns. Interpret as: when assistant responds in a clarification exchange.
    # Look for assistant turns that contain a question mark and check they are single short sentence with no tool calls.
    suspects = []
    for i, step in enumerate(traj):
        if step.get('role') and step.get('role') != 'assistant':
            continue
        content = (step.get('content') or '').strip()
        tcs = step.get('tool_calls') or []
        if not content:
            continue
        # Heuristic: clarification = short assistant message ending with '?'
        if content.endswith('?'):
            sentences = re.split(r'(?<=[.!?])\s+', content)
            sentences = [s for s in sentences if s.strip()]
            short = len(sentences) <= 1 and len(content.split()) <= 30
            no_tools = len(tcs) == 0
            suspects.append({'idx': i, 'short': short, 'no_tools': no_tools, 'text': content[:120]})
    if not suspects:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No clarification turns detected.', 'evidence_refs': []}
    bad = [s for s in suspects if not (s['short'] and s['no_tools'])]
    if bad:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Clarification turn(s) violated single-short-sentence/no-tool rule: {bad}', 'evidence_refs': [b['idx'] for b in bad]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'All clarification turns are short single sentences without tool calls.', 'evidence_refs': [s['idx'] for s in suspects]}
