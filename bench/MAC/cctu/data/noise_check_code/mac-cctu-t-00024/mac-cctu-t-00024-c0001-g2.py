def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # Check for JSON-like content
    if re.search(r'[\{\[].*[\}\]]', resp, re.DOTALL):
        if '{' in resp and '}' in resp:
            return {'observed_followed': False,'confidence':'high','reason':'contains JSON-like braces','evidence_refs':[]}
    # Check for fixed opening phrases
    lowered = resp.lower().lstrip()
    bad_openings = ['the answer is','answer:','result:','here is','here\'s','the event is','response:']
    for op in bad_openings:
        if lowered.startswith(op):
            return {'observed_followed': False,'confidence':'high','reason':f'fixed opening phrase: {op}','evidence_refs':[]}
    # Single sentence check: count sentence terminators (excluding decimals)
    # Strip trailing punctuation
    text = resp.rstrip()
    # Count sentence-ending punctuation followed by space or end
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    sentences = [s for s in sentences if s.strip()]
    if len(sentences) > 1:
        return {'observed_followed': False,'confidence':'high','reason':f'multiple sentences ({len(sentences)})','evidence_refs':[sentences[0][:60]]}
    # Check date in long-form prose: look for month name
    months = ['January','February','March','April','May','June','July','August','September','October','November','December']
    has_month = any(m in resp for m in months)
    # Check for numeric-only date patterns like 1990-01-15 or 01/15/1990
    has_numeric_date = bool(re.search(r'\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b', resp))
    if has_numeric_date and not has_month:
        return {'observed_followed': False,'confidence':'medium','reason':'date in numeric form, not long-form prose','evidence_refs':[]}
    if not has_month:
        return {'observed_followed': None,'confidence':'low','reason':'no clear long-form date detected','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'medium','reason':'single sentence, long-form date, no JSON or fixed opening','evidence_refs':[]}
