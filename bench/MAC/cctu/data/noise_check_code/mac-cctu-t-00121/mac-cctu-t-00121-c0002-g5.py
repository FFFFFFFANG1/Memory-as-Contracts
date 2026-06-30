def evaluate(trace):
    import re
    tcs = trace.get('tool_calls') or []
    names = {tc.get('name') for tc in tcs if tc.get('name')}
    final = (trace.get('final_response') or '').lower()
    has_audit = bool(re.search(r'audit\s*row|audit:|discrepan', final))
    if not tcs and not final:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no trajectory evidence','evidence_refs':[]}
    enough_tools = len(names) >= 3
    if enough_tools and has_audit:
        return {'observed_followed': True, 'confidence':'medium','reason':f'{len(names)} distinct tools used and audit/discrepancy mention present','evidence_refs': sorted(list(names))}
    if not enough_tools and not has_audit:
        return {'observed_followed': False, 'confidence':'high','reason':f'only {len(names)} distinct tools and no audit row','evidence_refs': sorted(list(names))}
    return {'observed_followed': False, 'confidence':'medium','reason': f'distinct_tools={len(names)}, audit_mention={has_audit}','evidence_refs': sorted(list(names))}
