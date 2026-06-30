def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    lines = [l for l in text.splitlines() if l.strip()]
    if len(lines) < 2:
        return {'observed_followed': False, 'confidence':'medium','reason':'fewer than 2 lines, cannot be CSV table','evidence_refs':[]}
    comma_lines = [l for l in lines if ',' in l]
    if len(comma_lines) < max(2, int(0.8*len(lines))):
        return {'observed_followed': False, 'confidence':'high','reason':'most lines lack commas; not CSV','evidence_refs':[]}
    counts = [l.count(',') for l in comma_lines]
    if len(set(counts)) > 2:
        return {'observed_followed': False, 'confidence':'medium','reason':f'inconsistent column counts {counts}','evidence_refs':[]}
    narrative_markers = ['\n\n', 'Here is', 'Below is', 'The following', 'In summary', 'Note:', 'Please', 'As requested']
    lowered = text
    found = [m for m in narrative_markers if m in lowered]
    if found:
        return {'observed_followed': False, 'confidence':'medium','reason':f'narrative markers present: {found}','evidence_refs':[]}
    if re.search(r'^[A-Z][a-z].{40,}[.!?]\s*$', text.split('\n')[0]):
        return {'observed_followed': False, 'confidence':'low','reason':'first line looks like prose sentence','evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'medium','reason':'looks like CSV table without narrative','evidence_refs':[]}
