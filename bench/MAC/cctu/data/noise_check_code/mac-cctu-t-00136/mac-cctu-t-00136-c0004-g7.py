def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    low = text.lower()
    asset_indicators = ['asset', 'listing', 'inventory', 'portfolio', 'holding', 'item', 'property']
    if not any(k in low for k in asset_indicators):
        return {'observed_followed': None, 'confidence':'low','reason':'no asset listing detected','evidence_refs':[]}
    has_date_kw = bool(re.search(r'acqui(red|sition)|purchas(e|ed)|obtain(ed)?|date acquired', low))
    has_date_val = bool(re.search(r'\b(19|20)\d{2}\b', text)) or bool(re.search(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', text))
    has_custodian = bool(re.search(r'custodian|responsible|caretaker|steward|owner of record|managed by|in charge', low))
    if has_date_kw and has_date_val and has_custodian:
        return {'observed_followed': True, 'confidence':'medium','reason':'asset listing includes acquisition date and custodian','evidence_refs':[]}
    missing = []
    if not (has_date_kw and has_date_val): missing.append('acquisition date')
    if not has_custodian: missing.append('custodian')
    return {'observed_followed': False, 'confidence':'medium','reason':'missing: '+', '.join(missing),'evidence_refs':[]}
