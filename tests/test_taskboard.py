from opencompany.company.taskboard import find_best_solver


def test_find_best_solver_matches_skills():
    solvers = [
        {"id": "backend-dev", "skills": ["python", "backend"], "workload": 3},
        {"id": "security-eng", "skills": ["security", "python"], "workload": 1},
    ]
    best = find_best_solver(tags=["security"], solvers=solvers)
    assert best["id"] == "security-eng"


def test_find_best_solver_prefers_lower_workload():
    solvers = [
        {"id": "dev-1", "skills": ["python"], "workload": 5},
        {"id": "dev-2", "skills": ["python"], "workload": 2},
    ]
    best = find_best_solver(tags=["python"], solvers=solvers)
    assert best["id"] == "dev-2"


def test_find_best_solver_no_match():
    solvers = [
        {"id": "dev-1", "skills": ["python"], "workload": 1},
    ]
    best = find_best_solver(tags=["rust"], solvers=solvers)
    assert best is None


def test_find_best_solver_multiple_tag_overlap():
    solvers = [
        {"id": "dev-1", "skills": ["python", "security"], "workload": 2},
        {"id": "dev-2", "skills": ["python"], "workload": 1},
    ]
    best = find_best_solver(tags=["python", "security"], solvers=solvers)
    assert best["id"] == "dev-1"  # more skill overlap wins despite higher workload
