def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'No final response','evidence_refs':[]}
    # Look for FTC code citations like '15 U.S.C. § 45', 'Section 5', '16 CFR', or explicit FTC Act references
    patterns = [r'15\s*U\.?S\.?C\.?\s*§?\s*\d+', r'16\s*C\.?F\.?R\.?\s*§?\s*\d+', r'Section\s+\d+\s+of\s+the\s+FTC', r'FTC\s+Act\s+Section\s+\d+', r'§\s*\d+']
    found = []
    for p in patterns:
        found += re.findall(p, text, flags=re.IGNORECASE)
    ftc_mentioned = bool(re.search(r'FTC|Federal Trade Commission', text, re.IGNORECASE))
    if not ftc_mentioned and not found:
        return {'observed_followed': None,'confidence':'unknown','reason':'No FTC context or codes found; cannot verify enumeration','evidence_refs':[]}
    if found:
        return {'observed_followed': True,'confidence':'medium','reason':f'Found {len(found)} FTC-style code citations in final report','evidence_refs': found[:5]}
    return {'observed_followed': False,'confidence':'medium','reason':'FTC mentioned but no specific violation codes enumerated','evidence_refs':[]}
