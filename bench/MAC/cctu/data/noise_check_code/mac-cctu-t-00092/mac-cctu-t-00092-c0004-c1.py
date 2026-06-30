def evaluate(trace):
 import re
 traj = trace.get('trajectory') or []
 tool_calls = trace.get('tool_calls') or []
 # Find first assistant text content and first tool call iteration
 first_tool_iter = None
 if tool_calls:
  iters = [tc.get('iteration') for tc in tool_calls if tc.get('iteration') is not None]
  if iters:
   first_tool_iter = min(iters)
 # Find earliest assistant step with text content
 decomposition_text = None
 decomposition_iter = None
 for i, step in enumerate(traj):
  content = step.get('content') if isinstance(step, dict) else None
  if content and isinstance(content, str) and content.strip():
   decomposition_text = content
   decomposition_iter = i
   break
 if decomposition_text is None:
  return {'observed_followed': None, 'confidence':'unknown','reason':'No assistant text content found before tool calls','evidence_refs':[]}
 # Check if it contains a single-line semicolon enumeration
 # Take the first non-empty line
 lines = [l for l in decomposition_text.splitlines() if l.strip()]
 has_semicolon_line = any(';' in l and l.count(';') >= 1 for l in lines)
 if not has_semicolon_line:
  return {'observed_followed': False, 'confidence':'medium','reason':'No semicolon-separated enumeration line found in initial assistant message','evidence_refs':[decomposition_text[:200]]}
 # Check ordering: was a tool called before this decomposition step?
 # If trajectory steps include tool calls inline, check if any tool call iteration precedes decomposition_iter
 if first_tool_iter is not None and decomposition_iter is not None:
  if first_tool_iter < decomposition_iter:
   return {'observed_followed': False, 'confidence':'high','reason':'Tool invoked before decomposition enumeration was recorded','evidence_refs':[]}
 return {'observed_followed': True, 'confidence':'medium','reason':'Initial assistant message contains semicolon-separated enumeration and no tool calls preceded it','evidence_refs':[lines[0][:200] if lines else '']}
