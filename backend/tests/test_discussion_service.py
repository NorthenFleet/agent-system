import json

from knowledge_manager import knowledge_manager
from project_manager import project_manager
from services.discussion_service import DiscussionService
from unified_data_manager import UnifiedDataManager


def test_discussion_lifecycle_writes_vault_and_promotes_to_research(tmp_path):
    vault = tmp_path / "vault"
    old_vault, old_index = knowledge_manager.vault_path, knowledge_manager.index_path
    old_project_file = project_manager.file_path
    projects_file = tmp_path / "projects.json"
    projects_file.write_text(json.dumps({"version": 1, "projects": [], "logs": []}), encoding="utf-8")
    knowledge_manager.configure(vault_path=str(vault), index_path=str(vault / "graph-index.json"))
    project_manager.file_path = str(projects_file)
    try:
        service = DiscussionService(UnifiedDataManager(str(tmp_path / "discussions.db")))
        created = service.create(
            {
                "title": "任务规划中的不确定性",
                "question": "如何把不确定性纳入任务规划？",
                "body": "先区分环境、观测和执行三类不确定性。",
                "topics": ["任务规划", "方法论"],
                "open_questions": ["应选择哪些量化指标？"],
            },
            owner_user_id="user-1",
        )
        assert created["status"] == "captured"
        assert (vault / created["vault_path"]).is_file()
        assert "任务规划中的不确定性" in created["content"]

        updated = service.update(
            created["id"],
            {"status": "research_candidate", "current_conclusion": "可先构建分类框架。"},
            owner_user_id="user-1",
        )
        assert updated["status"] == "research_candidate"
        assert len(updated["revisions"]) == 2
        assert "先区分环境" in updated["body"]
        assert updated["body"].count("## 原始问题") == 0

        promoted = service.promote(created["id"], {"project_name": "不确定性任务规划研究"}, owner_user_id="user-1")
        assert promoted["reused"] is False
        assert promoted["project"]["project_type"] == "research"
        assert promoted["discussion"]["promoted_project_id"] == promoted["project"]["id"]
        assert any(link["target_type"] == "project" for link in promoted["discussion"]["links"])
    finally:
        knowledge_manager.configure(vault_path=str(old_vault), index_path=str(old_index))
        project_manager.file_path = old_project_file


def test_conversation_is_persisted_then_archived_to_obsidian(tmp_path):
    vault = tmp_path / "vault"
    old_vault, old_index = knowledge_manager.vault_path, knowledge_manager.index_path
    knowledge_manager.configure(vault_path=str(vault), index_path=str(vault / "graph-index.json"))
    try:
        service = DiscussionService(UnifiedDataManager(str(tmp_path / "discussions.db")))
        discussion = service.create_conversation(owner_user_id="user-1")
        assert discussion["vault_path"] == ""
        reply, generated = service.parse_agent_reply(json.dumps({
            "reply": "可以先定义从对话到研究的转化门槛。",
            "title": "对话转研究的门槛",
            "topics": ["知识管理", "智能体"],
            "question": "何时应将讨论转为项目？",
            "summary": "正在定义转化标准。",
            "current_conclusion": "至少需要问题、假设和下一步。",
            "open_questions": ["门槛如何量化？"],
            "hypothesis": "结构化摘要可提升转化质量。",
            "status": "research_candidate",
        }, ensure_ascii=False))
        updated = service.add_turn(discussion["id"], "我想讨论何时把灵感转为研究项目。", reply, generated, owner_user_id="user-1")
        assert updated["title"] == "对话转研究的门槛"
        assert len(updated["messages"]) == 2
        archived = service.archive(discussion["id"], owner_user_id="user-1")
        assert archived["content_available"] is True
        assert "## 对话记录" in archived["content"]
        assert "研究助手" in archived["content"]
    finally:
        knowledge_manager.configure(vault_path=str(old_vault), index_path=str(old_index))
