def evaluate(trace):
    import re
    final = (trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    names = [tc.get('name','') for tc in tool_calls]
    used_cat = 'corporate_acquisition_tracker' in names
    if not final.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    if not used_cat:
        return {'observed_followed': False, 'confidence':'high','reason':'corporate_acquisition_tracker not used as primary source','evidence_refs':[{'tools_used': names}]}
    low = final.lower()
    hq_patterns = [r'headquarter', r'\bhq\b', r'based in', r'headquartered']
    has_hq_ref = any(re.search(p, low) for p in hq_patterns)
    country_hint = re.search(r'\b(country|united states|usa|u\.s\.|china|japan|germany|france|uk|united kingdom|india|canada|switzerland|netherlands|ireland|singapore|south korea|australia|brazil|italy|spain|sweden|norway|denmark|finland|israel|taiwan|hong kong|mexico|russia|saudi arabia|uae)\b', low)
    if has_hq_ref and country_hint:
        return {'observed_followed': True, 'confidence':'medium','reason':'final response references headquarters and a country','evidence_refs':[{'match': country_hint.group(0)}]}
    if country_hint and not has_hq_ref:
        return {'observed_followed': None, 'confidence':'low','reason':'country mentioned but no explicit headquarters citation','evidence_refs':[]}
    return {'observed_followed': False, 'confidence':'medium','reason':'no headquarters country citation found in conclusion','evidence_refs':[]}
