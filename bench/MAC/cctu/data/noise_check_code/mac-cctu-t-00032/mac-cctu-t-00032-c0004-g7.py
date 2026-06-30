def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    names = [c.get('name','') for c in calls]
    leg_calls = [c for c in calls if c.get('name')=='legislative_action_retriever']
    corroborators = [n for n in names if n and n!='legislative_action_retriever']
    final = (trace.get('final_response') or '').lower()
    if not leg_calls:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'No legislative_action_retriever calls found; cannot assess cross-check.', 'evidence_refs':[]}
    if len(corroborators) < 1:
        return {'observed_followed': False, 'confidence':'high', 'reason':'Legislative actions retrieved but no other tool used for cross-checking.', 'evidence_refs':[{'tools_used': names}]}
    unique_corroborators = set(corroborators)
    discard_signals = any(k in final for k in ['discard','unverified','single source','only one source','could not corroborate','unable to confirm','removed','excluded'])
    cross_signals = any(k in final for k in ['cross-check','corroborat','confirmed by','verified','two sources','multiple sources','independent'])
    if len(unique_corroborators) >= 1 and (cross_signals or discard_signals):
        return {'observed_followed': True, 'confidence':'medium', 'reason':'Legislative claims appear corroborated by additional tool(s) with cross-check/discard language.', 'evidence_refs':[{'corroborators': list(unique_corroborators)}]}
    return {'observed_followed': None, 'confidence':'low', 'reason':'Additional tools were called but no explicit cross-check or discard language found in final response.', 'evidence_refs':[{'corroborators': list(unique_corroborators)}]}
