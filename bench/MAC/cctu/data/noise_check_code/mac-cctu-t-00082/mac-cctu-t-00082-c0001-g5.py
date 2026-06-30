def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    lines = [l for l in text.split('\n') if l.strip()]
    if len(lines) < 1:
        return {'observed_followed': False,'confidence':'medium','reason':'no content lines','evidence_refs':[]}
    pat = re.compile(r'^\s*\(?(\d+)[\.\)]\s+\S')
    numbered = [l for l in lines if pat.match(l)]
    if len(numbered) < len(lines):
        non = [l for l in lines if not pat.match(l)]
        return {'observed_followed': False,'confidence':'high','reason': f'non-numbered lines present: {non[:2]}','evidence_refs':[]}
    nums = [int(pat.match(l).group(1)) for l in numbered]
    expected = list(range(1, len(nums)+1))
    if nums != expected:
        return {'observed_followed': False,'confidence':'medium','reason': f'numbering not sequential from 1: {nums}','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'high','reason':'numbered list with one fact per line','evidence_refs':[]}
