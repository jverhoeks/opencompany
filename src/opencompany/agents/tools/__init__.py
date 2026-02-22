from opencompany.agents.tools.code import (
    grep_code,
    list_files,
    publish_file,
    read_file,
    write_file,
)
from opencompany.agents.tools.company import create_role, fire_persona, hire_persona, list_team
from opencompany.agents.tools.memory import recall, remember
from opencompany.agents.tools.messaging import send_message
from opencompany.agents.tools.overseer import contact_overseer
from opencompany.agents.tools.tickets import create_ticket, list_tickets, update_ticket
from opencompany.agents.tools.web import web_fetch, web_search

ALL_TOOLS = {
    "create_ticket": create_ticket,
    "list_tickets": list_tickets,
    "update_ticket": update_ticket,
    "read_file": read_file,
    "grep_code": grep_code,
    "list_files": list_files,
    "write_file": write_file,
    "create_role": create_role,
    "hire_persona": hire_persona,
    "fire_persona": fire_persona,
    "list_team": list_team,
    "contact_overseer": contact_overseer,
    "send_message": send_message,
    "web_search": web_search,
    "web_fetch": web_fetch,
    "publish_file": publish_file,
    "remember": remember,
    "recall": recall,
}
