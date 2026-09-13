from scripts.promote_thesis_v34_authority import MARKER, _v34_abstracts, merge_front_matter


def test_v34_abstracts_define_rule_weapon_and_learning_maneuver_ownership():
    chinese, english = _v34_abstracts(
        "任务技能包将感知、火力和机动能力组织为可调用、可追踪、可回退的任务内部结构，并以动作所有权隔离规则技能与学习技能；机动技能采用网络。",
        "the task skill package organizes sensing, fire, and maneuver capabilities into an invocable, traceable, and recoverable intra-task structure, with action ownership separating rule skills from learned skills; the maneuver skill employs a network.",
    )
    assert "基于规则的武器运用策略负责目标威胁排序" in chinese
    assert "强化学习策略仅负责目标点、编队与速度" in chinese
    assert "rule-based weapon-employment policy owns threat ranking" in english
    assert "reinforcement learning owns only maneuver decisions" in english


def test_merge_front_matter_is_idempotent_and_updates_header(monkeypatch):
    from scripts import promote_thesis_v34_authority as module

    document = module.writing_collaboration_service.codec.from_markdown(
        "---\nworkspace_version: 33\nstatus: draft\nstage_lock: old\n---\n\n# 第1章 绪论\n\n正文",
        namespace="test-v34",
    )
    merged, inserted = merge_front_matter(document, f"{MARKER}\n\n# 摘 要\n\n摘要")
    markdown = module.writing_collaboration_service.codec.to_markdown(merged)
    assert inserted is True
    assert "workspace_version: 34" in markdown
    assert markdown.index(MARKER) < markdown.index("# 第1章 绪论")
    second, inserted_again = merge_front_matter(merged, f"{MARKER}\n\n# 摘 要\n\n摘要")
    assert inserted_again is False
    assert module.writing_collaboration_service.codec.to_markdown(second).count(MARKER) == 1
