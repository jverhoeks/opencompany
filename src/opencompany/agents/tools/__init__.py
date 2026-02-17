from opencompany.agents.tools.code import grep_code, list_files, read_file
from opencompany.agents.tools.company import fire_persona, hire_persona, list_team
from opencompany.agents.tools.tickets import create_ticket, list_tickets, update_ticket

ALL_TOOLS = {
    "create_ticket": create_ticket,
    "list_tickets": list_tickets,
    "update_ticket": update_ticket,
    "read_file": read_file,
    "grep_code": grep_code,
    "list_files": list_files,
    "hire_persona": hire_persona,
    "fire_persona": fire_persona,
    "list_team": list_team,
}
