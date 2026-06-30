def evaluate(trace):
    import re
    trace = trace or {}
    final = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not final.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'missing final response', 'evidence_refs': []}
    words = re.findall(r'\S+', final)
    word_count = len(words)
    low = final.lower()
    provenance_terms = ['provenance', 'tool call', 'tool-call', 'audit log', 'call log']
    has_provenance_label = any(t in low for t in provenance_terms)
    tool_names = []
    for c in tool_calls:
        n = c.get('name') if isinstance(c, dict) else None
        if n:
            tool_names.append(str(n))
    referenced_tools = [n for n in set(tool_names) if n.lower() in low]
    failures = []
    if word_count < 400:
        failures.append(f'final response word count {word_count} below required 400')
    if not has_provenance_label:
        failures.append('final response lacks a tool-call provenance log section (no provenance/tool-call/audit log marker)')
    if tool_names and not referenced_tools:
        failures.append('provenance log does not reference any invoked tool name')
    evidence = [{'field': 'final_response', 'word_count': word_count, 'has_provenance_label': has_provenance_label, 'invoked_tools': sorted(set(tool_names)), 'referenced_tools': sorted(referenced_tools)}]
    if failures:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(failures), 'evidence_refs': evidence}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'final response is {word_count} words and includes a tool-call provenance log', 'evidence_refs': evidence}
