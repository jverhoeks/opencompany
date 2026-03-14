# New Hire SOP

## When HR receives a hiring ticket, follow these steps:

1. **Check capacity first**:
   - Use `list_team` to see current headcount by role
   - If someone in that role already exists and is active, reject the hire
   - If team is at max capacity (12), reject the hire

2. **Select the right role**:
   - Match the hiring request to an existing role in the catalog
   - If no matching role exists, ask the CEO to create one first

3. **Hire the persona**:
   - Use `hire_persona` with a descriptive persona ID (lowercase, hyphens)
   - Set `reports_to` based on the org hierarchy
   - Include a backstory that fits the company culture

4. **Post-hire verification**:
   - Confirm the new hire appears in `list_team`
   - Check if any open tickets now match the new hire's skills
   - Update the hiring ticket status to "done"
