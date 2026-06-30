def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    trajectory = trace.get('trajectory') or []
    if not response.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'empty final response', 'evidence_refs': []}
    if not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no tool calls; multi-hop dependencies cannot be resolved', 'evidence_refs': []}
    reasons = []
    md_markers = ['**', '__', '`', '~~']
    for m in md_markers:
        if m in response:
            reasons.append('markdown marker present: ' + m)
            break
    for line in response.splitlines():
        s = line.lstrip()
        if s.startswith('#') or s.startswith('- ') or s.startswith('* ') or s.startswith('+ '):
            reasons.append('heading or list marker present')
            break
        if re.match(r'^\d+\.\s', s):
            reasons.append('numbered list present')
            break
    if re.search(r'(?i)answer\s*:\s*$', response.strip()):
        reasons.append("trailing 'Answer:' tag present")
    if re.search(r'(?im)^\s*answer\s*:', response):
        reasons.append("'Answer:' tag present")
    sentences = re.split(r'(?<=[.!?])\s+', response.strip())
    sentences = [s for s in sentences if s.strip()]
    if len(sentences) > 1:
        reasons.append('response is not a single sentence ({} sentences)'.format(len(sentences)))
    rounds = len(trajectory) if trajectory else 0
    if rounds > 20:
        reasons.append('exceeded 20 interaction rounds: {}'.format(rounds))
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'single plain-text sentence, no markdown/headings/lists/Answer tag, within 20 rounds, tool calls present', 'evidence_refs': []}
