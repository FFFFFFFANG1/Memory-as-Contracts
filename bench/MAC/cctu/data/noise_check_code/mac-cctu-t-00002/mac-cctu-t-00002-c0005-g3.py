def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    low = text.lower()
    nintendo_platforms = ['switch','wii u','wii','nintendo ds','nintendo 3ds','3ds','gamecube','n64','nintendo 64','snes','nes','game boy','gba']
    mentions = [p for p in nintendo_platforms if re.search(r'\b'+re.escape(p)+r'\b', low)]
    if 'nintendo' not in low and not mentions:
        return {'observed_followed': None,'confidence':'unknown','reason':'no Nintendo console launch reporting detected','evidence_refs':[]}
    # find bracketed lists
    brackets = re.findall(r'\[([^\[\]]+)\]', text)
    if not brackets:
        return {'observed_followed': False,'confidence':'medium','reason':'Nintendo platforms referenced but no [A, B] bracketed list found','evidence_refs':[text[:200]]}
    # check at least one bracket contains comma-separated platform-like tokens
    for b in brackets:
        items = [x.strip() for x in b.split(',') if x.strip()]
        if len(items) >= 1 and any(p in b.lower() for p in nintendo_platforms):
            # ensure comma-separated format if multiple platforms mentioned
            if len(mentions) >= 2 and len(items) < 2:
                continue
            return {'observed_followed': True,'confidence':'medium','reason':'found bracketed comma-separated platform list','evidence_refs':[b]}
    return {'observed_followed': False,'confidence':'medium','reason':'bracketed list did not contain platforms in required format','evidence_refs':brackets[:3]}
