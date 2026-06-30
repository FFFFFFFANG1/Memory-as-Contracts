def evaluate(trace):
    import re
    msgs = []
    for step in trace.get('trajectory', []) or []:
        if step.get('role') and step.get('role') != 'assistant':
            continue
        content = step.get('content')
        if isinstance(content, str) and content.strip():
            msgs.append(content)
    final = trace.get('final_response')
    if isinstance(final, str) and final.strip() and final not in msgs:
        msgs.append(final)
    if not msgs:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No assistant messages found.', 'evidence_refs': []}
    violations = []
    for i, m in enumerate(msgs):
        text = m.strip()
        paragraphs = [p for p in re.split(r'\n\s*\n', text) if p.strip()]
        word_count = len(re.findall(r'\S+', text))
        if len(paragraphs) > 1:
            violations.append(f'msg {i}: {len(paragraphs)} paragraphs')
        if word_count >= 40:
            violations.append(f'msg {i}: {word_count} words')
    if violations:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(violations), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'All {len(msgs)} assistant message(s) are single paragraphs under 40 words.', 'evidence_refs': []}
