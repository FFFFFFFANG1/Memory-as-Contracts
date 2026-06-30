def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    # Find all 4-digit year-like numbers
    years = list(re.finditer(r'\b(\d{3,4})\b', text))
    if not years:
        return {'observed_followed': None,'confidence':'low','reason':'no numeric chronology found','evidence_refs':[]}
    bad = []
    good = []
    for m in years:
        start = m.start()
        # Check if this number is inside parentheses preceded by alphabetic words
        # Pattern: word(s) (NUMBER)
        before = text[max(0,start-60):start]
        # number must be wrapped like '(1945)' and preceded by alpha words
        wrapped = text[max(0,start-1):start] == '(' and text[m.end():m.end()+1] == ')'
        preceded_by_words = bool(re.search(r'[A-Za-z][A-Za-z\- ]{2,}\s*\($', text[:start+1]))
        if wrapped and preceded_by_words:
            good.append(m.group(0))
        else:
            bad.append({'value':m.group(0),'pos':start,'context':text[max(0,start-30):m.end()+5]})
    if bad:
        return {'observed_followed': False,'confidence':'high','reason':f'Found {len(bad)} numeric value(s) not preceded by spelled-out words with parentheses formatting','evidence_refs':bad[:5]}
    return {'observed_followed': True,'confidence':'high','reason':f'All {len(good)} numeric chronology values formatted as words followed by figure in parentheses','evidence_refs':good[:5]}
