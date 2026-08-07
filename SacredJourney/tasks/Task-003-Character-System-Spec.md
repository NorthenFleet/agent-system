# Task-003: 人物系统详细规范

> **项目**: SacredJourney 数字文旅
> **Phase**: 3（人物系统 MVP）
> **3021 任务 ID**: task-3885aa180c
> **负责人**: 铁皮（ironhide）
> **截止日期**: 2026-10-30
> **关联项目**: proj-778a846996

---

## 📋 任务概述

构建完整的人物系统，包含 8 个角色、4 种角色类型、AI 驱动的交互行为。

---

## 👥 角色清单（8 角色，4 类型）

### 1. 导游类（2 角色）

#### 小智 🇹🇷
| 属性 | 值 |
|------|-----|
| 角色 ID | `xiao_zhi` |
| 类型 | Guide |
| 关联建筑 | 圣索菲亚大教堂 |
| 外观 | 现代导游装束，年轻热情 |
| 语言 | 中文（简体）、土耳其语 |

**行为树**:
```
GuideAI
├── OnStart → 欢迎语 + 建筑简介
├── OnRoute → 沿预设路径移动到下一展点
├── OnArrive → 触发讲解（文本 + 语音）
├── OnQuestion → 问答系统（3 个预设问题）
└── OnEnd → 告别语 + 评分邀请
```

**导览路线（圣索菲亚）**:
```json
[
  {"stop": 1, "landmark": "中央穹顶", "duration_s": 120, "script": "dome_intro"},
  {"stop": 2, "landmark": "镶嵌画", "duration_s": 90, "script": "mosaic_tour"},
  {"stop": 3, "landmark": "苏丹包厢", "duration_s": 60, "script": "sultan_box"},
  {"stop": 4, "landmark": "大理石门", "duration_s": 90, "script": "marble_gate"},
  {"stop": 5, "landmark": "地下蓄水池", "duration_s": 120, "script": "cistern_tour"},
  {"stop": 6, "landmark": "二层看台", "duration_s": 60, "script": "gallery_view"}
]
```

#### 明德法师 🇨🇳
| 属性 | 值 |
|------|-----|
| 角色 ID | `ming_de` |
| 类型 | Guide |
| 关联建筑 | 雍和宫 |
| 外观 | 藏传佛教僧袍，中年沉稳 |
| 语言 | 中文（简体）、藏语 |

**行为树**:
```
GuideAI
├── OnStart → 合十礼 + 雍和宫缘起
├── OnRoute → 沿寺院中轴线移动
├── OnArrive → 讲解建筑历史与佛教故事
├── OnQuestion → 问答系统（佛教知识）
└── OnEnd → 祝福 + 回向文
```

**导览路线（雍和宫）**:
```json
[
  {"stop": 1, "landmark": "牌坊", "duration_s": 60, "script": "arch_intro"},
  {"stop": 2, "landmark": "昭泰门", "duration_s": 60, "script": "zhao_gate"},
  {"stop": 3, "landmark": "天王殿", "duration_s": 90, "script": "hall_kings"},
  {"stop": 4, "landmark": "雍和宫殿", "duration_s": 120, "script": "main_hall"},
  {"stop": 5, "landmark": "永佑殿", "duration_s": 90, "script": "yongyou_hall"},
  {"stop": 6, "landmark": "法轮殿", "duration_s": 120, "script": "dharma_hall"},
  {"stop": 7, "landmark": "万福阁", "duration_s": 120, "script": "wanfu_pavilion"},
  {"stop": 8, "landmark": "绥成殿", "duration_s": 60, "script": "suicheng_hall"}
]
```

---

### 2. 历史人物类（3 角色）

#### 查士丁尼大帝 🏛️
| 属性 | 值 |
|------|-----|
| 角色 ID | `justinian` |
| 类型 | Historical |
| 关联建筑 | 圣索菲亚大教堂 |
| 时期 | 公元 527-565 年 |
| 出现场景 | 中央穹顶（过场动画） |

**叙事场景**:
```json
{
  "trigger": "player_approaches_dome",
  "animation": "emperor_speech_loop",
  "monologue": [
    "我，查士丁尼，罗马人的皇帝...",
    "这座圣殿，是上帝赐予我们的礼物。",
    "所罗门啊，我已经超越了你！"
  ],
  "duration_s": 45,
  "camera": "dramatic_pan_up"
}
```

#### 乾隆皇帝 🐉
| 属性 | 值 |
|------|-----|
| 角色 ID | `qianlong` |
| 类型 | Historical |
| 关联建筑 | 雍和宫 |
| 时期 | 公元 1735-1796 年 |
| 出现场景 | 雍和宫殿（宣读圣旨） |

**叙事场景**:
```json
{
  "trigger": "player_enters_main_hall",
  "animation": "emperor_decree_loop",
  "monologue": [
    "朕自幼好佛，深悟佛法...",
    "雍和宫者，朕潜龙邸也。",
    "今改为喇嘛庙，永垂后世。"
  ],
  "duration_s": 40,
  "camera": "throne_room_approach"
}
```

#### 宗喀巴大师 📿
| 属性 | 值 |
|------|-----|
| 角色 ID | `tsongkhapa` |
| 类型 | Historical |
| 关联建筑 | 雍和宫 |
| 时期 | 公元 1357-1419 年 |
| 出现场景 | 法轮殿（讲经演示） |

**叙事场景**:
```json
{
  "trigger": "player_enters_dharma_hall",
  "animation": "master_teaching_loop",
  "monologue": [
    "诸法因缘生，诸法因缘灭。",
    "菩提心者，大乘之本也。",
    "当以戒定慧，次第修学。"
  ],
  "duration_s": 50,
  "camera": "temple_interior_orbit"
}
```

---

### 3. 游客 NPC 类（2 角色）

#### 小明 📱
| 属性 | 值 |
|------|-----|
| 角色 ID | `xiao_ming` |
| 类型 | Tourist |
| 行为 | 自由漫游、拍照打卡、偶尔驻足观看 |
| 对话 | "哇，太壮观了！" "帮我拍张照！" |

**行为模式**:
```
TouristAI
├── Wander → 随机路径点移动（NavMesh）
├── Photo → 在指定地标停留 5s 做拍照动作
├── Observe → 在其他展点附近驻足观看（10-30s）
└── React → 对导游讲解做表情反应
```

#### Sarah 🌍
| 属性 | 值 |
|------|-----|
| 角色 ID | `sarah` |
| 类型 | Tourist |
| 行为 | 自由漫游、阅读展板、偶尔拍照 |
| 对话 | "Amazing!" "Let me read this plaque." |

**行为模式**: 同小明，不同的漫游路径和驻足点

---

### 4. 工作人员类（1 角色）

#### 安保大叔 👮
| 属性 | 值 |
|------|-----|
| 角色 ID | `security` |
| 类型 | Staff |
| 行为 | 巡逻循环、站岗守卫 |
| 对话 | "请注意不要触摸展品。" |

**行为模式**:
```
StaffAI
├── Patrol → 沿固定路径巡逻（NavMesh）
├── StandGuard → 在关键位置站岗（3min 循环）
└── Interact → 玩家靠近时触发提醒
```

---

## 🏗️ C++ 架构设计

### 类层次结构

```
UObject
└── AActor
    └── ASJCharacterBase
        ├── ASJGuideCharacter（导游）
        ├── ASJHistoricalFigure（历史人物）
        ├── ASJTouristNPC（游客）
        └── ASJStaffNPC（工作人员）
```

### ASJCharacterBase 接口

```cpp
// ASJCharacterBase.h
UCLASS(Abstract)
class ASJCharacterBase : public ACharacter
{
    GENERATED_BODY()

public:
    // 角色标识
    UPROPERTY(EditAnywhere, Category = "Character")
    FString CharacterId;

    UPROPERTY(EditAnywhere, Category = "Character")
    ECharacterType Type;

    // 行为接口
    UFUNCTION(BlueprintNativeEvent, Category = "Behavior")
    void StartBehavior();

    UFUNCTION(BlueprintNativeEvent, Category = "Behavior")
    void StopBehavior();

    // 交互接口
    UFUNCTION(BlueprintNativeEvent, Category = "Interaction")
    void OnPlayerApproach(AActor* Player);

    UFUNCTION(BlueprintNativeEvent, Category = "Interaction")
    void OnPlayerInteract();

    // 语音接口
    UFUNCTION(BlueprintNativeEvent, Category = "Audio")
    void PlayVoiceLine(const FString& ScriptId);

    // 移动接口
    UFUNCTION(BlueprintNativeEvent, Category = "Movement")
    void MoveToLandmark(const FString& LandmarkId);

protected:
    // 行为树组件
    UPROPERTY(VisibleAnywhere, Category = "AI")
    UBehaviorTreeComponent* BehaviorTreeComp;

    // 动画实例
    UPROPERTY(VisibleAnywhere, Category = "Animation")
    UAnimInstance* CharacterAnimInstance;
};
```

### ASJGuideCharacter 扩展

```cpp
// ASJGuideCharacter.h
UCLASS()
class ASJGuideCharacter : public ASJCharacterBase
{
    GENERATED_BODY()

public:
    // 导览配置
    UPROPERTY(EditAnywhere, Category = "Guide")
    TArray<FGuidedTourStop> TourStops;

    UPROPERTY(EditAnywhere, Category = "Guide")
    float StopDurationSeconds = 90.0f;

    UPROPERTY(EditAnywhere, Category = "Guide")
    TMap<FString, FString> Scripts;

    // 问答系统
    UPROPERTY(EditAnywhere, Category = "Guide")
    TArray<FQuestionAnswer> FAQ;

    // 多语言
    UPROPERTY(EditAnywhere, Category = "Guide")
    ELanguage CurrentLanguage = ELanguage::Chinese;

    // 导游专属行为
    UFUNCTION(BlueprintNativeEvent, Category = "Guide")
    void StartGuidedTour();

    UFUNCTION(BlueprintNativeEvent, Category = "Guide")
    void MoveToNextStop();

    UFUNCTION(BlueprintNativeEvent, Category = "Guide")
    void AnswerQuestion(int32 QuestionIndex);
};
```

### SJCharacterManager 全局管理器

```cpp
// SJCharacterManager.h
UCLASS()
class USJCharacterManager : public UActorComponent
{
    GENERATED_BODY()

public:
    // 从 JSON 加载角色配置
    UFUNCTION(BlueprintCallable, Category = "Character")
    bool LoadCharacterCatalog(const FString& JsonPath);

    // 生成角色到指定建筑
    UFUNCTION(BlueprintCallable, Category = "Character")
    ASJCharacterBase* SpawnCharacter(
        const FString& CharacterId,
        const FString& BuildingId,
        const FVector& Location,
        const FRotator& Rotation
    );

    // 销毁角色
    UFUNCTION(BlueprintCallable, Category = "Character")
    void DespawnCharacter(const FString& CharacterId);

    // 按建筑查询
    UFUNCTION(BlueprintCallable, Category = "Character")
    TArray<ASJCharacterBase*> GetCharactersByBuilding(
        const FString& BuildingId
    );

    // 按类型查询
    UFUNCTION(BlueprintCallable, Category = "Character")
    TArray<ASJCharacterBase*> GetCharactersByType(
        ECharacterType Type
    );

private:
    UPROPERTY()
    TMap<FString, ASJCharacterBase*> SpawnedCharacters;

    UPROPERTY()
    TMap<FString, FCharacterConfig> CharacterConfigs;
};
```

---

## 📊 数据结构

### CharacterCatalog.json（完整结构）

```json
{
  "version": "1.0",
  "buildings": ["sophia", "yonghe"],
  "characters": [
    {
      "id": "xiao_zhi",
      "type": "guide",
      "building": "sophia",
      "name_zh": "小智",
      "name_en": "Xiao Zhi",
      "voice_lines": {
        "welcome_zh": "欢迎来到圣索菲亚大教堂！",
        "welcome_en": "Welcome to Hagia Sophia!",
        "goodbye_zh": "感谢您的参观，祝您旅途愉快！",
        "goodbye_en": "Thank you for visiting!"
      },
      "tour_stops": [
        {"landmark": "central_dome", "script": "dome_intro", "duration_s": 120},
        {"landmark": "mosaics", "script": "mosaic_tour", "duration_s": 90}
      ],
      "faq": [
        {
          "question_zh": "圣索菲亚大教堂建于哪一年？",
          "answer_zh": "公元 537 年，由查士丁尼大帝下令建造。",
          "question_en": "When was Hagia Sophia built?",
          "answer_en": "In 537 AD, commissioned by Emperor Justinian."
        }
      ],
      "animation_set": "Guide_Modern",
      "mesh": "/Game/Characters/Guides/SK_Guide_Modern.SK_Guide_Modern"
    }
  ]
}
```

---

## 🔧 实现任务分解

### 子任务清单（7 项）

| # | 子任务 | 预估工时 | 依赖 |
|---|--------|---------|------|
| 3.1 | SJCharacterBase 基类框架 | 3 天 | Phase 1 基础架构 |
| 3.2 | SJGuideCharacter 导游 AI | 5 天 | 3.1 |
| 3.3 | SJHistoricalFigure 历史人物叙事 | 4 天 | 3.1 |
| 3.4 | SJTouristNPC 游客行为 | 3 天 | 3.1 |
| 3.5 | SJStaffNPC 工作人员 | 2 天 | 3.1 |
| 3.6 | SJCharacterManager 全局管理器 | 4 天 | 3.1 |
| 3.7 | 语音系统集成 | 3 天 | 3.2 |

**总计**: ~24 天（约 5 周，并行执行）

---

## ✅ 验收标准

1. **所有 8 个角色可生成到场景中**
2. **导游可完成完整导览路线（6+ 站点）**
3. **历史人物在触发区域播放叙事动画**
4. **游客 NPC 自由漫游 + 拍照行为**
5. **工作人员巡逻 + 站岗循环**
6. **角色可通过 CharacterManager 按建筑/类型查询**
7. **语音系统可播放多语言讲解**
8. **所有行为可通过 Blueprint 配置（无需改代码）**

---

## 📝 技术注意事项

- **UE 版本**: 5.8
- **动画系统**: Control Rig + Animation Blueprints
- **AI 系统**: Behavior Tree + Blackboard + EQS
- **导航**: NavMesh + Recast
- **语音**: MetaSounds + TTS 集成
- **多语言**: DataTable 驱动本地化

---

*创建日期: 2026-08-01*
*最后更新: 2026-08-01*
