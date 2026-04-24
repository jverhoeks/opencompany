# Test Report

**Date:** 2026-04-24 15:07  


## Summary

| Metric | Count |
|--------|-------|
| Total  | 444 |
| Passed | 442 |
| Failed | 0 |
| Errors | 0 |
| Skipped | 2 |
| **Coverage** | **0%** |

## Test Results

### test_budget_cov.py (17/17 passed) ok

| Test | Status |
|------|--------|
| `test_check_budget_nonexistent` | pass |
| `test_check_budget_unlimited` | pass |
| `test_check_budget_auto_reset_on_new_day` | pass |
| `test_check_budget_no_reset_at` | pass |
| `test_check_budget_exhausted` | pass |
| `test_check_budget_partial_remaining` | pass |
| `test_consume_tokens_zero_total` | pass |
| `test_consume_tokens_nonexistent` | pass |
| `test_consume_tokens_accumulates` | pass |
| `test_consume_tokens_sets_budget_reset_at` | pass |
| `test_reset_budget_found` | pass |
| `test_reset_budget_not_found` | pass |
| `test_reset_all_budgets` | pass |
| `test_get_budget_status_found` | pass |
| `test_get_budget_status_not_found` | pass |
| `test_get_budget_status_unlimited` | pass |
| `test_get_all_budget_statuses` | pass |

### test_bus.py (2/2 passed) ok

| Test | Status |
|------|--------|
| `test_publish_serializes_and_sends` | pass |
| `test_publish_different_event_types` | pass |

### test_bus_cov.py (14/15 passed) ok

| Test | Status |
|------|--------|
| `test_init_redis_creates_pool_and_client` | pass |
| `test_init_redis_is_idempotent` | pass |
| `test_close_redis_cleans_up` | pass |
| `test_close_redis_noop_when_not_initialized` | pass |
| `test_get_redis_returns_existing` | pass |
| `test_get_redis_initializes_lazily` | pass |
| `test_ping_returns_true_when_reachable` | pass |
| `test_ping_returns_false_on_error` | pass |
| `test_ensure_consumer_group_creates_group` | pass |
| `test_ensure_consumer_group_ignores_busygroup` | pass |
| `test_ensure_consumer_group_raises_other_errors` | pass |
| `test_subscribe_processes_messages_and_acks` | pass |
| `test_subscribe_handles_empty_read` | pass |
| `test_subscribe_handles_callback_error` | pass |
| `test_subscribe_retries_on_transient_error` | skip |

### test_company_tools_cov.py (8/8 passed) ok

| Test | Status |
|------|--------|
| `test_create_role_tool_success` | pass |
| `test_create_role_tool_no_optional_fields` | pass |
| `test_create_role_tool_already_exists` | pass |
| `test_create_role_tool_file_not_found` | pass |
| `test_fire_persona_tool_delegates` | pass |
| `test_fire_persona_tool_default_reason` | pass |
| `test_hire_persona_tool_with_tools_and_picks_up` | pass |
| `test_list_team_with_reports_to` | pass |

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

### test_dashboard.py (3/3 passed) ok

| Test | Status |
|------|--------|
| `test_overview_empty` | pass |
| `test_overview_with_personas_and_tickets` | pass |
| `test_overview_work_log` | pass |

### test_dashboard_cov.py (13/14 passed) ok

| Test | Status |
|------|--------|
| `test_serve_dashboard_returns_html` | pass |
| `test_workspace_file_not_found` | pass |
| `test_workspace_file_path_traversal` | pass |
| `test_workspace_serves_existing_file` | pass |
| `test_overseer_list_messages` | pass |
| `test_overseer_reply_message_not_found` | pass |
| `test_overseer_reply_success` | pass |
| `test_overseer_reply_no_persona` | pass |
| `test_overview_persona_fields` | pass |
| `test_soul_update_endpoint` | pass |
| `test_overview_includes_fired_personas` | pass |
| `test_overview_includes_reports_to` | pass |
| `test_patch_persona_config_name_and_role` | pass |
| `test_dashboard_stream_returns_sse` | skip |

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

### test_engine_cov.py (34/34 passed) ok

| Test | Status |
|------|--------|
| `test_handle_event_dispatches_ticket_created` | pass |
| `test_handle_event_dispatches_ticket_review` | pass |
| `test_handle_event_ignores_unknown_type` | pass |
| `test_handle_event_catches_errors` | pass |
| `test_set_persona_state` | pass |
| `test_set_persona_state_missing_persona` | pass |
| `test_set_ticket_in_progress` | pass |
| `test_set_ticket_in_progress_skips_done_ticket` | pass |
| `test_add_ticket_tokens` | pass |
| `test_add_ticket_tokens_missing_ticket` | pass |
| `test_trigger_review_falls_back_to_manager` | pass |
| `test_trigger_review_ticket_not_found` | pass |
| `test_spawn_persona_task_full_run` | pass |
| `test_spawn_persona_task_error_sets_blocked` | pass |
| `test_on_persona_idle_claims_ticket` | pass |
| `test_on_persona_idle_no_tickets` | pass |
| `test_on_persona_idle_inactive_persona` | pass |
| `test_hr_pickup_finds_hr_tagged_tickets` | pass |
| `test_hr_pickup_ignores_non_hr_tickets` | pass |
| `test_escalate_to_ceo` | pass |
| `test_escalate_to_ceo_inactive` | pass |
| `test_build_task_prompt` | pass |
| `test_get_routing_target_no_creator` | pass |
| `test_get_routing_target_by_id` | pass |
| `test_get_routing_target_by_role_type` | pass |
| `test_get_routing_target_lead_default` | pass |
| `test_find_lead_for_tags_exact_match` | pass |
| `test_find_lead_for_tags_no_match` | pass |
| `test_sweep_no_orphans` | pass |
| `test_sweep_handles_route_error` | pass |
| `test_start_event_listener` | pass |
| `test_hr_tagged_ticket_routes_to_hr` | pass |
| `test_route_ticket_skips_assigned` | pass |
| `test_route_ticket_no_config` | pass |

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

### test_messaging.py (4/4 passed) ok

| Test | Status |
|------|--------|
| `test_deliver_message_success` | pass |
| `test_deliver_message_sender_not_found` | pass |
| `test_deliver_message_recipient_not_found` | pass |
| `test_deliver_message_recipient_not_active` | pass |

### test_messaging_tools.py (4/4 passed) ok

| Test | Status |
|------|--------|
| `test_send_message_calls_run_async` | pass |
| `test_send_message_returns_run_async_result` | pass |
| `test_contact_overseer_returns_confirmation` | pass |
| `test_contact_overseer_includes_message_id` | pass |

### test_models.py (4/4 passed) ok

| Test | Status |
|------|--------|
| `test_persona_creation` | pass |
| `test_ticket_creation` | pass |
| `test_persona_defaults` | pass |
| `test_work_log_creation` | pass |

### test_overseer.py (6/6 passed) ok

| Test | Status |
|------|--------|
| `test_store_message` | pass |
| `test_reply_to_message` | pass |
| `test_reply_to_nonexistent_message` | pass |
| `test_list_messages_all` | pass |
| `test_list_messages_pending_only` | pass |
| `test_list_messages_empty` | pass |

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

### test_personas_cov.py (13/13 passed) ok

| Test | Status |
|------|--------|
| `test_hire_invalid_persona_id` | pass |
| `test_hire_with_all_optional_fields` | pass |
| `test_hire_loads_role_config` | pass |
| `test_hire_post_sweep` | pass |
| `test_hire_post_sweep_failure` | pass |
| `test_fire_persona_reassigns_orphaned_tickets` | pass |
| `test_append_to_company_yaml` | pass |
| `test_append_to_company_yaml_no_file` | pass |
| `test_append_to_company_yaml_already_exists` | pass |
| `test_append_to_company_yaml_exception` | pass |
| `test_hire_persona_sync_wrapper` | pass |
| `test_fire_persona_sync_wrapper` | pass |
| `test_list_personas_sync_wrapper` | pass |

### test_policy.py (21/21 passed) ok

| Test | Status |
|------|--------|
| `test_create_policy` | pass |
| `test_approve_policy` | pass |
| `test_approve_policy_requires_manager_or_lead` | pass |
| `test_approve_non_draft_fails` | pass |
| `test_reject_policy` | pass |
| `test_reject_policy_requires_manager_or_lead` | pass |
| `test_list_policies` | pass |
| `test_get_policy_not_found` | pass |
| `test_build_policy_context_wildcard` | pass |
| `test_build_policy_context_role_match` | pass |
| `test_build_policy_context_persona_id_match` | pass |
| `test_build_policy_context_tag_skill_match` | pass |
| `test_build_policy_context_draft_excluded` | pass |
| `test_build_policy_context_empty` | pass |
| `test_write_policy_tool` | pass |
| `test_approve_policy_tool` | pass |
| `test_approve_policy_tool_error` | pass |
| `test_list_policies_tool` | pass |
| `test_list_policies_tool_empty` | pass |
| `test_read_policy_tool` | pass |
| `test_read_policy_tool_not_found` | pass |

### test_runner.py (3/3 passed) ok

| Test | Status |
|------|--------|
| `test_build_system_prompt_from_config` | pass |
| `test_build_system_prompt_solver` | pass |
| `test_build_system_prompt_fallback_no_role` | pass |

### test_runner_cov.py (16/16 passed) ok

| Test | Status |
|------|--------|
| `test_register_tool` | pass |
| `test_get_model_uses_env_litellm` | pass |
| `test_get_model_explicit_model_id` | pass |
| `test_get_model_bedrock_default` | pass |
| `test_get_model_bedrock_explicit` | pass |
| `test_create_agent_resolves_tools_from_registry` | pass |
| `test_create_agent_skips_missing_tools` | pass |
| `test_create_agent_extra_tools` | pass |
| `test_create_agent_sets_name_and_description` | pass |
| `test_agent_result_defaults` | pass |
| `test_agent_result_with_metrics` | pass |
| `test_run_persona_happy_path` | pass |
| `test_run_persona_strips_thinking_tags` | pass |
| `test_run_persona_extracts_token_metrics` | pass |
| `test_run_persona_error_handling` | pass |
| `test_run_persona_metrics_with_none_values` | pass |

### test_scenarios.py (5/5 passed) ok

| Test | Status |
|------|--------|
| `test_scenario_landing_page` | pass |
| `test_scenario_personality_injection` | pass |
| `test_scenario_trust_boundaries` | pass |
| `test_scenario_stale_escalation` | pass |
| `test_scenario_sprint_with_memory` | pass |

### test_scheduler_cov.py (12/12 passed) ok

| Test | Status |
|------|--------|
| `test_sweep_job_calls_sweep` | pass |
| `test_sweep_job_handles_exception` | pass |
| `test_ceo_kickoff_triggers_ceo` | pass |
| `test_ceo_kickoff_skips_inactive_ceo` | pass |
| `test_ceo_kickoff_skips_busy_ceo` | pass |
| `test_ceo_kickoff_skips_over_budget` | pass |
| `test_ceo_kickoff_handles_exception` | pass |
| `test_ceo_kickoff_no_ceo` | pass |
| `test_start_scheduler_adds_sweep_job` | pass |
| `test_start_scheduler_with_ceo_kickoff` | pass |
| `test_start_scheduler_with_heartbeat` | pass |
| `test_start_scheduler_with_all_jobs` | pass |

### test_sprint1.py (16/16 passed) ok

| Test | Status |
|------|--------|
| `test_ticket_has_budget_tokens_field` | pass |
| `test_check_task_budget_requeues_exhausted` | pass |
| `test_check_task_budget_allows_with_remaining` | pass |
| `test_check_task_budget_unlimited_when_zero` | pass |
| `test_claim_next_claims_best_match` | pass |
| `test_claim_next_returns_none_when_no_tickets` | pass |
| `test_claim_next_returns_none_for_inactive_persona` | pass |
| `test_claim_next_skips_assigned_tickets` | pass |
| `test_capacity_ratio_no_solvers` | pass |
| `test_capacity_ratio_balanced` | pass |
| `test_hire_rejected_when_capacity_sufficient` | pass |
| `test_hire_allowed_when_understaffed` | pass |
| `test_hire_rejected_at_team_cap` | pass |
| `test_expires_stale_tickets` | pass |
| `test_ignores_recent_tickets` | pass |
| `test_ignores_open_tickets` | pass |

### test_sprint10.py (6/6 passed) ok

| Test | Status |
|------|--------|
| `test_get_soul` | pass |
| `test_soul_history` | pass |
| `test_soul_rollback_api` | pass |
| `test_entrypoint_script_exists` | pass |
| `test_entrypoint_has_otel_toggle` | pass |
| `test_dockerfile_copies_soul_and_sops` | pass |

### test_sprint11_session.py (7/7 passed) ok

| Test | Status |
|------|--------|
| `test_save_and_load` | pass |
| `test_load_empty_when_no_session` | pass |
| `test_save_truncates_to_50` | pass |
| `test_clear` | pass |
| `test_load_handles_redis_error` | pass |
| `test_save_handles_redis_error` | pass |
| `test_returns_singleton` | pass |

### test_sprint2_events.py (5/5 passed) ok

| Test | Status |
|------|--------|
| `test_handle_event_dispatches_persona_idle` | pass |
| `test_handle_event_handles_persona_blocked` | pass |
| `test_spawn_publishes_idle_on_success` | pass |
| `test_spawn_publishes_blocked_on_error` | pass |
| `test_spawn_publishes_blocked_on_budget_exhausted` | pass |

### test_sprint3_metrics.py (2/2 passed) ok

| Test | Status |
|------|--------|
| `test_metrics_returns_per_persona_data` | pass |
| `test_metrics_empty_when_no_work` | pass |

### test_sprint4_concurrency.py (3/3 passed) ok

| Test | Status |
|------|--------|
| `test_concurrent_tasks_blocked_by_semaphore` | pass |
| `test_get_persona_lock_creates_semaphore` | pass |
| `test_get_persona_lock_custom_concurrency` | pass |

### test_sprint5_persona_config.py (9/9 passed) ok

| Test | Status |
|------|--------|
| `test_create_persona_config` | pass |
| `test_company_snapshot_model` | pass |
| `test_boot_seeds_from_yaml` | pass |
| `test_boot_skips_if_already_seeded` | pass |
| `test_snapshot_captures_state` | pass |
| `test_snapshot_skips_empty_config` | pass |
| `test_list_persona_configs` | pass |
| `test_patch_persona_config` | pass |
| `test_patch_nonexistent_config` | pass |

### test_sprint6_soul.py (13/13 passed) ok

| Test | Status |
|------|--------|
| `test_get_version_from_content` | pass |
| `test_count_rule_changes` | pass |
| `test_protected_rules_intact` | pass |
| `test_rejects_same_version` | pass |
| `test_rejects_too_many_changes` | pass |
| `test_rejects_missing_protected_rules` | pass |
| `test_rejects_too_many_lines` | pass |
| `test_accepts_valid_update` | pass |
| `test_propose_valid_update` | pass |
| `test_propose_invalid_rejected` | pass |
| `test_rollback_to_version` | pass |
| `test_rollback_nonexistent_version` | pass |
| `test_soul_injected_into_prompt` | pass |

### test_sprint7.py (7/7 passed) ok

| Test | Status |
|------|--------|
| `test_researcher_role_exists` | pass |
| `test_marketer_role_exists` | pass |
| `test_propose_soul_update_requires_lead` | pass |
| `test_solver_cannot_propose_soul_update` | pass |
| `test_lead_can_propose_soul_update` | pass |
| `test_read_soul_accessible_to_all` | pass |
| `test_tools_registered` | pass |

### test_sprint8_strands.py (7/7 passed) ok

| Test | Status |
|------|--------|
| `test_tool_registered` | pass |
| `test_requires_solver_tier` | pass |
| `test_external_denied` | pass |
| `test_solver_allowed` | pass |
| `test_on_tool_use_records_calls` | pass |
| `test_on_invocation_complete_consumes_budget` | pass |
| `test_summary` | pass |

### test_sprint9.py (9/9 passed) ok

| Test | Status |
|------|--------|
| `test_allows_hire_when_understaffed` | pass |
| `test_blocks_hire_when_sufficient` | pass |
| `test_ignores_non_hire_tools` | pass |
| `test_sop_files_exist` | pass |
| `test_load_sop_for_review_tag` | pass |
| `test_load_sop_for_hr_tag` | pass |
| `test_load_sop_for_unknown_tag` | pass |
| `test_load_sop_deduplicates` | pass |
| `test_load_sop_multiple_tags` | pass |

### test_taskboard.py (12/12 passed) ok

| Test | Status |
|------|--------|
| `test_find_best_solver_matches_skills` | pass |
| `test_find_best_solver_prefers_lower_workload` | pass |
| `test_find_best_solver_no_match_falls_back_to_least_busy` | pass |
| `test_find_best_solver_empty_solvers` | pass |
| `test_find_best_solver_multiple_tag_overlap` | pass |
| `test_create_ticket_db` | pass |
| `test_list_tickets_by_status` | pass |
| `test_list_tickets_with_tag_filter` | pass |
| `test_update_ticket_status` | pass |
| `test_update_ticket_not_found` | pass |
| `test_update_ticket_result` | pass |
| `test_update_ticket_review_publishes_event` | pass |

### test_telegram.py (12/12 passed) ok

| Test | Status |
|------|--------|
| `test_resolve_persona_found` | pass |
| `test_resolve_persona_not_found` | pass |
| `test_handle_start_sends_welcome` | pass |
| `test_handle_start_exception` | pass |
| `test_handle_message_no_persona` | pass |
| `test_handle_message_success` | pass |
| `test_handle_message_long_result` | pass |
| `test_handle_message_result_no_text_attr` | pass |
| `test_handle_message_group_chat` | pass |
| `test_handle_message_exception` | pass |
| `test_create_telegram_app_no_token` | pass |
| `test_create_telegram_app_with_token` | pass |

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

### test_utils.py (4/4 passed) ok

| Test | Status |
|------|--------|
| `test_set_main_loop_stores_loop` | pass |
| `test_run_async_fallback_creates_new_loop` | pass |
| `test_run_async_uses_main_loop_when_running` | pass |
| `test_run_async_fallback_when_loop_not_running` | pass |

### test_web_tools.py (12/12 passed) ok

| Test | Status |
|------|--------|
| `test_web_fetch_rejects_ftp_url` | pass |
| `test_web_fetch_strips_html` | pass |
| `test_web_fetch_respects_max_chars` | pass |
| `test_web_fetch_handles_timeout` | pass |
| `test_web_fetch_handles_encoding_error` | pass |
| `test_web_fetch_collapses_whitespace` | pass |
| `test_web_search_no_api_key` | pass |
| `test_web_search_with_results` | pass |
| `test_web_search_no_results` | pass |
| `test_web_search_api_error` | pass |
| `test_web_search_result_without_snippet` | pass |
| `test_web_search_limits_to_five_results` | pass |

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
