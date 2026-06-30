def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # Find numeric figures with storm/impact context and turnout shift figures
    lower = text.lower()
    storm_kw = ['storm','hurricane','cyclone','typhoon','flood','wind','rain','damage','impact']
    turnout_kw = ['turnout','voter','election','shift','participation']
    has_storm = any(k in lower for k in storm_kw)
    has_turnout = any(k in lower for k in turnout_kw)
    if not has_storm and not has_turnout:
        return {'observed_followed': None,'confidence':'unknown','reason':'no storm or turnout discussion found','evidence_refs':[]}
    # Split into paragraphs/sentences and check pairing
    chunks = re.split(r'(?:\n\n|(?<=[.!?])\s+)', text)
    paired = 0
    storm_mentions = 0
    for c in chunks:
        cl = c.lower()
        nums = re.findall(r'\d[\d,\.]*%?', c)
        s = any(k in cl for k in storm_kw)
        t = any(k in cl for k in turnout_kw)
        if s and len(nums) >= 1:
            storm_mentions += 1
            if t and len(nums) >= 2:
                paired += 1
    # Also accept side-by-side via 'vs' or parenthetical pairing
    sidebyside = len(re.findall(r'\d[\d\.,]*%?\s*(?:vs\.?|versus|/|,|\|)\s*\d[\d\.,]*%?', text))
    if storm_mentions == 0:
        return {'observed_followed': None,'confidence':'low','reason':'no storm impact figures detected','evidence_refs':[]}
    if paired >= storm_mentions or sidebyside >= storm_mentions:
        return {'observed_followed': True,'confidence':'medium','reason':f'paired {paired} storm/turnout, sidebyside={sidebyside}','evidence_refs':[]}
    return {'observed_followed': False,'confidence':'medium','reason':f'storm figures={storm_mentions}, paired with turnout={paired}','evidence_refs':[]}
