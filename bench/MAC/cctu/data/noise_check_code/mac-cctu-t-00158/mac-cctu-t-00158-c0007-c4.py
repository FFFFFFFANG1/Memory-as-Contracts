def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    names = [str(c.get('name') or '') for c in tool_calls]
    n_forest = sum(1 for n in names if n == 'forest_tree_data_retriever')
    if n_forest < 2:
        reasons.append('forest_tree_data_retriever called ' + str(n_forest) + ' times (<2)')
    lines = response.splitlines()
    bullet_re = re.compile(r'^\s*([-*+]|\d+[.)])\s+\S')
    bullets = [ln for ln in lines if bullet_re.match(ln)]
    if len(bullets) < 2:
        reasons.append('no bulleted list with multiple items found')
    counts = []
    has_count_evidence = False
    for ln in bullets:
        m = re.search(r'(\d[\d,]*)', ln)
        if m:
            try:
                counts.append(int(m.group(1).replace(',', '')))
                has_count_evidence = True
            except Exception:
                pass
        else:
            counts.append(None)
    if bullets and not has_count_evidence:
        reasons.append('bulleted list lacks numeric species counts')
    numeric = [c for c in counts if c is not None]
    if len(numeric) >= 2:
        if not (all(numeric[i] >= numeric[i+1] for i in range(len(numeric)-1)) or all(numeric[i] <= numeric[i+1] for i in range(len(numeric)-1))):
            reasons.append('bulleted counts not ordered by abundance')
        elif all(numeric[i] <= numeric[i+1] for i in range(len(numeric)-1)) and not all(numeric[i] >= numeric[i+1] for i in range(len(numeric)-1)):
            # ascending only — constraint says ordered by abundance, accept either direction as ordered
            pass
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'forest_tree_data_retriever invoked >=2 and bulleted ordered species counts present', 'evidence_refs': []}
