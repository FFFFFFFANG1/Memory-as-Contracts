def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls present', 'evidence_refs': []}
    final = (trace.get('final_response') or '')
    traj = trace.get('trajectory') or []
    texts = [final] + [str(s.get('content') or '') for s in traj]
    combined = '\n\n'.join(texts)
    if not combined.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No narrative text found', 'evidence_refs': []}
    # Heuristic: per tool call, look for multi-paragraph narrative mentioning background, key figures, aftermath
    bg_terms = ['background','context','prior','leading up','before']
    fig_terms = ['figure','leader','president','general','key player','protagonist','notable','prominent']
    after_terms = ['aftermath','consequence','result','impact','legacy','following','afterward','outcome']
    paragraphs = [p for p in re.split(r'\n\s*\n', combined) if p.strip()]
    if len(paragraphs) < 3 * len(tool_calls):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Only {len(paragraphs)} paragraphs for {len(tool_calls)} tool results', 'evidence_refs': []}
    low = combined.lower()
    has_bg = any(t in low for t in bg_terms)
    has_fig = any(t in low for t in fig_terms)
    has_after = any(t in low for t in after_terms)
    missing = [n for n,ok in [('background',has_bg),('key figures',has_fig),('aftermath',has_after)] if not ok]
    if missing:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Missing coverage of: ' + ', '.join(missing), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'low', 'reason': 'Multi-paragraph narrative covers background, key figures, and aftermath', 'evidence_refs': []}
