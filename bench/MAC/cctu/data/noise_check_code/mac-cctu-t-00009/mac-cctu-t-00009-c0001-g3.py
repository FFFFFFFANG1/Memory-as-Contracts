def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls') or []
    traj = trace.get('trajectory') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls', 'evidence_refs': []}
    used_names = [tc.get('name','') for tc in tool_calls]
    # Gather assistant content excluding the final response
    contents = []
    for step in traj:
        c = step.get('content') or ''
        if c:
            contents.append(c)
    final = trace.get('final_response') or ''
    if contents and contents[-1].strip() == final.strip():
        notes = '\n'.join(contents[:-1])
    else:
        notes = '\n'.join(contents)
    if not notes.strip():
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no working notes content found before final synthesis', 'evidence_refs': []}
    # find numbered list lines like '1.', '2)', '1:' etc
    numbered_lines = re.findall(r'(?m)^\s*(\d+)[\.\)\:]\s+(.+)$', notes)
    if not numbered_lines:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no numbered list found in working notes', 'evidence_refs': []}
    # consecutive numbering starting at 1
    nums = [int(n) for n,_ in numbered_lines]
    # find longest run starting at 1
    run_items = []
    expected = 1
    for n, text in numbered_lines:
        if int(n) == expected:
            run_items.append(text)
            expected += 1
        elif int(n) == 1:
            run_items = [text]
            expected = 2
    if len(run_items) < len(tool_calls):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'numbered chain has {len(run_items)} entries but {len(tool_calls)} tool calls', 'evidence_refs': []}
    # check each tool name appears in order in the run_items
    joined = ' | '.join(run_items).lower()
    missing = [t for t in used_names if t and t.lower() not in joined]
    if missing:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'tools not logged: {missing}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'numbered chain-of-tools list precedes final synthesis and covers all tool calls', 'evidence_refs': []}
