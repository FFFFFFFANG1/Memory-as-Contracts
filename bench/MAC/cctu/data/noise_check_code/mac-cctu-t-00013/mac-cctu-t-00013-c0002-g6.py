def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    bullet_re = re.compile(r'^\s*([-*+•]|\d+[\.)])\s+(.*)')
    bullets = []
    for l in lines:
        m = bullet_re.match(l)
        if m:
            bullets.append(m.group(2).strip())
    if len(bullets) < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'response is not a bullet list with multiple items', 'evidence_refs': [text[:200]]}
    # Try to extract vote share percentages from each bullet
    shares = []
    for b in bullets:
        nums = re.findall(r'(\d+(?:\.\d+)?)\s*%', b)
        if not nums:
            nums = re.findall(r'(\d+(?:\.\d+)?)', b)
        shares.append(float(nums[0]) if nums else None)
    # Check ordering descending where shares known
    known = [s for s in shares if s is not None]
    ordered = all(shares[i] is not None and shares[i+1] is not None and shares[i] >= shares[i+1] for i in range(len(shares)-1)) if len(known) == len(shares) else None
    # Check each bullet begins with a party-like name (capitalized word/acronym at start)
    party_start_re = re.compile(r'^["\'\(\[]?[A-Z][A-Za-z0-9&\.\-]*(\s+[A-Z][A-Za-z0-9&\.\-]*)*')
    starts_ok = all(bool(party_start_re.match(b)) for b in bullets)
    if not starts_ok:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'not all bullets begin with a party-like name', 'evidence_refs': bullets[:3]}
    if ordered is False:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'bullets not ordered by vote share descending', 'evidence_refs': [str(shares)]}
    if ordered is None:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'could not extract vote shares for all bullets', 'evidence_refs': bullets[:3]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'bullet list ordered by vote share with party names leading', 'evidence_refs': bullets[:3]}
