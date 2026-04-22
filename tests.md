# Test Report

**Date:** 2026-04-22 18:20  


## Summary

| Metric | Count |
|--------|-------|
| Total  | 83 |
| Passed | 83 |
| Failed | 0 |
| Errors | 0 |
| Skipped | 0 |
| **Coverage** | **0%** |

## Test Results

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

### test_config_roles.py (4/4 passed) ok

| Test | Status |
|------|--------|
| `test_update_role` | pass |
| `test_update_role_not_found` | pass |
| `test_delete_role` | pass |
| `test_delete_role_not_found` | pass |

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

### test_main.py (14/14 passed) ok

| Test | Status |
|------|--------|
| `test_app_exists` | pass |
| `test_app_has_routers` | pass |
| `test_main_function` | pass |
| `test_main_function_with_reload` | pass |
| `test_cors_default_origins` | pass |
| `test_wait_for_db_success` | pass |
| `test_wait_for_db_retries_then_succeeds` | pass |
| `test_wait_for_db_exhausted_retries` | pass |
| `test_lifespan_startup_shutdown` | pass |
| `test_lifespan_no_telegram` | pass |
| `test_root_returns_html` | pass |
| `test_health_all_ok` | pass |
| `test_health_db_error` | pass |
| `test_health_redis_error` | pass |

### test_sprint4_concurrency.py (3/3 passed) ok

| Test | Status |
|------|--------|
| `test_concurrent_tasks_blocked_by_semaphore` | pass |
| `test_get_persona_lock_creates_semaphore` | pass |
| `test_get_persona_lock_custom_concurrency` | pass |
