def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    words = re.findall(r"\S+", text)
    wc = len(words)
    low = text.lower()
    forbidden = ['choreographer','choreographers','choreography','choreographed']
    hits = [t for t in forbidden if t in low]
    if wc != 30:
        return {'observed_followed': False, 'confidence':'high','reason': f'word count {wc} != 30','evidence_refs':[]}
    if hits:
        return {'observed_followed': False, 'confidence':'high','reason': f'mentions choreographer terms: {hits}','evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'high','reason':'exactly 30 words and no choreographer reference','evidence_refs':[]}
