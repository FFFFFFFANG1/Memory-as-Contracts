def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    low = text.lower()
    id_markers = [' dan ', ' yang ', ' adalah ', ' dengan ', ' untuk ', ' tidak ', ' pada ', ' dari ', ' ini ', ' itu ', ' atau ', 'bahasa indonesia', 'terjemahan']
    en_markers = [' the ', ' and ', ' is ', ' are ', ' was ', ' were ', ' of ', ' to ', ' in ', ' that ', ' this ', ' english']
    id_hits = sum(1 for m in id_markers if m in low)
    en_hits = sum(1 for m in en_markers if m in low)
    if id_hits < 2 or en_hits < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Insufficient bilingual markers (en={en_hits}, id={id_hits})', 'evidence_refs': []}
    # Find approximate split: position of first ID-only marker
    id_only = ['bahasa indonesia','terjemahan',' dan ',' yang ',' adalah ',' dengan ']
    first_id = min((low.find(m) for m in id_only if low.find(m) != -1), default=-1)
    en_only = [' the ',' and ',' is ',' of ',' to ']
    first_en = min((low.find(m) for m in en_only if low.find(m) != -1), default=-1)
    if first_en == -1 or first_id == -1:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Could not locate both language segments', 'evidence_refs': []}
    if first_en < first_id:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'English segment appears before Indonesian segment', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Indonesian appears before English or order unclear', 'evidence_refs': []}
