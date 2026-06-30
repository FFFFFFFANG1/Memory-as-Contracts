def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls', []) or []
    cbs = [tc for tc in tool_calls if tc.get('name') == 'celestial_body_surface_calculator']
    if not cbs:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'celestial_body_surface_calculator not used', 'evidence_refs': []}
    final = (trace.get('final_response') or '')
    low = final.lower()
    has_unit = ('square kilometer' in low) or ('km²' in low) or ('km^2' in low) or ('sq km' in low) or ('sq. km' in low)
    identifiers = []
    for tc in cbs:
        res = tc.get('result')
        if isinstance(res, dict):
            for k in ('id','identifier','body_id','name','celestial_body','celestial_body_id'):
                if k in res and res[k] is not None:
                    identifiers.append(str(res[k]))
        elif isinstance(res, str):
            identifiers.append(res)
    if not identifiers:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'no identifier found in tool result', 'evidence_refs': []}
    has_citation = any(ident and ident.lower() in low for ident in identifiers)
    has_citation_block = bool(re.search(r'(?i)(citation|source|reference|\[ref|\[cite)', final)) and has_citation
    ok = has_unit and has_citation_block
    return {'observed_followed': bool(ok), 'confidence': 'medium', 'reason': f'unit={has_unit}, citation_with_id={has_citation_block}, ids={identifiers}', 'evidence_refs': []}
