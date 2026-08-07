# SacredJourney 数字文旅项目

> **项目 ID**: proj-778a846996
> **3021 看板**: http://localhost:3021/projects/proj-778a846996
> **创建日期**: 2026-08-01
> **目标发布**: 2027-02-28
> **状态**: Planning

---

## 📐 项目架构

```
SacredJourney 统一项目
├── /Game/Sophia/          ← 圣索菲亚大教堂（独立场景）
├── /Game/Yonghe/          ← 雍和宫（独立场景）
├── /Game/Common/          ← 共享系统（UI、加载器、人物管理）
└── /Source/SacredJourney/ ← C++ 模块
```

**核心原则**: 每个建筑完全独立，共享程序框架。一个游戏入口，多个独立博物馆。

---

## 👥 人物系统（8 角色）

| 类别 | 角色 | 建筑 | 行为 |
|------|------|------|------|
| **导游** | 小智 | 圣索菲亚 | 导览讲解、多语言、问答 |
| **导游** | 明德法师 | 雍和宫 | 导览讲解、佛教知识、问答 |
| **历史人物** | 查士丁尼大帝 | 圣索菲亚 | 叙事独白、过场动画 |
| **历史人物** | 乾隆皇帝 | 雍和宫 | 叙事独白、宣读圣旨 |
| **历史人物** | 宗喀巴大师 | 雍和宫 | 叙事独白、讲经演示 |
| **游客 NPC** | 小明 | 全建筑 | 漫游、拍照、提问 |
| **游客 NPC** | Sarah | 全建筑 | 漫游、拍照、多语言 |
| **工作人员** | 安保大叔 | 全建筑 | 巡逻、站岗、提醒 |

---

## 📋 开发计划（5 Phase，22 任务）

### Phase 1: 基础架构（08-01 → 08-30）
- 任务: `Task-001-Phase1-Infrastructure.md`
- 3021 ID: `task-5851bd9401`
- 状态: 🟡 **In Progress**
- 负责人: 擎天柱
- 子任务: UE5项目初始化 → 多建筑框架 → 主菜单 → PixelStreaming

### Phase 2: 场景与资产（08-30 → 11-30）
- 任务: `Task-002-Phase2-Scene-Assets.md`
- 3021 ID: `task-224d99687e`
- 状态: ⬜ Todo
- 负责人: 铁皮
- 子任务: 圣索菲亚导入 → 雍和宫建模 → 灯光 → DCC管线

### Phase 3: 人物系统（09-30 → 10-30）
- 任务: `Task-003-Character-System-Spec.md`
- 3021 ID: `task-3885aa180c`
- 状态: ⬜ Todo
- 负责人: 铁皮
- 子任务: 角色基类 → 导游AI → 历史人物 → 游客NPC → 工作人员 → 管理器 → 语音

### Phase 4: 交互与文化内容（10-30 → 12-30）
- 任务: `Task-004-Phase4-Interaction-Content.md`
- 3021 ID: `task-0da07afcea`
- 状态: ⬜ Todo
- 负责人: 通天晓
- 子任务: 展点交互 → 内容管理 → 本地化 → 用户存档

### Phase 5: 优化与交付（12-30 → 02-28）
- 任务: `Task-005-Phase5-Optimization-Release.md`
- 3021 ID: `task-a7a95966da`
- 状态: ⬜ Todo
- 负责人: 擎天柱
- 子任务: LOD/Nanite → 流媒体调优 → 测试 → 发布包

---

## 🏆 里程碑

| 里程碑 | 日期 | 交付物 | 状态 |
|--------|------|--------|------|
| M1 | 2026-08-01 | 项目立项 | ✅ Done |
| M2 | 2026-08-30 | 主菜单+多建筑切换 | 🟡 进行中 |
| M3 | 2026-09-30 | 圣索菲亚完整体验 | ⬜ |
| M4 | 2026-10-30 | 人物系统 MVP | ⬜ |
| M5 | 2026-11-30 | 雍和宫建模完成 | ⬜ |
| M6 | 2026-12-30 | 雍和宫完整体验 | ⬜ |
| M7 | 2027-01-30 | Beta 发布 | ⬜ |
| M8 | 2027-02-28 | 正式发布 | ⬜ |

---

## 📁 文件结构

```
SacredJourney/
├── SacredJourney.uproject
├── Config/
├── Content/
│   ├── Common/
│   │   ├── Data/
│   │   │   └── LandmarkCatalog.json
│   │   ├── Characters/
│   │   │   └── CharacterCatalog.json
│   │   └── UI/
│   ├── Sophia/
│   │   ├── ProjectData/
│   │   │   └── SophiaScene.json
│   │   └── Exhibits/
│   │       └── SophiaExhibits.json
│   └── Yonghe/
│       ├── ProjectData/
│       │   └── YongheScene.json
│       └── Exhibits/
│           └── YongheExhibits.json
├── Source/
│   └── SacredJourney/
│       ├── Character/
│       │   ├── SJCharacterBase.h
│       │   ├── SJGuideCharacter.h
│       │   ├── SJHistoricalFigure.h
│       │   └── SJTouristNPC.h
│       └── Systems/
│           ├── SJCharacterManager.h
│           └── SJLandmarkCatalog.h
├── DCC/
│   ├── Sophia/
│   │   └── build_sophia.py
│   └── Yonghe/
│       ├── build_yonghe.py
│       └── validate_yonghe.py
├── Content/PixelStreaming/
│   └── configs/
│       └── config-sacredjourney.json
├── tasks/
│   ├── Task-001-Phase1-Infrastructure.md
│   ├── Task-002-Phase2-Scene-Assets.md
│   ├── Task-003-Character-System-Spec.md
│   ├── Task-004-Phase4-Interaction-Content.md
│   └── Task-005-Phase5-Optimization-Release.md
└── PROJECT.md
```

---

*最后更新: 2026-08-01*