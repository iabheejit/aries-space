Start a new milestone:
1. Ask Abheejit: what are we building and why?
2. Draft a plan at .claude/plans/milestone-{N}-{slug}.md using references/plan-template.md
3. Present the plan and ask for confirmation
4. Once confirmed: spawn the plan-reviewer agent (Vikram)
5. If Vikram returns READY: add row to .claude/milestones.md (status: IN_PROGRESS), create branch milestone/{N}-{slug}, log version bump in .claude/versions.md
6. If Vikram returns REFINE or REWORK_PLAN: surface his findings and iterate before proceeding
