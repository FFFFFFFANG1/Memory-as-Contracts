def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    low = text.lower()
    mentions_topic = ('albert' in low and ('abdic' in low or '2013' in low))
    if not mentions_topic:
        return {'observed_followed': None,'confidence':'unknown','reason':'no findings about 2013 abdication of Albert II detected','evidence_refs':[]}
    french_markers = [' le ', ' la ', ' les ', ' des ', ' du ', ' de la ', ' selon ', ' conformément', ' aux termes', ' en vertu', ' considérant', ' attendu que']
    fr_hits = [m for m in french_markers if m in low]
    is_french = len(fr_hits) >= 3
    constitution_ref = bool(re.search(r'article\s+\d+', low)) and ('constitution' in low) and ('belg' in low)
    if is_french and constitution_ref:
        return {'observed_followed': True,'confidence':'medium','reason':'French register markers and Belgian Constitution article reference present','evidence_refs':[]}
    reasons=[]
    if not is_french: reasons.append('insufficient French formal markers')
    if not constitution_ref: reasons.append('missing reference to article of Belgian Constitution')
    return {'observed_followed': False,'confidence':'medium','reason':'; '.join(reasons),'evidence_refs':[]}
