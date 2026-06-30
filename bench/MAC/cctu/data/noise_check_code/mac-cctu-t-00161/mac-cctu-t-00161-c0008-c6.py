def evaluate(trace):
    import json, re
    resp = str(trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response to evaluate', 'evidence_refs': []}
    md_markers = ['```', '**', '__', '# ', '## ', '### ', '\n- ', '\n* ', '\n> ']
    found_md = [m for m in md_markers if m in resp]
    if resp.startswith('- ') or resp.startswith('* ') or resp.startswith('> ') or resp.startswith('#'):
        found_md.append('leading markdown marker')
    if re.search(r'`[^`\n]+`', resp):
        found_md.append('inline code backticks')
    parsed = None
    parse_err = None
    try:
        parsed = json.loads(resp)
    except Exception as e:
        parse_err = str(e)
    if parsed is None:
        # try to find json-looking substrings
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'final response is not raw JSON: ' + (parse_err or 'parse failed'), 'evidence_refs': [resp[:120]]}
    is_dict_or_list_of_dicts = isinstance(parsed, dict) or (isinstance(parsed, list) and all(isinstance(x, dict) for x in parsed))
    if not is_dict_or_list_of_dicts:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'JSON is not a dictionary (or list of dictionaries) of findings', 'evidence_refs': []}
    if found_md:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'markdown formatting present: ' + ', '.join(found_md), 'evidence_refs': []}
    # check for natural-language commentary outside JSON: since json.loads succeeded on whole string, none exists
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'final response is raw JSON dict(s) with no markdown or commentary', 'evidence_refs': []}
