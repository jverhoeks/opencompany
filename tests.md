# Test Report

**Date:** 2026-02-22 18:08  


## Summary

| Metric | Count |
|--------|-------|
| Total  | 143 |
| Passed | 143 |
| Failed | 0 |
| Errors | 0 |
| Skipped | 0 |
| **Coverage** | **61%** |

## Test Results

### test_bus.py (2/2 passed) ok

| Test | Status |
|------|--------|
| `test_publish_serializes_and_sends` | pass |
| `test_publish_different_event_types` | pass |

### test_config.py (9/9 passed) ok

| Test | Status |
|------|--------|
| `test_load_company_config` | pass |
| `test_get_role` | pass |
| `test_get_role_missing` | pass |
| `test_get_org_routing` | pass |
| `test_load_config_missing_file` | pass |
| `test_config_caching` | pass |
| `test_add_role` | pass |
| `test_add_role_duplicate` | pass |
| `test_load_real_company_yaml` | pass |

### test_dashboard.py (3/3 passed) ok

| Test | Status |
|------|--------|
| `test_overview_empty` | pass |
| `test_overview_with_personas_and_tickets` | pass |
| `test_overview_work_log` | pass |

### test_e2e.py (53/53 passed) ok

| Test | Status |
|------|--------|
| `test_health` | pass |
| `test_list_personas_empty` | pass |
| `test_list_personas_seeded` | pass |
| `test_get_persona` | pass |
| `test_get_persona_not_found` | pass |
| `test_create_ticket` | pass |
| `test_create_ticket_defaults` | pass |
| `test_list_tickets_by_status` | pass |
| `test_list_tickets_empty_status` | pass |
| `test_create_ticket_with_context` | pass |
| `test_chat_persona_not_found` | pass |
| `test_chat_with_persona` | pass |
| `test_chat_returns_agent_response` | pass |
| `test_ticket_lifecycle` | pass |
| `test_multiple_tickets_ordering` | pass |
| `test_engine_auto_assign` | pass |
| `test_engine_no_solver_available` | pass |
| `test_seed_company` | pass |
| `test_seed_company_skips_if_personas_exist` | pass |
| `test_full_org_is_seeded` | pass |
| `test_org_roles` | pass |
| `test_backend_ticket_auto_assigned_to_jamie` | pass |
| `test_frontend_ticket_auto_assigned_to_sam` | pass |
| `test_marketing_ticket_auto_assigned` | pass |
| `test_sales_ticket_auto_assigned` | pass |
| `test_ceo_ticket_routes_to_pm` | pass |
| `test_tech_lead_reviews_backlog_via_chat` | pass |
| `test_full_sprint_lifecycle` | pass |
| `test_workload_balancing_across_solvers` | pass |
| `test_seed_real_company_yaml` | pass |
| `test_fuzzy_tag_matching_exact` | pass |
| `test_fuzzy_tag_matching_substring` | pass |
| `test_fuzzy_tag_matching_reverse_substring` | pass |
| `test_engine_escalates_to_ceo` | pass |
| `test_sweep_routes_orphaned_tickets` | pass |
| `test_api_rejects_without_key` | pass |
| `test_api_rejects_wrong_key` | pass |
| `test_api_accepts_correct_key` | pass |
| `test_dashboard_stream_requires_auth` | pass |
| `test_dashboard_overview_requires_auth` | pass |
| `test_overseer_messages_requires_auth` | pass |
| `test_overseer_reply_requires_auth` | pass |
| `test_budget_check_unlimited` | pass |
| `test_budget_check_and_consume` | pass |
| `test_budget_reset` | pass |
| `test_budget_status` | pass |
| `test_budget_api_list` | pass |
| `test_budget_api_reset` | pass |
| `test_seed_populates_model_id` | pass |
| `test_engine_budget_blocks_over_budget_persona` | pass |
| `test_heartbeat_triggers_idle_personas` | pass |
| `test_heartbeat_skips_busy_personas` | pass |
| `test_heartbeat_skips_over_budget` | pass |

### test_memory.py (9/9 passed) ok

| Test | Status |
|------|--------|
| `test_store_and_recall` | pass |
| `test_recall_filters` | pass |
| `test_build_memory_context` | pass |
| `test_build_memory_context_empty` | pass |
| `test_compaction` | pass |
| `test_compaction_below_threshold` | pass |
| `test_remember_tool` | pass |
| `test_recall_tool` | pass |
| `test_recall_tool_empty` | pass |

### test_models.py (4/4 passed) ok

| Test | Status |
|------|--------|
| `test_persona_creation` | pass |
| `test_ticket_creation` | pass |
| `test_persona_defaults` | pass |
| `test_work_log_creation` | pass |

### test_personality.py (4/4 passed) ok

| Test | Status |
|------|--------|
| `test_personality_injected_in_prompt` | pass |
| `test_personality_falls_back_to_role` | pass |
| `test_no_personality_no_crash` | pass |
| `test_persona_personality_overrides_role` | pass |

### test_personas.py (7/7 passed) ok

| Test | Status |
|------|--------|
| `test_hire_persona` | pass |
| `test_hire_duplicate_persona` | pass |
| `test_fire_persona` | pass |
| `test_fire_nonexistent_persona` | pass |
| `test_list_personas` | pass |
| `test_list_personas_excludes_fired` | pass |
| `test_list_personas_filter_by_reports_to` | pass |

### test_runner.py (3/3 passed) ok

| Test | Status |
|------|--------|
| `test_build_system_prompt_from_config` | pass |
| `test_build_system_prompt_solver` | pass |
| `test_build_system_prompt_fallback_no_role` | pass |

### test_scenarios.py (5/5 passed) ok

| Test | Status |
|------|--------|
| `test_scenario_landing_page` | pass |
| `test_scenario_personality_injection` | pass |
| `test_scenario_trust_boundaries` | pass |
| `test_scenario_stale_escalation` | pass |
| `test_scenario_sprint_with_memory` | pass |

### test_taskboard.py (5/5 passed) ok

| Test | Status |
|------|--------|
| `test_find_best_solver_matches_skills` | pass |
| `test_find_best_solver_prefers_lower_workload` | pass |
| `test_find_best_solver_no_match_falls_back_to_least_busy` | pass |
| `test_find_best_solver_empty_solvers` | pass |
| `test_find_best_solver_multiple_tag_overlap` | pass |

### test_tools.py (20/20 passed) ok

| Test | Status |
|------|--------|
| `test_ticket_tool_schema` | pass |
| `test_code_tool_schema` | pass |
| `test_company_tool_schema` | pass |
| `test_all_tools_registry` | pass |
| `test_read_file_returns_contents` | pass |
| `test_read_file_missing_file` | pass |
| `test_list_files_shows_directory_contents` | pass |
| `test_list_files_with_pattern` | pass |
| `test_grep_code_finds_pattern` | pass |
| `test_grep_code_no_matches` | pass |
| `test_create_ticket_tool_calls_sync` | pass |
| `test_list_tickets_tool_formats_output` | pass |
| `test_list_tickets_tool_empty` | pass |
| `test_update_ticket_tool` | pass |
| `test_hire_persona_tool` | pass |
| `test_fire_persona_tool` | pass |
| `test_list_team_tool_with_data` | pass |
| `test_list_team_tool_empty` | pass |
| `test_web_fetch_bad_url` | pass |
| `test_web_fetch_strips_html` | pass |

### test_trust.py (12/12 passed) ok

| Test | Status |
|------|--------|
| `test_ceo_gets_full_tier` | pass |
| `test_hr_gets_full_tier` | pass |
| `test_manager_gets_full_tier` | pass |
| `test_solver_gets_solver_tier` | pass |
| `test_lead_gets_lead_tier` | pass |
| `test_unknown_type_gets_external_tier` | pass |
| `test_full_tier_can_use_all_tools` | pass |
| `test_solver_denied_dangerous_tools` | pass |
| `test_external_read_only` | pass |
| `test_lead_tier_access` | pass |
| `test_web_fetch_requires_solver_tier` | pass |
| `test_tier_levels_ordered` | pass |

### test_workspaces.py (7/7 passed) ok

| Test | Status |
|------|--------|
| `test_persona_writes_to_private_workspace` | pass |
| `test_persona_reads_shared_workspace` | pass |
| `test_publish_file_copies_to_shared` | pass |
| `test_workspace_path_escape_blocked` | pass |
| `test_publish_file_requires_persona_id` | pass |
| `test_publish_file_missing_source` | pass |
| `test_default_workspace_still_works` | pass |

## Coverage

| Module | Stmts | Miss | Cover |
|--------|-------|------|-------|
| `opencompany/__init__.py` | 0 | 0 | 100% |
| `opencompany/agents/__init__.py` | 0 | 0 | 100% |
| `opencompany/agents/prompts.py` | 59 | 4 | 93% |
| `opencompany/agents/runner.py` | 57 | 37 | 35%! |
| `opencompany/agents/tools/__init__.py` | 8 | 0 | 100% |
| `opencompany/agents/tools/code.py` | 87 | 11 | 87% |
| `opencompany/agents/tools/company.py` | 31 | 8 | 74% |
| `opencompany/agents/tools/memory.py` | 21 | 0 | 100% |
| `opencompany/agents/tools/messaging.py` | 6 | 3 | 50% |
| `opencompany/agents/tools/overseer.py` | 7 | 4 | 42%! |
| `opencompany/agents/tools/tickets.py` | 22 | 0 | 100% |
| `opencompany/agents/tools/web.py` | 47 | 28 | 40%! |
| `opencompany/company/__init__.py` | 0 | 0 | 100% |
| `opencompany/company/budget.py` | 68 | 15 | 77% |
| `opencompany/company/config.py` | 65 | 4 | 93% |
| `opencompany/company/engine.py` | 259 | 98 | 62% |
| `opencompany/company/memory.py` | 57 | 1 | 98% |
| `opencompany/company/messaging.py` | 19 | 19 | 0%! |
| `opencompany/company/overseer.py` | 32 | 32 | 0%! |
| `opencompany/company/personas.py` | 104 | 34 | 67% |
| `opencompany/company/scheduler.py` | 68 | 42 | 38%! |
| `opencompany/company/seed.py` | 50 | 8 | 84% |
| `opencompany/company/taskboard.py` | 77 | 37 | 51% |
| `opencompany/company/trust.py` | 27 | 0 | 100% |
| `opencompany/events/__init__.py` | 0 | 0 | 100% |
| `opencompany/events/bus.py` | 86 | 60 | 30%! |
| `opencompany/gateway/__init__.py` | 0 | 0 | 100% |
| `opencompany/gateway/api.py` | 109 | 17 | 84% |
| `opencompany/gateway/channels/__init__.py` | 0 | 0 | 100% |
| `opencompany/gateway/channels/telegram.py` | 47 | 47 | 0%! |
| `opencompany/gateway/dashboard.py` | 78 | 29 | 62% |
| `opencompany/main.py` | 110 | 110 | 0%! |
| `opencompany/models/__init__.py` | 5 | 0 | 100% |
| `opencompany/models/base.py` | 3 | 0 | 100% |
| `opencompany/models/db.py` | 69 | 0 | 100% |
| `opencompany/models/engine.py` | 8 | 2 | 75% |
| `opencompany/utils.py` | 12 | 8 | 33%! |
| **TOTAL** | **1698** | **658** | **61%** |
