def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls', []) or []
    final = (trace.get('final_response') or '').lower()
    lang_calls = [tc for tc in tool_calls if tc.get('name') == 'international_organization_language_info']
    if not lang_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No language info tool calls found', 'evidence_refs': []}
    org_counts = {}
    for tc in lang_calls:
        args = tc.get('arguments') or {}
        org = None
        if isinstance(args, dict):
            for k, v in args.items():
                if isinstance(v, str) and v:
                    org = v
                    break
        if org is None:
            org = str(args)
        org_counts[org] = org_counts.get(org, 0) + 1
    re_queried = [o for o, c in org_counts.items() if c >= 2]
    all_re = len(re_queried) == len(org_counts) and len(org_counts) > 0
    has_discrepancy_note = bool(re.search(r'discrepanc', final))
    if all_re and has_discrepancy_note:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'Each org ({len(org_counts)}) queried >=2 times and discrepancy note present', 'evidence_refs': []}
    if all_re and not has_discrepancy_note:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Re-queries present but no discrepancy note in final response', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Not all orgs re-queried: {org_counts}', 'evidence_refs': []}
