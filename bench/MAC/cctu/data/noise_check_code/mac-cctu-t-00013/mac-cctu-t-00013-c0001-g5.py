def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    # Find assistant content emitted before any tool results returned
    pre_tool_texts = []
    saw_tool_result = False
    for step in traj:
        content = step.get('content') or ''
        tcs = step.get('tool_calls') or []
        if content and not saw_tool_result:
            pre_tool_texts.append(content)
        if step.get('role') == 'tool' or step.get('tool_results') or (tcs and any(tc.get('result') for tc in tcs)):
            saw_tool_result = True
        if tcs:
            # content alongside tool calls counts as pre-corroboration
            pass
    if not pre_tool_texts:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No pre-tool assistant content found to evaluate.', 'evidence_refs': []}
    # Heuristic: look for factual-looking claims (years, proper nouns, numbers) outside brackets
    violations = []
    claim_pat = re.compile(r'\b(1[6-9]\d{2}|20\d{2})\b|\b[A-Z][a-zA-Z]+ (?:was|is|signed|won|elected|appointed|became|served)\b')
    bracket_pat = re.compile(r'\[[^\]]+\]')
    for text in pre_tool_texts:
        stripped = bracket_pat.sub('', text)
        m = claim_pat.search(stripped)
        if m:
            violations.append(m.group(0))
    if violations:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Tentative claims found outside square brackets before tool corroboration: ' + '; '.join(violations[:3]), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'low', 'reason': 'No unbracketed tentative factual claims detected before tool use.', 'evidence_refs': []}
