def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    starts = resp.lower().startswith('based on verified tool data,')
    tool_calls = trace.get('tool_calls') or []
    # Look for an audit trail: mentions of tool names or an explicit audit/trail section before substantive finding
    tool_names = [tc.get('name','') for tc in tool_calls if tc.get('name')]
    mentions = sum(1 for n in tool_names if n and n in resp)
    has_audit_keyword = bool(re.search(r'(audit trail|tool[- ]call audit|tools used|trail:)', resp, re.I))
    audit_ok = has_audit_keyword or mentions >= 1
    if starts and audit_ok:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'opens with boilerplate and includes audit trail reference', 'evidence_refs': []}
    if not starts:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'response does not open with required boilerplate', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no tool-call audit trail detected before finding', 'evidence_refs': []}
