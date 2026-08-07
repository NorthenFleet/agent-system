# Task-004: Phase 4 交互与文化内容

> **项目**: SacredJourney 数字文旅
> **Phase**: 4（交互与文化内容）
> **3021 任务 ID**: task-0da07afcea
> **状态**: todo
> **负责人**: 通天晓（ultra-magnus）
> **截止日期**: 2026-12-30
> **关联项目**: proj-778a846996

---

## 📋 任务概述

实现展点交互系统、文化内容管理、多语言本地化和用户存档功能。

---

## 📍 展点交互系统

### 4.1 展点数据结构

```json
{
  "exhibit_id": "sophia_dome_01",
  "building": "sophia",
  "landmark": "central_dome",
  "position": [0, 0, 3500],
  "interactable": true,
  "content": {
    "title_zh": "中央穹顶",
    "title_en": "Central Dome",
    "title_tr": "Merkez Kubbe",
    "description_zh": "圣索菲亚大教堂的中央穹顶高 55.6 米，直径 31 米...",
    "description_en": "The central dome of Hagia Sophia rises 55.6 meters...",
    "images": ["/Game/Sophia/Exhibits/Dome_01.jpg"],
    "audio_guide": {
      "zh": "/Game/Sophia/Audio/Dome_zh.wav",
      "en": "/Game/Sophia/Audio/Dome_en.wav"
    },
    "3d_model": null
  },
  "triggers": {
    "on_approach": "play_intro_audio",
    "on_interact": "show_detail_panel",
    "on_leave": "hide_detail_panel"
  }
}
```

### 4.2 交互类型

| 类型 | 说明 | 示例 |
|------|------|------|
| 信息展板 | 图文展示 | 历史年代、建筑参数 |
| 3D 模型查看 | 旋转查看 | 微型佛像、建筑构件 |
| 音频讲解 | 多语言播放 | 导游语音 |
| 过场动画 | 自动播放 | 历史重现 |

---

## 🌐 多语言本地化

### 4.3 支持语言

| 语言 | 代码 | 覆盖建筑 |
|------|------|----------|
| 中文（简体） | zh | 全部 |
| 英语 | en | 全部 |
| 土耳其语 | tr | 圣索菲亚 |
| 藏语 | bo | 雍和宫 |

### 4.4 本地化实现

- 使用 UE5 DataTable 存储翻译文本
- 所有 UI 文本通过 `FText` + `LOCTEXT` 本地化
- 音频文件按语言分目录存放

---

## 💾 用户存档系统

### 4.5 存档数据

```json
{
  "save_slot": "slot_01",
  "player_name": "孙总",
  "visit_log": [
    {"building": "sophia", "completed_exhibits": 5, "total_exhibits": 8},
    {"building": "yonghe", "completed_exhibits": 2, "total_exhibits": 10}
  ],
  "collected_items": [],
  "settings": {
    "language": "zh",
    "voice_volume": 0.8,
    "guide_speed": 1.0
  },
  "play_time_minutes": 45
}
```

---

## ✅ 验收标准

1. 所有展点可交互点击
2. 文化内容（文本/图片/3D 模型）正确显示
3. 中英文切换完整
4. 用户进度可保存/加载

---

*创建日期: 2026-08-01*
