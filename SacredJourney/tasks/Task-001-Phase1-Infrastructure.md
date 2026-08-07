# Task-001: Phase 1 基础架构搭建

> **项目**: SacredJourney 数字文旅
> **Phase**: 1（基础架构）
> **3021 任务 ID**: task-5851bd9401
> **状态**: in_progress
> **负责人**: 擎天柱（optimus）
> **截止日期**: 2026-08-30
> **关联项目**: proj-778a846996

---

## 📋 任务概述

搭建 SacredJourney UE5 项目基础架构，实现多建筑切换框架、主菜单 UI 和 PixelStreaming 配置。

---

## 🔧 子任务清单

### 1.1 创建 SacredJourney.uproject 项目 ✅
- [x] UE5.8 Blank 项目初始化
- [x] 项目配置（DefaultGame.ini / DefaultEngine.ini）
- [x] C++ 模块 SacredJourney 创建
- [x] .gitignore 配置

### 1.2 搭建 Common 共享模块 ✅
- [x] `/Game/Common/Data/LandmarkCatalog.json` 建筑目录
- [x] `/Game/Common/UI/` 主菜单 UI Widget
- [x] `/Game/Common/Systems/` 场景加载器
- [ ] `/Game/Common/Characters/CharacterCatalog.json` 角色目录（待 Phase 3）

### 1.3 场景目录结构 ✅
- [x] `/Game/Sophia/` 圣索菲亚大教堂（独立场景合同）
- [x] `/Game/Yonghe/` 雍和宫（独立场景合同）
- [x] 两个建筑完全独立，不共享资产

### 1.4 PixelStreaming 配置 ✅
- [x] `config-sacredjourney.json` 流媒体配置
- [x] 双建筑 URL 路由

---

## 📁 已创建文件清单

| 文件 | 说明 |
|------|------|
| `SacredJourney.uproject` | UE5.8 项目文件 |
| `Config/DefaultGame.ini` | 游戏配置 |
| `Config/DefaultEngine.ini` | 引擎配置 |
| `Content/Common/Data/LandmarkCatalog.json` | 建筑目录 |
| `Content/Sophia/ProjectData/SophiaScene.json` | 圣索菲亚场景合同 |
| `Content/Yonghe/ProjectData/YongheScene.json` | 雍和宫场景合同 |
| `Content/Common/Characters/CharacterCatalog.json` | 角色目录 |
| `README.md` | 项目文档 |

---

## ✅ 验收标准

1. SacredJourney.uproject 可打开编译通过
2. 主菜单可选择建筑
3. PixelStreaming 可远程访问
4. 圣索菲亚和雍和宫场景可独立加载

---

*创建日期: 2026-08-01*
