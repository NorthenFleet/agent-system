from services.memory_system_matrix import evaluate_matrix_invariants, summarize_matrix


def _case(case_id, agent_id, counts, *, healthy=True):
    return {
        "case_id": case_id,
        "agent_id": agent_id,
        "healthy": healthy,
        "failures": [],
        "summary": {
            "authority": "3021-unified-memory",
            "identity_bound": True,
            "counts": counts,
        },
    }


def test_matrix_accepts_shared_canonical_counts_and_isolated_agent_counts():
    cases = [
        _case("optimus", "optimus", {"profile": 1, "profile_facts": 10, "project_memories": 3, "agent_memories": 2}),
        _case("inspector", "inspector", {"profile": 1, "profile_facts": 10, "project_memories": 3, "agent_memories": 0}),
    ]
    invariants = {
        "authority_system": "3021-unified-memory",
        "identity_bound_for_all": True,
        "canonical_counts_equal": ["profile", "profile_facts", "project_memories"],
    }

    result = summarize_matrix(cases, invariants)

    assert result["healthy"] is True
    assert result["passed_cases"] == 2


def test_matrix_detects_cross_agent_canonical_scope_drift():
    cases = [
        _case("optimus", "optimus", {"profile": 1, "profile_facts": 10, "project_memories": 3}),
        _case("inspector", "inspector", {"profile": 1, "profile_facts": 9, "project_memories": 3}),
    ]
    failures = evaluate_matrix_invariants(
        cases,
        {"canonical_counts_equal": ["profile", "profile_facts", "project_memories"]},
    )

    assert failures == [
        {
            "check": "matrix.inspector.counts.profile_facts",
            "expected": 10,
            "actual": 9,
        }
    ]
