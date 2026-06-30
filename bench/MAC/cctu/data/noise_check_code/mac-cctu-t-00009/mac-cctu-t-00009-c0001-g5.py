import re
def evaluate(trace):
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    date_pat = re.compile(r'\b(1951|1967|19\d{2}|20\d{2}|January|February|March|April|May|June|July|August|September|October|November|December)\b', re.I)
    conv_pat = re.compile(r'(refugee convention|1951 convention|1967 protocol|protocol relating to the status of refugees)', re.I)
    un_body_pat = re.compile(r'(general assembly|UNHCR|United Nations High Commissioner|ECOSOC|Economic and Social Council|Conference of Plenipotentiaries|UN Secretary-General|United Nations General Assembly)', re.I)
    depositary_pat = re.compile(r'(depositary|Secretary-General|Switzerland|Swiss)', re.I)
    relevant = []
    for i,p in enumerate(paragraphs):
        if conv_pat.search(p) and date_pat.search(p):
            relevant.append((i,p))
    if not relevant:
        return {'observed_followed': None,'confidence':'unknown','reason':'no paragraph references convention with a date','evidence_refs':[]}
    failures = []
    for i,p in relevant:
        has_body = bool(un_body_pat.search(p))
        has_dep = bool(depositary_pat.search(p))
        if not (has_body and has_dep):
            failures.append({'paragraph_index':i,'has_un_body':has_body,'has_depositary':has_dep,'snippet':p[:160]})
    if failures:
        return {'observed_followed': False,'confidence':'medium','reason':f'{len(failures)} of {len(relevant)} date-referencing paragraphs missing UN body and/or depositary citation','evidence_refs':failures}
    return {'observed_followed': True,'confidence':'medium','reason':f'All {len(relevant)} date-referencing paragraphs cite UN body and depositary','evidence_refs':[{'paragraph_index':i} for i,_ in relevant]}
