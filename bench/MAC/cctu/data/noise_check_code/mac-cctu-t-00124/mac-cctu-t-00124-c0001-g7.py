def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    if not response.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'empty response', 'evidence_refs': []}
    tool_calls = trace.get('tool_calls') or []
    lower = response.lower()
    header_patterns = [r'chronolog', r'audit', r'step[- ]by[- ]step', r'timeline', r'trace log', r'tool call log', r'reasoning steps', r'process log', r'execution log', r'\bsteps\b']
    header_hits = [p for p in header_patterns if re.search(p, lower)]
    if not header_hits:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no chronology/audit section header found in final response', 'evidence_refs': []}
    # find earliest header position to ensure it is appended after main answer
    positions = []
    for p in header_patterns:
        m = re.search(p, lower)
        if m:
            positions.append(m.start())
    header_pos = min(positions) if positions else -1
    if header_pos < 0 or header_pos < max(1, int(len(response) * 0.2)):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'chronology section does not appear appended after the final answer', 'evidence_refs': []}
    appendix = response[header_pos:]
    # Look for enumerated steps
    step_markers = re.findall(r'(?:^|\n)\s*(?:\d+[\.)\-:]|step\s*\d+|-\s+)', appendix, flags=re.IGNORECASE)
    if len(step_markers) < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'appended section lacks an enumerated step-by-step list', 'evidence_refs': []}
    # If tool calls were made, the chronology should reference them
    if tool_calls:
        names = []
        for tc in tool_calls:
            n = tc.get('name') if isinstance(tc, dict) else None
            if n:
                names.append(n)
        if names:
            appendix_l = appendix.lower()
            referenced = sum(1 for n in names if n.lower() in appendix_l or n.lower().replace('_',' ') in appendix_l)
            if referenced == 0:
                return {'observed_followed': False, 'confidence': 'high', 'reason': 'chronology does not reference any of the tool calls made', 'evidence_refs': [n for n in names]}
            if referenced < len(set(names)):
                return {'observed_followed': False, 'confidence': 'medium', 'reason': f'chronology references only {referenced}/{len(set(names))} distinct tools used', 'evidence_refs': list(set(names))}
    else:
        # No tool calls were made; constraint asks for chronology of tool calls AND reasoning steps
        # Reasoning-only chronology is still possible, but mention of tool calls/reasoning should be present
        if not re.search(r'tool|reason|think', appendix, flags=re.IGNORECASE):
            return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no tool calls made and appendix does not document reasoning steps explicitly', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'appended step-by-step chronology with references to tool calls/reasoning', 'evidence_refs': []}
