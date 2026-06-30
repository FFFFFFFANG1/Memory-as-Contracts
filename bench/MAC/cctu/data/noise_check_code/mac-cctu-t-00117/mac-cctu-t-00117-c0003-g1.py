def evaluate(trace):
    import json
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    parsed_json = None
    try:
        parsed_json = json.loads(response.strip())
    except Exception:
        parsed_json = None
    if not isinstance(parsed_json, dict):
        reasons.append('valid json object missing')
    tool_names = [str(call.get('name') or '') for call in tool_calls if call.get('name')]
    tool_count = len(tool_names)
    _count_global_language_statistics_v2 = sum(1 for name in tool_names if name == 'global_language_statistics_v2')
    if _count_global_language_statistics_v2 > 2:
        reasons.append('global_language_statistics_v2' + ' call count ' + str(_count_global_language_statistics_v2) + ' above 2')
    _count_language_speaker_estimator = sum(1 for name in tool_names if name == 'language_speaker_estimator')
    if _count_language_speaker_estimator > 2:
        reasons.append('language_speaker_estimator' + ' call count ' + str(_count_language_speaker_estimator) + ' above 2')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
