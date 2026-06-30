def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # find year-like tokens
    year_pattern = re.compile(r'\b\d{1,4}\b')
    years = year_pattern.findall(text)
    if not years:
        return {'observed_followed': None,'confidence':'unknown','reason':'no dates detected','evidence_refs':[]}
    bce_ce = re.findall(r'\b\d{1,4}\s*(?:BCE|CE|B\.C\.E\.|C\.E\.)\b', text)
    has_bce_ce = len(bce_ce) > 0
    # check that AD/BC isn't used in place
    ad_bc = re.findall(r'\b\d{1,4}\s*(?:AD|BC|A\.D\.|B\.C\.)\b', text)
    regnal = re.search(r'regnal year|year of (?:his|her|the) reign|\b\d+(?:st|nd|rd|th) year of', text, re.I)
    if not has_bce_ce:
        return {'observed_followed': False,'confidence':'medium','reason':'no BCE/CE notation found near dates','evidence_refs':[]}
    if ad_bc:
        return {'observed_followed': False,'confidence':'medium','reason':'AD/BC used instead of BCE/CE for some dates','evidence_refs':ad_bc[:3]}
    if not regnal:
        return {'observed_followed': False,'confidence':'low','reason':'BCE/CE present but no regnal year mentioned','evidence_refs':bce_ce[:3]}
    return {'observed_followed': True,'confidence':'medium','reason':'BCE/CE notation and regnal year mention present','evidence_refs':bce_ce[:3]}
