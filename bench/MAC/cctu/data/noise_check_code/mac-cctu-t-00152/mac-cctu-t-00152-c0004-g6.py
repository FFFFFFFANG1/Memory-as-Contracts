def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    # Find numbered cards like '1.' '2)' etc at line starts
    lines = text.splitlines()
    card_indices = [i for i,l in enumerate(lines) if re.match(r'^\s*(\d+)[\.)\:]\s+\S', l)]
    if len(card_indices) < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'found {len(card_indices)} numbered cards', 'evidence_refs': []}
    # Check for hidden spoiler markers
    spoiler_pat = re.compile(r'(<details[\s>]|\|\|[^|]+\|\||<spoiler|\[spoiler\]|>!.+!<|\bSpoiler\b\s*[:\-])', re.IGNORECASE)
    # Split into card blocks
    blocks = []
    for idx, start in enumerate(card_indices):
        end = card_indices[idx+1] if idx+1 < len(card_indices) else len(lines)
        blocks.append('\n'.join(lines[start:end]))
    missing_spoiler = [i for i,b in enumerate(blocks) if not spoiler_pat.search(b)]
    if missing_spoiler:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'cards without hidden spoiler section: {missing_spoiler}', 'evidence_refs': []}
    # Check teaser: first non-number line should be short (one line)
    bad_teaser = []
    for i,b in enumerate(blocks):
        first = b.splitlines()[0]
        # remove leading number
        teaser = re.sub(r'^\s*\d+[\.)\:]\s*', '', first).strip()
        if not teaser or len(teaser) > 300:
            bad_teaser.append(i)
    if bad_teaser:
        return {'observed_followed': False, 'confidence': 'low', 'reason': f'cards with missing/overlong teaser: {bad_teaser}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'{len(blocks)} numbered cards each with teaser and spoiler section', 'evidence_refs': []}
