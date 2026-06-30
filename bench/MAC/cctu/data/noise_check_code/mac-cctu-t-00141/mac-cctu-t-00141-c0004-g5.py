def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    lines = [l for l in text.splitlines() if l.strip()]
    prefix_lines = [l for l in lines if l.lstrip().startswith('✈ Year:')]
    if not prefix_lines:
        return {'observed_followed': None, 'confidence':'unknown','reason':'No lines with ✈ Year: prefix found','evidence_refs':[]}
    bad = []
    for l in prefix_lines:
        body = l.lstrip()[len('✈ Year:'):].strip()
        # check one sentence: roughly one terminal punctuation at end, no multiple sentence breaks inside
        # count sentence terminators not at end
        inner = body[:-1] if body and body[-1] in '.!?' else body
        if re.search(r'[.!?]\s+[A-Z0-9]', inner):
            bad.append(l)
            continue
        if not body:
            bad.append(l)
    followed = len(bad) == 0
    return {'observed_followed': followed, 'confidence': 'medium', 'reason': f'{len(prefix_lines)} prefixed lines, {len(bad)} not single-sentence summaries','evidence_refs': bad[:3]}
