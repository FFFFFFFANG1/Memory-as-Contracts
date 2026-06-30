def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    # Count sentence terminators
    # Strip trailing punctuation for analysis
    stripped = text.rstrip()
    # Check for question/exclamation
    if stripped.endswith('?') or stripped.endswith('!'):
        return {'observed_followed': False, 'confidence':'high','reason':'not declarative','evidence_refs':[stripped[-1]]}
    # Split into sentences
    parts = re.split(r'(?<=[.!?])\s+', stripped)
    parts = [p for p in parts if p.strip()]
    if len(parts) > 1:
        return {'observed_followed': False, 'confidence':'high','reason':f'{len(parts)} sentences found','evidence_refs':parts}
    # Check for internal terminators that would indicate multiple sentences
    inner = stripped[:-1] if stripped[-1:] in '.!?' else stripped
    if re.search(r'[.!?]\s+[A-Z]', inner):
        return {'observed_followed': False,'confidence':'medium','reason':'multiple sentences detected','evidence_refs':[inner]}
    # Look for mention of 'University' (proper noun) and a city
    has_university = bool(re.search(r'[Uu]niversity', stripped))
    if not has_university:
        return {'observed_followed': False,'confidence':'high','reason':'no university named','evidence_refs':[stripped]}
    # City heuristic: at least one additional capitalized token beyond University name, or comma-separated location
    # Look for pattern like 'in <City>' or ', <City>'
    city_match = re.search(r'(?:in|,|located in|based in)\s+([A-Z][\w\-]+(?:\s+[A-Z][\w\-]+)*)', stripped)
    if not city_match:
        return {'observed_followed': False,'confidence':'medium','reason':'no city detected','evidence_refs':[stripped]}
    return {'observed_followed': True,'confidence':'medium','reason':'single declarative sentence with university and city','evidence_refs':[stripped, city_match.group(1)]}
