def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    # Get first sentence
    m = re.match(r'\s*([^.!?\n]+[.!?])', resp)
    if not m:
        first = resp.split('\n',1)[0].strip()
    else:
        first = m.group(1).strip()
    region_hints = ['region','culture','cultural','people','peoples','tradition','ethnograph','community','indigenous','tribe','village','province','highlands','lowlands','valley','coast','delta','plateau','nation','country','island','andes','amazon','sahara','balkan','mediterranean','caribbean','polynesia','melanesia','micronesia','scandinav','iberian','anatolian','appalachian','levant','maghreb','sahel','steppe','siberia','patagonia','oceania','asia','africa','europe','america']
    low = first.lower()
    has_region = any(h in low for h in region_hints)
    # Heuristic: also accept proper noun capitalized place before colon/comma
    # Ensure it precedes any conclusion (it's literally the first sentence)
    followed = has_region and len(first.split()) >= 4
    return {'observed_followed': bool(followed), 'confidence': 'medium' if followed else 'low', 'reason': f'first sentence: {first!r}; region_hint={has_region}', 'evidence_refs': []}
