-- ============================================================================
-- Migration 001: Add Plans Tables
-- 
-- 描述：创建任务与开发计划的从属关系相关表结构
-- 应用：team-dashboard/backend/migrations/001_add_plans.sql
-- 依赖：无
-- ============================================================================

-- 开始事务
BEGIN;

-- ============================================================================
-- 1. 枚举类型定义
-- ============================================================================

-- 任务状态枚举
DO $$ BEGIN
    CREATE TYPE task_status AS ENUM (
        'pending',        -- 待处理
        'in_progress',    -- 进行中
        'testing',        -- 测试中
        'completed',      -- 已完成
        'failed',         -- 已失败
        'blocked'         -- 已阻塞
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- 任务优先级枚举
DO $$ BEGIN
    CREATE TYPE task_priority AS ENUM (
        'low',            -- 低
        'normal',         -- 普通
        'high',           -- 高
        'critical'        -- 紧急
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- 计划状态枚举
DO $$ BEGIN
    CREATE TYPE plan_status AS ENUM (
        'draft',              -- 草稿
        'pending_review',     -- 待审核
        'approved',           -- 已通过
        'rejected',           -- 已拒绝
        'in_progress',        -- 执行中
        'completed',          -- 已完成
        'archived'            -- 已归档
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- 计划步骤状态枚举
DO $$ BEGIN
    CREATE TYPE plan_step_status AS ENUM (
        'pending',        -- 待执行
        'in_progress',    -- 执行中
        'completed',      -- 已完成
        'skipped',        -- 已跳过
        'blocked'         -- 已阻塞
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- 计划类型枚举
DO $$ BEGIN
    CREATE TYPE plan_type AS ENUM (
        'frontend',
        'backend',
        'testing',
        'design',
        'research',
        'general'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================================
-- 2. 核心表设计
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 2.1 tasks 表 (任务表)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tasks (
    -- 基础信息
    id                  VARCHAR(32) PRIMARY KEY,           -- 任务 ID (格式：YYYYMMDD-XXX)
    title               VARCHAR(500) NOT NULL,             -- 任务标题
    description         TEXT,                              -- 任务描述
    priority            task_priority NOT NULL DEFAULT 'normal',  -- 优先级
    
    -- 状态信息
    status              task_status NOT NULL DEFAULT 'pending',   -- 任务状态
    progress            INTEGER NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),  -- 进度百分比
    
    -- 人员信息
    assignee            VARCHAR(100) NOT NULL,             -- 负责人
    creator             VARCHAR(100) NOT NULL,             -- 创建人
    
    -- 时间信息
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at          TIMESTAMP WITH TIME ZONE,          -- 开始时间
    completed_at        TIMESTAMP WITH TIME ZONE,          -- 完成时间
    deadline            TIMESTAMP WITH TIME ZONE,          -- 截止时间
    
    -- 从属关系
    active_plan_id      VARCHAR(64),                       -- 当前激活的计划 ID (外键)
    
    -- 扩展字段 (JSONB 存储上下文、子任务、标签等)
    context             JSONB DEFAULT '{}'::jsonb,         -- 任务上下文
    subtasks            JSONB DEFAULT '[]'::jsonb,         -- 子任务列表
    tags                JSONB DEFAULT '[]'::jsonb,         -- 标签数组
    metadata            JSONB DEFAULT '{}'::jsonb,         -- 元数据
    
    -- 约束
    CONSTRAINT tasks_deadline_check CHECK (deadline IS NULL OR deadline > created_at)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee);
CREATE INDEX IF NOT EXISTS idx_tasks_creator ON tasks(creator);
CREATE INDEX IF NOT EXISTS idx_tasks_deadline ON tasks(deadline);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_updated_at ON tasks(updated_at);
CREATE INDEX IF NOT EXISTS idx_tasks_active_plan ON tasks(active_plan_id);
CREATE INDEX IF NOT EXISTS idx_tasks_tags ON tasks USING GIN(tags);

-- 全文搜索索引
CREATE INDEX IF NOT EXISTS idx_tasks_title_search ON tasks USING GIN(to_tsvector('simple', title));

-- ----------------------------------------------------------------------------
-- 2.2 plans 表 (开发计划表)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS plans (
    -- 基础信息
    id                  VARCHAR(64) PRIMARY KEY,           -- 计划 ID (格式：plan_YYYYMMDDHHMMSS)
    task_id             VARCHAR(32) NOT NULL,              -- 所属任务 ID (外键)
    title               VARCHAR(500) NOT NULL,             -- 计划标题
    version             INTEGER NOT NULL DEFAULT 1,        -- 版本号
    type                plan_type NOT NULL DEFAULT 'general',  -- 计划类型
    
    -- 状态信息
    status              plan_status NOT NULL DEFAULT 'draft',   -- 计划状态
    
    -- 人员信息
    creator             VARCHAR(100) NOT NULL,             -- 创建人
    reviewer            VARCHAR(100),                      -- 审核人
    executors           JSONB DEFAULT '[]'::jsonb,         -- 执行人列表
    
    -- 时间信息
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at         TIMESTAMP WITH TIME ZONE,          -- 审核时间
    started_at          TIMESTAMP WITH TIME ZONE,          -- 开始执行时间
    completed_at        TIMESTAMP WITH TIME ZONE,          -- 完成时间
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- 计划内容
    steps               JSONB NOT NULL DEFAULT '[]'::jsonb,  -- 执行步骤列表 (JSON 数组)
    estimated_total_hours NUMERIC(10,2) DEFAULT 0,         -- 总预估工时
    actual_total_hours  NUMERIC(10,2),                     -- 总实际工时
    
    -- 审核信息
    review_comment      TEXT,                              -- 审核意见
    rejection_reason    TEXT,                              -- 拒绝原因
    
    -- 从属关系元数据
    is_based_on         VARCHAR(64),                       -- 基于的计划 ID (版本迭代)
    superseded_by       VARCHAR(64),                       -- 被哪个计划替代
    
    -- 扩展字段
    metadata            JSONB DEFAULT '{}'::jsonb,         -- 元数据
    
    -- 外键约束
    CONSTRAINT fk_plans_task FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    CONSTRAINT fk_plans_based_on FOREIGN KEY (is_based_on) REFERENCES plans(id) ON DELETE SET NULL,
    CONSTRAINT fk_plans_superseded_by FOREIGN KEY (superseded_by) REFERENCES plans(id) ON DELETE SET NULL,
    
    -- 检查约束
    CONSTRAINT plans_version_check CHECK (version > 0),
    CONSTRAINT plans_hours_check CHECK (estimated_total_hours >= 0)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_plans_task_id ON plans(task_id);
CREATE INDEX IF NOT EXISTS idx_plans_status ON plans(status);
CREATE INDEX IF NOT EXISTS idx_plans_type ON plans(type);
CREATE INDEX IF NOT EXISTS idx_plans_creator ON plans(creator);
CREATE INDEX IF NOT EXISTS idx_plans_reviewer ON plans(reviewer);
CREATE INDEX IF NOT EXISTS idx_plans_created_at ON plans(created_at);
CREATE INDEX IF NOT EXISTS idx_plans_reviewed_at ON plans(reviewed_at);
CREATE INDEX IF NOT EXISTS idx_plans_version ON plans(task_id, version);  -- 复合索引

-- 唯一约束：同一任务的同一版本只能有一个计划
CREATE UNIQUE INDEX IF NOT EXISTS idx_plans_task_version_unique ON plans(task_id, version);

-- ----------------------------------------------------------------------------
-- 2.3 task_plans 关联表 (任务 - 计划历史关联表)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS task_plans (
    id                  SERIAL PRIMARY KEY,                -- 自增 ID
    task_id             VARCHAR(32) NOT NULL,              -- 任务 ID
    plan_id             VARCHAR(64) NOT NULL,              -- 计划 ID
    relation_type       VARCHAR(32) NOT NULL DEFAULT 'owns',  -- 关系类型
    is_active           BOOLEAN NOT NULL DEFAULT false,    -- 是否为当前激活关系
    activated_at        TIMESTAMP WITH TIME ZONE,          -- 激活时间
    deactivated_at      TIMESTAMP WITH TIME ZONE,          -- 失效时间
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- 外键约束
    CONSTRAINT fk_task_plans_task FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    CONSTRAINT fk_task_plans_plan FOREIGN KEY (plan_id) REFERENCES plans(id) ON DELETE CASCADE,
    
    -- 唯一约束：同一时间一个任务只能有一个激活计划
    CONSTRAINT task_plans_unique_active UNIQUE (task_id, is_active)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_task_plans_task_id ON task_plans(task_id);
CREATE INDEX IF NOT EXISTS idx_task_plans_plan_id ON task_plans(plan_id);
CREATE INDEX IF NOT EXISTS idx_task_plans_active ON task_plans(task_id, is_active);
CREATE INDEX IF NOT EXISTS idx_task_plans_relation_type ON task_plans(relation_type);

-- ----------------------------------------------------------------------------
-- 2.4 plan_steps 表 (计划步骤表)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS plan_steps (
    id                  SERIAL PRIMARY KEY,                -- 自增 ID
    plan_id             VARCHAR(64) NOT NULL,              -- 计划 ID
    step_index          INTEGER NOT NULL,                  -- 步骤序号
    name                VARCHAR(200) NOT NULL,             -- 步骤名称
    description         TEXT,                              -- 步骤描述
    estimated_hours     NUMERIC(10,2) NOT NULL DEFAULT 0,  -- 预估工时
    status              plan_step_status NOT NULL DEFAULT 'pending',
    executor            VARCHAR(100),                      -- 执行人
    started_at          TIMESTAMP WITH TIME ZONE,          -- 开始时间
    completed_at        TIMESTAMP WITH TIME ZONE,          -- 完成时间
    output              TEXT,                              -- 产出物描述
    dependencies        INTEGER[] DEFAULT '{}',            -- 依赖的步骤索引数组
    
    -- 外键约束
    CONSTRAINT fk_plan_steps_plan FOREIGN KEY (plan_id) REFERENCES plans(id) ON DELETE CASCADE,
    
    -- 唯一约束：同一计划的同一索引只能有一个步骤
    CONSTRAINT plan_steps_unique_index UNIQUE (plan_id, step_index),
    
    -- 检查约束
    CONSTRAINT plan_steps_hours_check CHECK (estimated_hours >= 0)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_plan_steps_plan_id ON plan_steps(plan_id);
CREATE INDEX IF NOT EXISTS idx_plan_steps_status ON plan_steps(status);
CREATE INDEX IF NOT EXISTS idx_plan_steps_executor ON plan_steps(executor);

-- ============================================================================
-- 3. 视图 (Views)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 3.1 v_task_plan_relation: 任务 - 计划关系视图
-- ----------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_task_plan_relation AS
SELECT 
    t.id AS task_id,
    t.title AS task_title,
    t.status AS task_status,
    t.active_plan_id,
    ap.status AS active_plan_status,
    ap.title AS active_plan_title,
    COUNT(p.id) AS total_plans,
    COUNT(CASE WHEN p.status = 'approved' THEN 1 END) AS approved_plans,
    MAX(p.created_at) AS last_plan_created_at
FROM tasks t
LEFT JOIN plans p ON t.id = p.task_id
LEFT JOIN plans ap ON t.active_plan_id = ap.id
GROUP BY t.id, t.title, t.status, t.active_plan_id, ap.status, ap.title;

-- ----------------------------------------------------------------------------
-- 3.2 v_plan_progress: 计划执行进度视图
-- ----------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_plan_progress AS
SELECT 
    p.id AS plan_id,
    p.task_id,
    p.title AS plan_title,
    p.status AS plan_status,
    JSONB_ARRAY_LENGTH(p.steps) AS total_steps,
    JSONB_ARRAY_LENGTH(
        JSONB_PATH_QUERY_ARRAY(p.steps, '$[*] ? (@.status == "completed")')
    ) AS completed_steps,
    ROUND(
        JSONB_ARRAY_LENGTH(
            JSONB_PATH_QUERY_ARRAY(p.steps, '$[*] ? (@.status == "completed")')
        ) * 100.0 / NULLIF(JSONB_ARRAY_LENGTH(p.steps), 0),
        2
    ) AS progress_percentage,
    p.estimated_total_hours,
    p.actual_total_hours
FROM plans p
WHERE p.status IN ('approved', 'in_progress');

-- ----------------------------------------------------------------------------
-- 3.3 v_task_with_plans: 任务及其计划详情视图
-- ----------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_task_with_plans AS
SELECT 
    t.id AS task_id,
    t.title AS task_title,
    t.status AS task_status,
    t.priority AS task_priority,
    t.assignee,
    t.creator,
    t.progress,
    t.deadline,
    t.active_plan_id,
    JSONB_AGG(
        JSONB_BUILD_OBJECT(
            'id', p.id,
            'title', p.title,
            'version', p.version,
            'status', p.status,
            'type', p.type,
            'creator', p.creator,
            'created_at', p.created_at,
            'estimated_total_hours', p.estimated_total_hours
        ) ORDER BY p.version
    ) FILTER (WHERE p.id IS NOT NULL) AS plans
FROM tasks t
LEFT JOIN plans p ON t.id = p.task_id
GROUP BY t.id, t.title, t.status, t.priority, t.assignee, t.creator, t.progress, t.deadline, t.active_plan_id;

-- ============================================================================
-- 4. 触发器 (Triggers)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 4.1 update_updated_at_column: 通用触发器函数
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ----------------------------------------------------------------------------
-- 4.2 tasks_updated_at: tasks 表自动更新 updated_at
-- ----------------------------------------------------------------------------

DROP TRIGGER IF EXISTS tasks_updated_at ON tasks;
CREATE TRIGGER tasks_updated_at
    BEFORE UPDATE ON tasks
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ----------------------------------------------------------------------------
-- 4.3 plans_updated_at: plans 表自动更新 updated_at
-- ----------------------------------------------------------------------------

DROP TRIGGER IF EXISTS plans_updated_at ON plans;
CREATE TRIGGER plans_updated_at
    BEFORE UPDATE ON plans
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ----------------------------------------------------------------------------
-- 4.4 maintain_task_plans_active: 维护 task_plans 表的激活状态
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION maintain_task_plans_active()
RETURNS TRIGGER AS $$
BEGIN
    -- 当任务的 active_plan_id 更新时，同步更新 task_plans 表
    IF NEW.active_plan_id IS DISTINCT FROM OLD.active_plan_id THEN
        -- 失效旧计划
        UPDATE task_plans 
        SET is_active = false, deactivated_at = CURRENT_TIMESTAMP
        WHERE task_id = NEW.id AND is_active = true;
        
        -- 激活新计划
        IF NEW.active_plan_id IS NOT NULL THEN
            INSERT INTO task_plans (task_id, plan_id, is_active, activated_at)
            VALUES (NEW.id, NEW.active_plan_id, true, CURRENT_TIMESTAMP)
            ON CONFLICT (task_id) 
            DO UPDATE SET 
                plan_id = EXCLUDED.plan_id,
                is_active = true,
                activated_at = CURRENT_TIMESTAMP,
                deactivated_at = NULL;
        END IF;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS task_plans_maintain_active ON tasks;
CREATE TRIGGER task_plans_maintain_active
    AFTER UPDATE ON tasks
    FOR EACH ROW
    EXECUTE FUNCTION maintain_task_plans_active();

-- ----------------------------------------------------------------------------
-- 4.5 insert_task_plans_on_plan_create: 创建计划时自动插入 task_plans 记录
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION insert_task_plans_on_plan_create()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO task_plans (task_id, plan_id, relation_type, is_active)
    VALUES (NEW.task_id, NEW.id, 'owns', false);
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS plans_insert_task_plans ON plans;
CREATE TRIGGER plans_insert_task_plans
    AFTER INSERT ON plans
    FOR EACH ROW
    EXECUTE FUNCTION insert_task_plans_on_plan_create();

-- ============================================================================
-- 提交事务
-- ============================================================================

COMMIT;

-- ============================================================================
-- 迁移完成
-- ============================================================================
