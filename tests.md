# Test Report

**Date:** 2026-03-11 13:46  


## Summary

| Metric | Count |
|--------|-------|
| Total  | 13 |
| Passed | 13 |
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

### test_engine_cov.py (2/2 passed) ok

| Test | Status |
|------|--------|
| `test_greedy_pickup_no_config` | pass |
| `test_route_ticket_no_config` | pass |

### test_personas_cov.py (1/1 passed) ok

| Test | Status |
|------|--------|
| `test_hire_loads_role_config` | pass |

### test_runner.py (1/1 passed) ok

| Test | Status |
|------|--------|
| `test_build_system_prompt_from_config` | pass |
