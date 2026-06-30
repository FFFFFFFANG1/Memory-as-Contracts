def evaluate(trace):
    tcs = trace.get('tool_calls') or []
    if not tcs:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls', 'evidence_refs': []}
    train_tools = {'train_specification_retriever', 'train_speed_analyzer'}
    # group by iteration (same turn)
    turns = {}
    for c in tcs:
        key = c.get('iteration', c.get('index'))
        turns.setdefault(key, []).append(c.get('name'))
    violations = []
    # check movie_feature_locator co-occurring with any train tool in the same turn
    for k, names in turns.items():
        if 'movie_feature_locator' in names and any(n in train_tools for n in names):
            violations.append(f'turn {k}: movie_feature_locator with train tool ({names})')
    # check director/movie lookups exclusively use director_genre_identifier
    # heuristic: movie_feature_locator usage implies non-exclusive movie lookup
    mfl_calls = [c for c in tcs if c.get('name') == 'movie_feature_locator']
    if mfl_calls:
        violations.append(f'movie_feature_locator invoked {len(mfl_calls)} time(s); director/movie lookups must use only director_genre_identifier')
    if violations:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(violations), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'no movie_feature_locator misuse and no co-turn with train tools', 'evidence_refs': []}
