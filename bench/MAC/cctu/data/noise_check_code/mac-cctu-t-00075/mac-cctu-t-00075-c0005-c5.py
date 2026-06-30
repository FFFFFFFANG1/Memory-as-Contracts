def evaluate(trace):
    import re
    final = trace.get('final_response','') or ''
    traj = trace.get('trajectory',[]) or []
    # Count assistant turns
    assistant_turns = 0
    for step in traj:
        role = step.get('role') if isinstance(step, dict) else None
        if role == 'assistant' or role is None:
            assistant_turns += 1
    if assistant_turns == 0:
        assistant_turns = 1
    within_turns = assistant_turns <= 4
    # Detect markdown table
    lines = final.splitlines()
    table_header_idx = None
    for i, ln in enumerate(lines):
        if '|' in ln and i+1 < len(lines) and re.search(r'\|\s*:?-{2,}', lines[i+1]):
            table_header_idx = i
            break
    if table_header_idx is None:
        return {'observed_followed': False, 'confidence':'high', 'reason':'No markdown table detected in final response.', 'evidence_refs':[]}
    header = lines[table_header_idx].lower()
    cols_ok = ('region' in header) and ('dance' in header) and ('source' in header and 'tool' in header)
    if not cols_ok:
        return {'observed_followed': False, 'confidence':'high', 'reason': f'Table header missing required columns: {lines[table_header_idx]}', 'evidence_refs':[]}
    if not within_turns:
        return {'observed_followed': False, 'confidence':'medium', 'reason': f'Interaction exceeded 4 turns: {assistant_turns}', 'evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'high', 'reason':'Markdown table with required columns present and within 4 turns.', 'evidence_refs':[]}
