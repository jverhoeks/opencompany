# Project Kickoff SOP

## When the CEO creates a new project, follow these steps:

1. **Research phase** (if researcher persona is available):
   - Create a research ticket tagged `research` with the project domain
   - Wait for research findings before proceeding to design

2. **Planning phase** (PM):
   - Review research findings in `workspace/research/`
   - Break the project into 3-7 tickets with clear acceptance criteria
   - Tag tickets appropriately: `backend`, `frontend`, `design`, `marketing`
   - Set priorities: the critical path gets `high`, everything else `medium`

3. **Assignment phase** (automatic):
   - Tickets route through the org hierarchy
   - Leads assign to solvers based on skill match

4. **Execution** (solvers):
   - Each solver works on one ticket at a time
   - Save all deliverables to workspace using `write_file`
   - Submit for review when done (`update_ticket` with status=`review`)

5. **Review** (leads/managers):
   - Follow the Code Review SOP for code tickets
   - Marketing copy gets reviewed by the marketing lead

6. **Completion**:
   - When all tickets are done, snapshot the company state
   - CEO reviews final deliverables and reports to overseer
