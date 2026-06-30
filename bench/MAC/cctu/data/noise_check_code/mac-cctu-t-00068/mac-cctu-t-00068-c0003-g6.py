def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls', []) or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls to audit.', 'evidence_refs': []}
    text_parts = []
    final = trace.get('final_response') or ''
    text_parts.append(final)
    for step in trace.get('trajectory', []) or []:
        c = step.get('content')
        if isinstance(c, str):
            text_parts.append(c)
    blob = '\n'.join(text_parts).lower()
    has_audit_term = any(k in blob for k in ['audit log', 'audit_log', 'audit.log', 'auditlog'])
    if not has_audit_term:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No mention of an audit log file in trajectory or final response.', 'evidence_refs': []}
    has_timestamp = bool(re.search(r'\d{4}-\d{2}-\d{2}[ tT]\d{2}:\d{2}', blob)) or 'timestamp' in blob
    mentions_params = 'parameter' in blob or 'arguments' in blob or 'args' in blob or 'input' in blob
    mentions_outputs = 'output' in blob or 'result' in blob or 'response' in blob
    missing = []
    if not has_timestamp: missing.append('timestamp')
    if not mentions_params: missing.append('parameters')
    if not mentions_outputs: missing.append('outputs')
    if missing:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Audit log mentioned but missing: ' + ', '.join(missing), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Audit log mention includes timestamps, parameters, and outputs.', 'evidence_refs': []}
