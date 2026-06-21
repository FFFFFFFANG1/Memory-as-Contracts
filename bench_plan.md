# idea: turn long instuction short, but crud complex

## context
1. start from code-base.
2. task分布上：
	69 ██████████  Cline_Prompt (10 tasks)          ← 断层
	23 ████        Manus (10 tasks)
	16 ██          Cursor chat / Lovable / DeepSeek  ← 第三梯队
	12 ██
	9 █
	5 █
	3 ████████████████████████████████████  382 tasks (78.6%)
	2 ████████████
	1 ████████

3. constraint sequence 长度（eval_step3_base_v2.validated.json, 476 tasks）：

	easy (220 tasks, 1 graph, avg=5.1, median=5, range 5–6):
	   5 ████████████████████████████████████████  195 (88.6%)   ← 1 graph × ~5条
	   6 █████                                     25 (11.4%)

	normal (216 tasks, 2+ graphs, avg=16.3, median=15, range 9–48):
	   9 █                                           2 (0.9%)
	  10 ████████████████████████████████████████   60 (27.8%)   ← 2 graphs
	  11 ████████████████████                       30 (13.9%)
	  16 █████████████                              19 (8.8%)   ← 3 graphs
	  15 ███████████████████                        29 (13.4%)
	  12 █████                                       7 (3.2%)
	  17 ███                                         5 (2.3%)
	  21 ███                                         5 (2.3%)
	  26 █████                                       7 (3.2%)
	  27 █                                           2 (0.9%)
	  14–48 (tail)                                 50 (23.1%)

	hard (40 tasks, avg=79.5, median=67, range 58–124):
	  65 ████████████████████                       2 (5.0%)   ← 12–16 graphs
	  66 ██████████                                 1 (2.5%)
	 124 ██████████                                 1 (2.5%)   ← 23 graphs
	  58–70, 72–88, 111–124 (其余)                36 (90.0%)

	← easy / normal 在 6–9 处断层（1 graph vs 2+ graphs）；normal / hard 在 ~50 处断层（最长 48 vs 最短 58）

4. task chain length (step4 user-only histories, 476 tasks, tiktoken cl100k_base):

	easy (220 tasks): avg 10.0 turns/task, avg 1,236 tokens/task
	normal (216 tasks): avg 49.4 turns/task, avg 5,995 tokens/task
	hard (40 tasks): avg 128.3 turns/task, avg 13,052 tokens/task


## main pipeline
for each task:
	extract all constraints
	for each c in constraints:
		construct some noisy_constraints followed by certain constraint
		validate by graph
		
	generate one task claiming c
	for each nc in noisy_constaints:
		generate one task claiming nc
	gather all task, construct task_chain, shuffle?
	# so, final task will not contain any constraint in-context
		
	for each t in task_chain:
		somehow also generate the trace


## steps
step 0: filter structure
    - remove cn
    - remove multi-turn

step 1: extract cm-candidtate
    for every constraint, judge if it's code-based:
        if code-based: pass
        if not code, if in user:
            llm judge if it's a preference
            if preference, add to cm-candidtate
    

step 2: 改写constraint
    对于每一个constraint: 
        生成conflict, 并且用scope区分
        四套prompt：global/project/phase + exception
	
	merge algorithm:
	for every task, prepare a constraint sequence cs = []
	for every constraint graph cg in a task:
		if cs is empty:
			cs = cg.copy()
		else:
			for every cosntraint c in cg:
				randomly insert at one index in cs, denoted as id_current
			# the next insertion can only happens between [id_current = 1, length(cg)]
			# if id_current already at the end of cs, then directly append the rest of cg to cs's end


step 3: for constraint, merge it into a task description
	for each task:
		for each constraint c in constraint sequence:
			if c is global:
				use tone like "always remeber ..."
			if c is project:
				use tone like "in this project, always ..."
			if c is phase:
				use tone like "when doing this part in the project, always ..."
			if c is exception:
				use tone like "for this time, do ..." or "<give a specific condition>, do exception"
			and generate the task chain.
	
	for llm:
		input should be current system prompt, constraint, project+phase (if scope applied)
		output should be a user prompt containing task description + constraint
			should also output response? - no
			should directly output multiple user prompt? - yes
	unify the number of task history to easy: ~10, normal: 40-60, hard: 100-150
	finally, merge preference as global to some task.

	key point: each user turn should be a realistic task the requirement should be naturally included in the task description

	key point: bench only has user turn, no assistant response, because we only focus on "user requirement".


step 4: agent system tool
	per-agent design agentic tools?
	input: system prompt
	output: several tool schema
