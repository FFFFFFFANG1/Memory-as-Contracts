def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    for step in trace.get('trajectory',[]) or []:
        c = step.get('content')
        if isinstance(c,str): text += '\n'+c
    if not text.strip():
        return {'observed_followed': None,'confidence':'unknown','reason':'no notes','evidence_refs':[]}
    locations = ['desk','drawer','bag','shelf','table','cabinet','pocket','box','counter','floor','closet','backpack','briefcase']
    loc_re = re.compile(r'\b(' + '|'.join(locations) + r')\b', re.I)
    lines = [l for l in re.split(r'[\n\r]|(?<=[.;])\s+', text) if l.strip()]
    item_lines = []
    for l in lines:
        if re.search(r'\b(item|brand|model)\b', l, re.I) or re.search(r'[A-Z][a-zA-Z]+\s+[A-Z0-9][a-zA-Z0-9-]*', l):
            item_lines.append(l)
    if not item_lines:
        return {'observed_followed': None,'confidence':'unknown','reason':'no identifiable item entries','evidence_refs':[]}
    missing = [l for l in item_lines if not loc_re.search(l)]
    if missing:
        return {'observed_followed': False,'confidence':'medium','reason':f'{len(missing)} item line(s) lack inline location','evidence_refs': missing[:3]}
    return {'observed_followed': True,'confidence':'medium','reason':'all detected item lines include a location keyword','evidence_refs':[]}
