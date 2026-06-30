def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    traj = trace.get('trajectory', []) or []
    full = text + '\n' + '\n'.join((s.get('content','') or '') for s in traj)
    low = full.lower()
    if 'confirmed' not in low:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No promotion to confirmed detected.', 'evidence_refs': []}
    # Find blocks/lines mentioning confirmed
    lines = full.splitlines()
    confirmed_blocks = []
    for i, ln in enumerate(lines):
        if 'confirmed' in ln.lower():
            start = max(0, i-6); end = min(len(lines), i+7)
            confirmed_blocks.append('\n'.join(lines[start:end]))
    if not confirmed_blocks:
        confirmed_blocks = [full]
    tool_names = ['comet_event_tracker','historical_event_finder','incident_search_tool','international_agreement_finder','legislative_action_retriever','organization_membership_tracker']
    issues = []
    for blk in confirmed_blocks:
        bl = blk.lower()
        cited = [t for t in tool_names if t in bl]
        # also count generic citation markers
        cite_markers = len(re.findall(r'\[(?:source|citation|ref)[^\]]*\]', bl)) + len(re.findall(r'source\s*\d', bl)) + len(re.findall(r'citation\s*\d', bl))
        independent = len(set(cited))
        if independent < 2 and cite_markers < 2:
            issues.append({'block': blk[:240], 'tools_cited': list(set(cited)), 'cite_markers': cite_markers})
    if issues:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'A confirmed promotion lacks >=2 independent tool-returned citations.', 'evidence_refs': issues[:3]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Each confirmed promotion shows >=2 independent citations.', 'evidence_refs': []}
