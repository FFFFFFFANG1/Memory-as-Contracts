def evaluate(trace):
    import re
    final = trace.get('final_response') or ''
    calls = trace.get('tool_calls') or []
    tool_used = any((c.get('name')=='historical_sales_data_retriever') for c in calls)
    # Find wingspan mentions
    # Look for patterns like 'wingspan ... <number> m' or 'wingspan: X.XX m'
    lower = final.lower()
    if 'wingspan' not in lower:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'No wingspan mention found in final response.', 'evidence_refs':[]}
    # Extract substrings around each 'wingspan' occurrence
    issues = []
    found_any_number = False
    for m in re.finditer(r'wingspan', lower):
        start = m.start()
        snippet = final[start:start+200]
        # find first number with unit in snippet
        nm = re.search(r'(\d+(?:[\.,]\d+)?)\s*(m\b|meters?\b|ft\b|feet\b|cm\b)', snippet, re.IGNORECASE)
        if not nm:
            issues.append('wingspan without numeric value+unit: '+snippet[:80])
            continue
        found_any_number = True
        num, unit = nm.group(1), nm.group(2).lower()
        if not unit.startswith('m') or unit.startswith('ml'):
            issues.append(f'wingspan unit not meters: {num} {unit}')
            continue
        # check two decimal places
        if not re.match(r'^\d+\.\d{2}$', num.replace(',', '.')):
            issues.append(f'wingspan not two decimals: {num}')
    format_ok = (len(issues)==0) and found_any_number
    if not tool_used:
        return {'observed_followed': False, 'confidence':'high', 'reason':'historical_sales_data_retriever not invoked.', 'evidence_refs':[]}
    if not format_ok:
        return {'observed_followed': False, 'confidence':'medium', 'reason':'Wingspan formatting issues: '+'; '.join(issues) if issues else 'No numeric wingspan found.', 'evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'high', 'reason':'Wingspan in meters with 2 decimals and tool invoked.', 'evidence_refs':[]}
