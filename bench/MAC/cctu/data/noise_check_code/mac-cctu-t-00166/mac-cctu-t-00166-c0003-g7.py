def evaluate(trace):
    import re
    final = (trace.get('final_response') or '')
    tcs = trace.get('tool_calls') or []
    analyzer_calls = [t for t in tcs if (t.get('name') or '') == 'mountain_range_analyzer']
    if not analyzer_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'mountain_range_analyzer was not invoked, so range identifiers cannot have been used to tag observations', 'evidence_refs': []}
    # Collect range identifiers from analyzer results
    range_ids = []
    for c in analyzer_calls:
        res = c.get('result')
        s = res if isinstance(res, str) else str(res) if res is not None else ''
        for m in re.findall(r'[A-Z0-9][A-Za-z0-9_\-]{2,}', s):
            range_ids.append(m)
    low = final.lower()
    has_elev = bool(re.search(r'elevation\s*band|elev\.?\s*band|\b(alpine|subalpine|montane|submontane|foothill|lowland|nival)\b', low))
    has_range_ref = any(rid.lower() in low for rid in range_ids) or bool(re.search(r'range\s*id|range\s*identifier|mountain\s*range', low))
    if not has_elev or not has_range_ref:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Final response missing elevation band tag={not has_elev} or mountain range identifier={not has_range_ref}', 'evidence_refs': []}
    # Try to find species-like observation entries and verify each has both tags nearby
    lines = [ln for ln in re.split(r'\n|(?<=\.)\s+', final) if ln.strip()]
    species_lines = [ln for ln in lines if re.search(r'\b[A-Z][a-z]+\s+[a-z]+\b', ln)]
    if not species_lines:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'No clear species observation entries detected to verify per-entry tagging', 'evidence_refs': []}
    bad = []
    for ln in species_lines:
        l = ln.lower()
        e = bool(re.search(r'elevation|alpine|subalpine|montane|submontane|foothill|lowland|nival|\bm\b|meters|metres', l))
        r = any(rid.lower() in l for rid in range_ids) or bool(re.search(r'range', l))
        if not (e and r):
            bad.append(ln[:80])
    if bad:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'{len(bad)} species observation(s) missing elevation band and/or range id tags', 'evidence_refs': bad[:3]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Each detected species observation includes elevation band and a mountain range identifier from analyzer output', 'evidence_refs': []}
