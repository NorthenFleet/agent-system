from services.business_flow_service import BusinessFlowRegistry
from services.plan_quality_service import PlanQualityService


def _software_plan():
    return {
        "schema_version": "2.0",
        "summary": "交付一个可验证的 API",
        "risk_level": "low",
        "steps": [
            {
                "order_index": 1,
                "title": "设计接口",
                "description": "定义边界与验收口径",
                "task_type": "architecture",
                "agent_id": "leonardo",
                "depends_on": [],
            },
            {
                "order_index": 2,
                "title": "实现接口",
                "description": "在后端实现并保留回滚路径",
                "task_type": "backend",
                "agent_id": "raphael",
                "depends_on": [1],
                "resources": ["backend/api.py"],
            },
            {
                "order_index": 3,
                "title": "验证接口",
                "description": "运行针对性测试",
                "task_type": "testing",
                "agent_id": "michelangelo",
                "depends_on": [2],
            },
        ],
    }


def test_catalog_exposes_versioned_flows_contracts_risks_and_lifecycles():
    catalog = BusinessFlowRegistry().catalog()

    assert catalog["schema_version"] == "1.0"
    assert {flow["flow_key"] for flow in catalog["flows"]} >= {
        "general",
        "software",
        "document",
        "finance",
        "research",
        "operations",
    }
    assert set(catalog["risk_levels"]) == {"L0", "L1", "L2", "L3"}
    assert catalog["risk_levels"]["L3"]["step_approval"] is True
    assert "artifact" in catalog["contracts"]
    assert "evidence" in catalog["contracts"]
    assert "awaiting_approval" in catalog["state_machines"]["mission"]


def test_explicit_business_flow_is_independent_from_legacy_project_type():
    resolved = BusinessFlowRegistry().resolve(
        {
            "mission_type": "software",
            "context": {
                "mission_type": "software",
                "user_context": {"business_flow_key": "research"},
            },
        }
    )

    assert resolved["flow_key"] == "research"


def test_software_flow_enriches_step_execution_contracts():
    registry = BusinessFlowRegistry()
    enriched = registry.enrich_plan(
        _software_plan(),
        mission={"id": "mission-test", "mission_type": "software", "plan_version": 2},
    )

    assert enriched["flow_spec"]["flow_key"] == "software"
    assert enriched["flow_spec"]["version"] == "1.0.0"
    assert enriched["flow_validation"]["status"] == "pass"
    implementation = enriched["steps"][1]
    assert implementation["phase"] == "implementation"
    assert implementation["objective"]
    assert implementation["output_contract"]["artifact_types"]
    assert implementation["risk_class"] == "L1"
    assert implementation["side_effect"] is True
    assert implementation["idempotency_key"] == "mission-test:plan:3:step:2"
    assert implementation["timeout_seconds"] >= 30
    assert implementation["max_attempts"] == 2
    assert implementation["compensation"]["instructions"]


def test_generated_idempotency_key_rebinds_to_real_mission_version():
    registry = BusinessFlowRegistry()
    provisional = registry.enrich_plan(_software_plan())
    rebound = registry.enrich_plan(
        provisional,
        mission={"id": "mission-real", "mission_type": "software", "plan_version": 4},
    )

    assert provisional["steps"][0]["idempotency_key"] == "mission:plan:1:step:1"
    assert rebound["steps"][0]["idempotency_key"] == "mission-real:plan:5:step:1"


def test_l3_action_is_explicit_and_requires_approval():
    registry = BusinessFlowRegistry()
    plan = {
        "summary": "执行付款",
        "steps": [
            {
                "order_index": 1,
                "title": "向供应商付款",
                "description": "核对后执行银行转账",
                "task_type": "finance",
                "agent_id": "soundwave",
                "depends_on": [],
                "deliverables": ["付款回执"],
                "acceptance_criteria": ["金额、对象与审批一致"],
                "evidence_required": ["finance_evidence"],
                "rollback_plan": "未完成前停止；已发起则转人工追踪",
                "risk_class": "L0",
            }
        ],
    }

    enriched = registry.enrich_plan(
        plan,
        mission={"id": "mission-pay", "mission_type": "finance", "plan_version": 0},
    )
    step = enriched["steps"][0]

    assert step["risk_class"] == "L3"
    assert step["approval_required"] is True
    assert step["max_attempts"] == 1
    assert enriched["risk_assessment"]["highest_risk"] == "L3"
    assert enriched["risk_assessment"]["step_approvals"] == [1]


def test_domain_coverage_and_parallel_resource_conflict_are_visible():
    registry = BusinessFlowRegistry()
    plan = {
        "business_type": "software",
        "steps": [
            {
                "order_index": 1,
                "title": "修改 A",
                "task_type": "backend",
                "agent_id": "raphael",
                "depends_on": [],
                "resources": ["backend/main.py"],
                "deliverables": ["A"],
                "acceptance_criteria": ["A 通过"],
                "evidence_required": ["test_output"],
                "rollback_plan": "停止合并",
            },
            {
                "order_index": 2,
                "title": "修改 B",
                "task_type": "backend",
                "agent_id": "raphael",
                "depends_on": [],
                "resources": ["backend/main.py"],
                "deliverables": ["B"],
                "acceptance_criteria": ["B 通过"],
                "evidence_required": ["test_output"],
                "rollback_plan": "停止合并",
            },
        ],
    }

    enriched = registry.enrich_plan(plan)
    warnings = enriched["flow_validation"]["warnings"]

    assert any("必要环节" in warning for warning in warnings)
    assert any("并行修改" in warning for warning in warnings)


def test_plan_quality_embeds_flow_risk_and_runtime_policy():
    enriched = PlanQualityService().enrich_plan(
        _software_plan(),
        mission={"id": "mission-quality", "mission_type": "software", "plan_version": 0},
    )

    assert enriched["plan_quality"]["flow_key"] == "software"
    assert enriched["plan_quality"]["risk_assessment"]["highest_risk"] == "L1"
    assert enriched["execution_policy"]["runtime"] == "command-center"
    assert enriched["execution_policy"]["idempotency_required_for_side_effects"] is True
    assert "business-flow" in enriched["plan_quality"]["checked_rules"]
