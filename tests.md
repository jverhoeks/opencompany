# Test Report

**Date:** 2026-11-07 11:30  


## Summary

| Metric | Count |
|--------|-------|
| Total  | 511 |
| Passed | 240 |
| Failed | 9 |
| Errors | 260 |
| Skipped | 2 |
| **Coverage** | **48%** |

## Test Results

### test_budget_cov.py (0/20 passed) FAIL

| Test | Status |
|------|--------|
| `test_check_budget_nonexistent` | ERROR |
| `test_check_budget_unlimited` | ERROR |
| `test_check_budget_auto_reset_on_new_day` | ERROR |
| `test_check_budget_no_reset_at` | ERROR |
| `test_check_budget_exhausted` | ERROR |
| `test_check_budget_partial_remaining` | ERROR |
| `test_check_budget_unblocks_on_daily_reset` | ERROR |
| `test_check_budget_unblocks_unlimited_budget` | ERROR |
| `test_check_budget_keeps_blocked_when_still_over` | ERROR |
| `test_consume_tokens_zero_total` | ERROR |
| `test_consume_tokens_nonexistent` | ERROR |
| `test_consume_tokens_accumulates` | ERROR |
| `test_consume_tokens_sets_budget_reset_at` | ERROR |
| `test_reset_budget_found` | ERROR |
| `test_reset_budget_not_found` | ERROR |
| `test_reset_all_budgets` | ERROR |
| `test_get_budget_status_found` | ERROR |
| `test_get_budget_status_not_found` | ERROR |
| `test_get_budget_status_unlimited` | ERROR |
| `test_get_all_budget_statuses` | ERROR |

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

### test_config.py (7/9 passed) FAIL

| Test | Status |
|------|--------|
| `test_load_company_config` | pass |
| `test_get_role` | pass |
| `test_get_role_missing` | pass |
| `test_get_org_routing` | pass |
| `test_load_config_missing_file` | pass |
| `test_config_caching` | pass |
| `test_load_real_company_yaml` | pass |
| `test_add_role` | FAIL |
| `test_add_role_duplicate` | FAIL |

### test_config_roles.py (0/4 passed) FAIL

| Test | Status |
|------|--------|
| `test_update_role` | FAIL |
| `test_update_role_not_found` | FAIL |
| `test_delete_role` | FAIL |
| `test_delete_role_not_found` | FAIL |

### test_dashboard.py (0/3 passed) FAIL

| Test | Status |
|------|--------|
| `test_overview_empty` | ERROR |
| `test_overview_with_personas_and_tickets` | ERROR |
| `test_overview_work_log` | ERROR |

### test_dashboard_cov.py (1/14 passed) FAIL

| Test | Status |
|------|--------|
| `test_soul_update_endpoint` | pass |
| `test_serve_dashboard_returns_html` | ERROR |
| `test_workspace_file_not_found` | ERROR |
| `test_workspace_file_path_traversal` | ERROR |
| `test_workspace_serves_existing_file` | ERROR |
| `test_overseer_list_messages` | ERROR |
| `test_overseer_reply_message_not_found` | ERROR |
| `test_overseer_reply_success` | ERROR |
| `test_overseer_reply_no_persona` | ERROR |
| `test_overview_persona_fields` | ERROR |
| `test_overview_includes_fired_personas` | ERROR |
| `test_overview_includes_reports_to` | ERROR |
| `test_patch_persona_config_name_and_role` | ERROR |
| `test_dashboard_stream_returns_sse` | skip |

### test_dashboard_e2e.py (0/31 passed) FAIL

| Test | Status |
|------|--------|
| `test_dashboard_loads` | ERROR |
| `test_default_tab_is_kanban` | ERROR |
| `test_tab_switching` | ERROR |
| `test_sidebar_shows_personas` | ERROR |
| `test_kanban_columns_present` | ERROR |
| `test_kanban_tickets_in_correct_columns` | ERROR |
| `test_kanban_ticket_card_content` | ERROR |
| `test_kanban_filter_by_persona` | ERROR |
| `test_kanban_click_ticket_shows_detail` | ERROR |
| `test_organigram_renders_svg` | ERROR |
| `test_organigram_hierarchy` | ERROR |
| `test_organigram_node_content` | ERROR |
| `test_organigram_zoom` | ERROR |
| `test_organigram_zoom_to_fit` | ERROR |
| `test_organigram_click_node` | ERROR |
| `test_office_renders_rooms` | ERROR |
| `test_office_ceo_corner_office` | ERROR |
| `test_office_hr_near_ceo` | ERROR |
| `test_office_leads_in_mid_row` | ERROR |
| `test_office_solvers_in_open_floor` | ERROR |
| `test_office_shows_ticket_counts` | ERROR |
| `test_office_fired_persona_dimmed` | ERROR |
| `test_editor_subtabs` | ERROR |
| `test_editor_persona_list` | ERROR |
| `test_editor_persona_form` | ERROR |
| `test_editor_persona_save` | ERROR |
| `test_editor_roles_list` | ERROR |
| `test_editor_role_form` | ERROR |
| `test_editor_soul_markdown` | ERROR |
| `test_editor_soul_version_history` | ERROR |
| `test_editor_fired_persona_not_editable` | ERROR |

### test_e2e.py (3/54 passed) FAIL

| Test | Status |
|------|--------|
| `test_fuzzy_tag_matching_exact` | pass |
| `test_fuzzy_tag_matching_substring` | pass |
| `test_fuzzy_tag_matching_reverse_substring` | pass |
| `test_health` | ERROR |
| `test_list_personas_empty` | ERROR |
| `test_list_personas_seeded` | ERROR |
| `test_get_persona` | ERROR |
| `test_get_persona_not_found` | ERROR |
| `test_create_ticket` | ERROR |
| `test_create_ticket_defaults` | ERROR |
| `test_list_tickets_by_status` | ERROR |
| `test_list_tickets_empty_status` | ERROR |
| `test_create_ticket_with_context` | ERROR |
| `test_chat_persona_not_found` | ERROR |
| `test_chat_with_persona` | ERROR |
| `test_chat_returns_agent_response` | ERROR |
| `test_ticket_lifecycle` | ERROR |
| `test_multiple_tickets_ordering` | ERROR |
| `test_engine_auto_assign` | ERROR |
| `test_engine_no_solver_available` | ERROR |
| `test_seed_company` | ERROR |
| `test_seed_company_skips_if_personas_exist` | ERROR |
| `test_full_org_is_seeded` | ERROR |
| `test_org_roles` | ERROR |
| `test_backend_ticket_auto_assigned_to_jamie` | ERROR |
| `test_frontend_ticket_auto_assigned_to_sam` | ERROR |
| `test_marketing_ticket_auto_assigned` | ERROR |
| `test_sales_ticket_auto_assigned` | ERROR |
| `test_ceo_ticket_routes_to_pm` | ERROR |
| `test_tech_lead_reviews_backlog_via_chat` | ERROR |
| `test_full_sprint_lifecycle` | ERROR |
| `test_workload_balancing_across_solvers` | ERROR |
| `test_seed_real_company_yaml` | ERROR |
| `test_engine_escalates_to_ceo` | ERROR |
| `test_sweep_routes_orphaned_tickets` | ERROR |
| `test_api_rejects_without_key` | ERROR |
| `test_api_rejects_wrong_key` | ERROR |
| `test_api_accepts_correct_key` | ERROR |
| `test_dashboard_stream_requires_auth` | ERROR |
| `test_dashboard_overview_requires_auth` | ERROR |
| `test_overseer_messages_requires_auth` | ERROR |
| `test_overseer_reply_requires_auth` | ERROR |
| `test_budget_check_unlimited` | ERROR |
| `test_budget_check_and_consume` | ERROR |
| `test_budget_reset` | ERROR |
| `test_budget_status` | ERROR |
| `test_budget_api_list` | ERROR |
| `test_budget_api_reset` | ERROR |
| `test_seed_populates_model_id` | ERROR |
| `test_engine_budget_blocks_over_budget_persona` | ERROR |
| `test_heartbeat_triggers_idle_personas` | ERROR |
| `test_heartbeat_skips_when_no_work` | ERROR |
| `test_heartbeat_skips_busy_personas` | ERROR |
| `test_heartbeat_skips_over_budget` | ERROR |

### test_engine_cov.py (10/41 passed) FAIL

| Test | Status |
|------|--------|
| `test_handle_event_ignores_unknown_type` | pass |
| `test_handle_event_catches_errors` | pass |
| `test_build_task_prompt` | pass |
| `test_get_routing_target_no_creator` | pass |
| `test_get_routing_target_by_id` | pass |
| `test_get_routing_target_by_role_type` | pass |
| `test_get_routing_target_lead_default` | pass |
| `test_find_lead_for_tags_exact_match` | pass |
| `test_find_lead_for_tags_no_match` | pass |
| `test_start_event_listener` | pass |
| `test_handle_event_dispatches_ticket_created` | ERROR |
| `test_handle_event_dispatches_ticket_review` | ERROR |
| `test_set_persona_state` | ERROR |
| `test_set_persona_state_missing_persona` | ERROR |
| `test_set_ticket_in_progress` | ERROR |
| `test_set_ticket_in_progress_skips_done_ticket` | ERROR |
| `test_add_ticket_tokens` | ERROR |
| `test_add_ticket_tokens_missing_ticket` | ERROR |
| `test_trigger_review_falls_back_to_manager` | ERROR |
| `test_trigger_review_ticket_not_found` | ERROR |
| `test_trigger_review_excludes_worker_from_fallback` | ERROR |
| `test_trigger_review_prefers_non_worker_creator` | ERROR |
| `test_release_ticket_for_retry_flips_open` | ERROR |
| `test_release_ticket_noop_when_already_started` | ERROR |
| `test_try_claim_ticket_wins_first` | ERROR |
| `test_find_hr_persona_id_by_role` | ERROR |
| `test_find_hr_persona_id_none_when_missing` | ERROR |
| `test_spawn_persona_task_full_run` | ERROR |
| `test_spawn_persona_task_error_sets_blocked` | ERROR |
| `test_on_persona_idle_claims_ticket` | ERROR |
| `test_on_persona_idle_no_tickets` | ERROR |
| `test_on_persona_idle_inactive_persona` | ERROR |
| `test_hr_pickup_finds_hr_tagged_tickets` | ERROR |
| `test_hr_pickup_ignores_non_hr_tickets` | ERROR |
| `test_escalate_to_ceo` | ERROR |
| `test_escalate_to_ceo_inactive` | ERROR |
| `test_sweep_no_orphans` | ERROR |
| `test_sweep_handles_route_error` | ERROR |
| `test_hr_tagged_ticket_routes_to_hr` | ERROR |
| `test_route_ticket_skips_assigned` | ERROR |
| `test_route_ticket_no_config` | ERROR |

### test_main.py (13/14 passed) FAIL

| Test | Status |
|------|--------|
| `test_app_exists` | pass |
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
| `test_app_has_routers` | FAIL |

### test_memory.py (3/9 passed) FAIL

| Test | Status |
|------|--------|
| `test_remember_tool` | pass |
| `test_recall_tool` | pass |
| `test_recall_tool_empty` | pass |
| `test_store_and_recall` | ERROR |
| `test_recall_filters` | ERROR |
| `test_build_memory_context` | ERROR |
| `test_build_memory_context_empty` | ERROR |
| `test_compaction` | ERROR |
| `test_compaction_below_threshold` | ERROR |

### test_messaging.py (0/4 passed) FAIL

| Test | Status |
|------|--------|
| `test_deliver_message_success` | ERROR |
| `test_deliver_message_sender_not_found` | ERROR |
| `test_deliver_message_recipient_not_found` | ERROR |
| `test_deliver_message_recipient_not_active` | ERROR |

### test_messaging2.py (4/4 passed) ok

| Test | Status |
|------|--------|
| `test_deliver_message_sender_not_found` | pass |
| `test_deliver_message_recipient_not_found` | pass |
| `test_deliver_message_recipient_inactive` | pass |
| `test_deliver_message_success` | pass |

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

### test_overseer.py (0/6 passed) FAIL

| Test | Status |
|------|--------|
| `test_store_message` | ERROR |
| `test_reply_to_message` | ERROR |
| `test_reply_to_nonexistent_message` | ERROR |
| `test_list_messages_all` | ERROR |
| `test_list_messages_pending_only` | ERROR |
| `test_list_messages_empty` | ERROR |

### test_personality.py (4/4 passed) ok

| Test | Status |
|------|--------|
| `test_personality_injected_in_prompt` | pass |
| `test_personality_falls_back_to_role` | pass |
| `test_no_personality_no_crash` | pass |
| `test_persona_personality_overrides_role` | pass |

### test_personas.py (0/7 passed) FAIL

| Test | Status |
|------|--------|
| `test_hire_persona` | ERROR |
| `test_hire_duplicate_persona` | ERROR |
| `test_fire_persona` | ERROR |
| `test_fire_nonexistent_persona` | ERROR |
| `test_list_personas` | ERROR |
| `test_list_personas_excludes_fired` | ERROR |
| `test_list_personas_filter_by_reports_to` | ERROR |

### test_personas_cov.py (7/15 passed) FAIL

| Test | Status |
|------|--------|
| `test_append_to_company_yaml` | pass |
| `test_append_to_company_yaml_no_file` | pass |
| `test_append_to_company_yaml_already_exists` | pass |
| `test_append_to_company_yaml_exception` | pass |
| `test_hire_persona_sync_wrapper` | pass |
| `test_fire_persona_sync_wrapper` | pass |
| `test_list_personas_sync_wrapper` | pass |
| `test_hire_invalid_persona_id` | ERROR |
| `test_hire_with_all_optional_fields` | ERROR |
| `test_hire_loads_role_config` | ERROR |
| `test_hire_post_sweep` | ERROR |
| `test_hire_post_sweep_failure` | ERROR |
| `test_fire_persona_reassigns_orphaned_tickets` | ERROR |
| `test_list_personas_includes_workload_and_budget` | ERROR |
| `test_list_personas_zero_workload_for_idle_persona` | ERROR |

### test_policy.py (7/21 passed) FAIL

| Test | Status |
|------|--------|
| `test_write_policy_tool` | pass |
| `test_approve_policy_tool` | pass |
| `test_approve_policy_tool_error` | pass |
| `test_list_policies_tool` | pass |
| `test_list_policies_tool_empty` | pass |
| `test_read_policy_tool` | pass |
| `test_read_policy_tool_not_found` | pass |
| `test_create_policy` | ERROR |
| `test_approve_policy` | ERROR |
| `test_approve_policy_requires_manager_or_lead` | ERROR |
| `test_approve_non_draft_fails` | ERROR |
| `test_reject_policy` | ERROR |
| `test_reject_policy_requires_manager_or_lead` | ERROR |
| `test_list_policies` | ERROR |
| `test_get_policy_not_found` | ERROR |
| `test_build_policy_context_wildcard` | ERROR |
| `test_build_policy_context_role_match` | ERROR |
| `test_build_policy_context_persona_id_match` | ERROR |
| `test_build_policy_context_tag_skill_match` | ERROR |
| `test_build_policy_context_draft_excluded` | ERROR |
| `test_build_policy_context_empty` | ERROR |

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

### test_scenarios.py (2/5 passed) FAIL

| Test | Status |
|------|--------|
| `test_scenario_personality_injection` | pass |
| `test_scenario_trust_boundaries` | pass |
| `test_scenario_landing_page` | ERROR |
| `test_scenario_stale_escalation` | ERROR |
| `test_scenario_sprint_with_memory` | ERROR |

### test_scheduler_cov.py (7/15 passed) FAIL

| Test | Status |
|------|--------|
| `test_sweep_job_handles_exception` | pass |
| `test_ceo_kickoff_handles_exception` | pass |
| `test_unblock_personas_job_handles_exception` | pass |
| `test_start_scheduler_adds_sweep_job` | pass |
| `test_start_scheduler_with_ceo_kickoff` | pass |
| `test_start_scheduler_with_heartbeat` | pass |
| `test_start_scheduler_with_all_jobs` | pass |
| `test_sweep_job_calls_sweep` | ERROR |
| `test_ceo_kickoff_triggers_ceo` | ERROR |
| `test_ceo_kickoff_skips_inactive_ceo` | ERROR |
| `test_ceo_kickoff_skips_busy_ceo` | ERROR |
| `test_ceo_kickoff_skips_over_budget` | ERROR |
| `test_ceo_kickoff_no_ceo` | ERROR |
| `test_unblock_personas_job_recovers_blocked` | ERROR |
| `test_unblock_personas_job_leaves_still_over_budget` | ERROR |

### test_sprint1.py (0/23 passed) FAIL

| Test | Status |
|------|--------|
| `test_ticket_has_budget_tokens_field` | ERROR |
| `test_check_task_budget_requeues_exhausted` | ERROR |
| `test_check_task_budget_allows_with_remaining` | ERROR |
| `test_check_task_budget_unlimited_when_zero` | ERROR |
| `test_check_task_budget_parks_after_loop_threshold` | ERROR |
| `test_claim_next_claims_best_match` | ERROR |
| `test_claim_next_returns_none_when_no_tickets` | ERROR |
| `test_claim_next_returns_none_for_inactive_persona` | ERROR |
| `test_claim_next_skips_assigned_tickets` | ERROR |
| `test_claim_next_backs_off_for_lighter_peer` | ERROR |
| `test_claim_next_proceeds_when_no_lighter_peer` | ERROR |
| `test_claim_next_ignores_peer_with_lower_score` | ERROR |
| `test_claim_next_fairness_respects_margin` | ERROR |
| `test_capacity_ratio_no_solvers` | ERROR |
| `test_capacity_ratio_balanced` | ERROR |
| `test_capacity_ratio_counts_assigned_as_pending` | ERROR |
| `test_hire_rejected_when_capacity_sufficient` | ERROR |
| `test_hire_allowed_when_understaffed` | ERROR |
| `test_hire_rejected_at_team_cap` | ERROR |
| `test_expires_stale_tickets` | ERROR |
| `test_ignores_recent_tickets` | ERROR |
| `test_ignores_open_tickets` | ERROR |
| `test_expires_stale_assigned_tickets` | ERROR |

### test_sprint10.py (3/6 passed) FAIL

| Test | Status |
|------|--------|
| `test_entrypoint_script_exists` | pass |
| `test_entrypoint_has_otel_toggle` | pass |
| `test_dockerfile_copies_soul_and_sops` | pass |
| `test_get_soul` | ERROR |
| `test_soul_history` | ERROR |
| `test_soul_rollback_api` | ERROR |

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

### test_sprint2_events.py (1/5 passed) FAIL

| Test | Status |
|------|--------|
| `test_handle_event_handles_persona_blocked` | pass |
| `test_handle_event_dispatches_persona_idle` | ERROR |
| `test_spawn_publishes_idle_on_success` | ERROR |
| `test_spawn_publishes_blocked_on_error` | ERROR |
| `test_spawn_publishes_blocked_on_budget_exhausted` | ERROR |

### test_sprint3_metrics.py (0/2 passed) FAIL

| Test | Status |
|------|--------|
| `test_metrics_returns_per_persona_data` | ERROR |
| `test_metrics_empty_when_no_work` | ERROR |

### test_sprint4_concurrency.py (2/3 passed) FAIL

| Test | Status |
|------|--------|
| `test_get_persona_lock_creates_semaphore` | pass |
| `test_get_persona_lock_custom_concurrency` | pass |
| `test_concurrent_tasks_blocked_by_semaphore` | ERROR |

### test_sprint5_persona_config.py (0/9 passed) FAIL

| Test | Status |
|------|--------|
| `test_create_persona_config` | ERROR |
| `test_company_snapshot_model` | ERROR |
| `test_boot_seeds_from_yaml` | ERROR |
| `test_boot_skips_if_already_seeded` | ERROR |
| `test_snapshot_captures_state` | ERROR |
| `test_snapshot_skips_empty_config` | ERROR |
| `test_list_persona_configs` | ERROR |
| `test_patch_persona_config` | ERROR |
| `test_patch_nonexistent_config` | ERROR |

### test_sprint6_soul.py (9/13 passed) FAIL

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
| `test_soul_injected_into_prompt` | pass |
| `test_propose_valid_update` | ERROR |
| `test_propose_invalid_rejected` | ERROR |
| `test_rollback_to_version` | ERROR |
| `test_rollback_nonexistent_version` | ERROR |

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

### test_sprint8_strands.py (6/7 passed) FAIL

| Test | Status |
|------|--------|
| `test_tool_registered` | pass |
| `test_requires_solver_tier` | pass |
| `test_external_denied` | pass |
| `test_solver_allowed` | pass |
| `test_on_tool_use_records_calls` | pass |
| `test_summary` | pass |
| `test_on_invocation_complete_consumes_budget` | ERROR |

### test_sprint9.py (7/9 passed) FAIL

| Test | Status |
|------|--------|
| `test_ignores_non_hire_tools` | pass |
| `test_sop_files_exist` | pass |
| `test_load_sop_for_review_tag` | pass |
| `test_load_sop_for_hr_tag` | pass |
| `test_load_sop_for_unknown_tag` | pass |
| `test_load_sop_deduplicates` | pass |
| `test_load_sop_multiple_tags` | pass |
| `test_allows_hire_when_understaffed` | ERROR |
| `test_blocks_hire_when_sufficient` | ERROR |

### test_taskboard.py (12/19 passed) FAIL

| Test | Status |
|------|--------|
| `test_find_best_solver_matches_skills` | pass |
| `test_find_best_solver_prefers_lower_workload` | pass |
| `test_find_best_solver_no_match_returns_none` | pass |
| `test_find_best_solver_empty_solvers` | pass |
| `test_find_best_solver_multiple_tag_overlap` | pass |
| `test_fuzzy_score_exact_match_full_credit` | pass |
| `test_fuzzy_score_length_weighted_partial` | pass |
| `test_fuzzy_score_specialist_outscores_generalist` | pass |
| `test_fuzzy_score_best_partial_not_summed` | pass |
| `test_fuzzy_score_ticket_tag_inside_solver_tag` | pass |
| `test_fuzzy_score_no_overlap` | pass |
| `test_fuzzy_score_handles_empty_tags` | pass |
| `test_create_ticket_db` | ERROR |
| `test_list_tickets_by_status` | ERROR |
| `test_list_tickets_with_tag_filter` | ERROR |
| `test_update_ticket_status` | ERROR |
| `test_update_ticket_not_found` | ERROR |
| `test_update_ticket_result` | ERROR |
| `test_update_ticket_review_publishes_event` | ERROR |

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

### test_tools.py (20/22 passed) FAIL

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
| `test_create_ticket_tool_calls_sync` | pass |
| `test_list_tickets_tool_formats_output` | pass |
| `test_list_tickets_tool_empty` | pass |
| `test_update_ticket_tool` | pass |
| `test_hire_persona_tool` | pass |
| `test_hire_persona_tool_blocked_by_guardrail` | pass |
| `test_fire_persona_tool` | pass |
| `test_list_team_tool_with_data` | pass |
| `test_list_team_tool_unlimited_budget` | pass |
| `test_list_team_tool_empty` | pass |
| `test_web_fetch_bad_url` | pass |
| `test_web_fetch_strips_html` | pass |
| `test_grep_code_finds_pattern` | FAIL |
| `test_grep_code_no_matches` | FAIL |

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

## Coverage

| Module | Stmts | Miss | Cover |
|--------|-------|------|-------|
| `opencompany/__init__.py` | 0 | 0 | 100% |
| `opencompany/agents\__init__.py` | 0 | 0 | 100% |
| `opencompany/agents\hooks.py` | 32 | 8 | 75% |
| `opencompany/agents\prompts.py` | 101 | 10 | 90% |
| `opencompany/agents\runner.py` | 140 | 22 | 84% |
| `opencompany/agents\session.py` | 45 | 2 | 95% |
| `opencompany/agents\tools\__init__.py` | 11 | 0 | 100% |
| `opencompany/agents\tools\code.py` | 140 | 48 | 65% |
| `opencompany/agents\tools\company.py` | 49 | 0 | 100% |
| `opencompany/agents\tools\memory.py` | 21 | 0 | 100% |
| `opencompany/agents\tools\messaging.py` | 9 | 0 | 100% |
| `opencompany/agents\tools\overseer.py` | 10 | 0 | 100% |
| `opencompany/agents\tools\policy.py` | 40 | 0 | 100% |
| `opencompany/agents\tools\soul.py` | 16 | 11 | 31%! |
| `opencompany/agents\tools\subagent.py` | 30 | 22 | 26%! |
| `opencompany/agents\tools\tickets.py` | 26 | 0 | 100% |
| `opencompany/agents\tools\web.py` | 79 | 10 | 87% |
| `opencompany/company\__init__.py` | 0 | 0 | 100% |
| `opencompany/company\budget.py` | 77 | 64 | 16%! |
| `opencompany/company\config.py` | 154 | 89 | 42%! |
| `opencompany/company\engine.py` | 359 | 259 | 27%! |
| `opencompany/company\memory.py` | 57 | 48 | 15%! |
| `opencompany/company\messaging.py` | 19 | 0 | 100% |
| `opencompany/company\overseer.py` | 32 | 23 | 28%! |
| `opencompany/company\personas.py` | 143 | 97 | 32%! |
| `opencompany/company\policy.py` | 84 | 69 | 17%! |
| `opencompany/company\scheduler.py` | 162 | 103 | 36%! |
| `opencompany/company\seed.py` | 80 | 69 | 13%! |
| `opencompany/company\soul.py` | 63 | 25 | 60% |
| `opencompany/company\taskboard.py` | 141 | 86 | 39%! |
| `opencompany/company\trust.py` | 27 | 0 | 100% |
| `opencompany/events\__init__.py` | 0 | 0 | 100% |
| `opencompany/events\bus.py` | 121 | 24 | 80% |
| `opencompany/gateway\__init__.py` | 0 | 0 | 100% |
| `opencompany/gateway\api.py` | 305 | 175 | 42%! |
| `opencompany/gateway\channels\__init__.py` | 0 | 0 | 100% |
| `opencompany/gateway\channels\telegram.py` | 60 | 7 | 88% |
| `opencompany/gateway\dashboard.py` | 80 | 49 | 38%! |
| `opencompany/main.py` | 171 | 50 | 70% |
| `opencompany/models\__init__.py` | 5 | 0 | 100% |
| `opencompany/models\base.py` | 3 | 0 | 100% |
| `opencompany/models\db.py` | 110 | 0 | 100% |
| `opencompany/models\engine.py` | 15 | 2 | 86% |
| `opencompany/utils.py` | 12 | 0 | 100% |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\__init__.py` | 0 | 0 | 100% |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\conftest.py` | 198 | 151 | 23%! |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_budget_cov.py` | 173 | 145 | 16%! |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_bus.py` | 22 | 0 | 100% |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_bus_cov.py` | 118 | 13 | 88% |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_company_tools_cov.py` | 53 | 0 | 100% |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_config.py` | 76 | 9 | 88% |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_config_roles.py` | 23 | 4 | 82% |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_dashboard.py` | 54 | 42 | 22%! |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_dashboard_cov.py` | 176 | 134 | 23%! |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_dashboard_e2e.py` | 221 | 188 | 14%! |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_e2e.py` | 661 | 565 | 14%! |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_engine_cov.py` | 449 | 351 | 21%! |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_main.py` | 152 | 1 | 99% |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_memory.py` | 110 | 80 | 27%! |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_messaging.py` | 42 | 33 | 21%! |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_messaging2.py` | 62 | 2 | 96% |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_messaging_tools.py` | 26 | 0 | 100% |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_models.py` | 19 | 0 | 100% |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_overseer.py` | 59 | 48 | 18%! |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_personality.py` | 39 | 0 | 100% |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_personas.py` | 69 | 55 | 20%! |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_personas_cov.py` | 137 | 82 | 40%! |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_policy.py` | 200 | 134 | 33%! |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_runner.py` | 35 | 0 | 100% |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_runner_cov.py` | 178 | 0 | 100% |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_scenarios.py` | 153 | 104 | 32%! |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_scheduler_cov.py` | 142 | 83 | 41%! |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_sprint1.py` | 286 | 250 | 12%! |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_sprint10.py` | 86 | 61 | 29%! |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_sprint11_session.py` | 65 | 0 | 100% |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_sprint2_events.py` | 72 | 59 | 18%! |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_sprint3_metrics.py` | 57 | 50 | 12%! |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_sprint4_concurrency.py` | 48 | 23 | 52% |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_sprint5_persona_config.py` | 149 | 130 | 12%! |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_sprint6_soul.py` | 106 | 34 | 67% |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_sprint7.py` | 38 | 0 | 100% |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_sprint8_strands.py` | 44 | 10 | 77% |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_sprint9.py` | 60 | 21 | 65% |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_taskboard.py` | 152 | 92 | 39%! |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_telegram.py` | 115 | 0 | 100% |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_tools.py` | 162 | 0 | 100% |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_trust.py` | 61 | 0 | 100% |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_utils.py` | 53 | 1 | 98% |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_web_tools.py` | 104 | 0 | 100% |
| `D:\Stepan\Urfu\Projects\Lab2Tests\opencompany\opencompany\tests\test_workspaces.py` | 52 | 0 | 100% |
| **TOTAL** | **8386** | **4327** | **48%** |
