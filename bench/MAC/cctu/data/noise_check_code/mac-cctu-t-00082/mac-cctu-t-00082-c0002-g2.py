def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    # Find numbered enumeration lines like '1.' '2)' etc.
    lines = text.splitlines()
    numbered = [l for l in lines if re.match(r'^\s*\d+[\.\)]\s+\S', l)]
    if len(numbered) < 2:
        return {'observed_followed': None, 'confidence':'low','reason':'no clear numbered enumeration found','evidence_refs':[]}
    # Check that numbered lines have no markdown decorations
    bad = []
    deco_pat = re.compile(r'(\*\*|__|`|^\s*[-\*\+]\s|#|\[[^\]]+\]\([^\)]+\))')
    for l in numbered:
        if re.search(r'\*\*|__|`', l):
            bad.append(l)
        elif re.search(r'\[[^\]]+\]\([^\)]+\)', l):
            bad.append(l)
    # Also check sequential numbering starting at 1
    nums = [int(re.match(r'^\s*(\d+)', l).group(1)) for l in numbered]
    sequential = nums == list(range(1, len(nums)+1)) or nums == list(range(nums[0], nums[0]+len(nums)))
    if bad:
        return {'observed_followed': False, 'confidence':'high','reason':f'numbered items contain formatting decorations: {bad[:2]}','evidence_refs':[]}
    if not sequential:
        return {'observed_followed': False, 'confidence':'medium','reason':f'numbering not sequential: {nums}','evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'medium','reason':'numbered plain-text enumeration without decorations','evidence_refs':[]}
