def evaluate(trace):
 import re
 calls = trace.get('tool_calls') or []
 n = len(calls)
 final = (trace.get('final_response') or '').strip()
 if not final:
  return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
 # count sentences via terminal punctuation
 parts = [p for p in re.split(r'(?<=[.!?])\s+', final) if p.strip()]
 sentences = len(parts)
 # telegram-style: terse, no first-person filler; allow lack of terminal punct
 if sentences == 0:
  sentences = 1
 within_calls = n <= 3
 one_sentence = sentences == 1
 followed = within_calls and one_sentence
 reason = f'tool_calls={n}, sentences={sentences}'
 return {'observed_followed': bool(followed), 'confidence':'high' if (within_calls is not None) else 'low', 'reason': reason, 'evidence_refs': []}
