def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    entities = ['explorer','archipelago','island','wetland','plant','pollinator','biologist','town','flower']
    lines = text.splitlines()
    numbered = []
    num_re = re.compile(r'^\s*(\d+)[\.\)\:-]\s*(.+)$')
    for ln in lines:
        m = num_re.match(ln)
        if m:
            numbered.append((int(m.group(1)), m.group(2).strip()))
    if len(numbered) < len(entities):
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'found {len(numbered)} numbered lines; need at least {len(entities)}', 'evidence_refs': []}
    missing = []
    matched_indices = []
    for ent in entities:
        found_idx = None
        for i,(n,content) in enumerate(numbered):
            if re.search(r'\b'+re.escape(ent)+r'\b', content, re.IGNORECASE):
                found_idx = i
                break
        if found_idx is None:
            missing.append(ent)
        else:
            matched_indices.append(found_idx)
    if missing:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'missing entities in numbered trace: {missing}', 'evidence_refs': []}
    last_entity_line_idx = max(matched_indices)
    last_numbered_line_text = numbered[last_entity_line_idx][1]
    last_pos = text.rfind(last_numbered_line_text)
    remainder = text[last_pos+len(last_numbered_line_text):].strip()
    if not remainder:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no final answer after numbered trace', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'numbered chain-of-evidence with all entities followed by final answer', 'evidence_refs': []}
