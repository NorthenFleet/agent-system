/**
 * Task-Plan 数据模型定义
 * 
 * 描述任务 (Task) 与开发计划 (Development Plan) 的从属关系
 * 一对多关系：一个任务可以关联多个开发计划（方案迭代）
 * 
 * @author 李奥纳多 (🐢 架构师)
 * @created 2026-04-16
 */

// ============================================================================
// 枚举类型定义
// ============================================================================

/** 任务状态枚举 */
export enum TaskStatus {
  PENDING = 'pending',           // 待处理
  IN_PROGRESS = 'in_progress',   // 进行中
  TESTING = 'testing',           // 测试中
  COMPLETED = 'completed',       // 已完成
  FAILED = 'failed',             // 已失败
  BLOCKED = 'blocked'            // 已阻塞
}

/** 任务优先级枚举 */
export enum TaskPriority {
  LOW = 'low',                   // 低
  NORMAL = 'normal',             // 普通
  HIGH = 'high',                 // 高
  CRITICAL = 'critical'          // 紧急
}

/** 计划状态枚举 */
export enum PlanStatus {
  DRAFT = 'draft',               // 草稿
  PENDING_REVIEW = 'pending_review',  // 待审核
  APPROVED = 'approved',         // 已通过
  REJECTED = 'rejected',         // 已拒绝
  IN_PROGRESS = 'in_progress',   // 执行中
  COMPLETED = 'completed',       // 已完成
  ARCHIVED = 'archived'          // 已归档
}

/** 计划步骤状态枚举 */
export enum PlanStepStatus {
  PENDING = 'pending',           // 待执行
  IN_PROGRESS = 'in_progress',   // 执行中
  COMPLETED = 'completed',       // 已完成
  SKIPPED = 'skipped',           // 已跳过
  BLOCKED = 'blocked'            // 已阻塞
}

// ============================================================================
// 核心数据模型
// ============================================================================

/**
 * 任务上下文 - 任务的完整背景信息
 */
export interface TaskContext {
  background: string;                    // 任务背景
  requirements: string[];                // 需求列表
  resources: ResourceLink[];             // 相关资源链接
  acceptanceCriteria: string[];          // 验收标准
  dependencies: string[];                // 依赖任务 ID 列表
  techStack: string[];                   // 技术栈
  notes: string;                         // 备注
  [key: string]: any;                    // 允许扩展字段
}

/**
 * 资源链接
 */
export interface ResourceLink {
  title: string;
  url: string;
  type: 'doc' | 'code' | 'design' | 'reference';
}

/**
 * 子任务
 */
export interface SubTask {
  id: string;
  title: string;
  assignee: string;
  completed: boolean;
  completedAt?: string;
  createdAt: string;
}

/**
 * 任务模型 (Task Model)
 * 
 * 表示一个完整的工作任务，可关联多个开发计划
 */
export interface Task {
  // 基础信息
  id: string;                            // 任务 ID (格式：YYYYMMDD-XXX)
  title: string;                         // 任务标题
  description: string;                   // 任务描述
  priority: TaskPriority;                // 优先级
  
  // 状态信息
  status: TaskStatus;                    // 任务状态
  progress: number;                      // 进度百分比 (0-100)
  
  // 人员信息
  assignee: string;                      // 负责人
  creator: string;                       // 创建人
  reviewers: string[];                   // 审核人列表
  
  // 时间信息
  createdAt: string;                     // 创建时间 (ISO 8601)
  updatedAt: string;                     // 更新时间 (ISO 8601)
  startedAt?: string;                    // 开始时间
  completedAt?: string;                  // 完成时间
  deadline?: string;                     // 截止时间
  
  // 从属关系
  activePlanId?: string;                 // 当前激活的计划 ID
  planIds: string[];                     // 关联的计划 ID 列表 (一对多)
  
  // 任务详情
  context: TaskContext;                  // 任务上下文
  subtasks: SubTask[];                   // 子任务列表
  tags: string[];                        // 标签
  
  // 扩展字段
  metadata?: {
    source?: string;                     // 任务来源
    estimatedHours?: number;             // 预估工时
    actualHours?: number;                // 实际工时
    [key: string]: any;
  };
}

/**
 * 计划步骤 (Plan Step)
 * 
 * 开发计划中的具体执行步骤
 */
export interface PlanStep {
  index: number;                         // 步骤序号
  name: string;                          // 步骤名称
  description: string;                   // 步骤描述
  estimatedHours: number;                // 预估工时
  status: PlanStepStatus;                // 步骤状态
  executor: string;                      // 执行人
  startedAt?: string;                    // 开始时间
  completedAt?: string;                  // 完成时间
  output?: string;                       // 产出物描述
  dependencies: number[];                // 依赖的步骤索引
}

/**
 * 开发计划模型 (Development Plan Model)
 * 
 * 任务的从属对象，描述如何完成任务的详细方案
 * 一个任务可以有多个计划（方案迭代），但同一时间只有一个激活计划
 */
export interface DevelopmentPlan {
  // 基础信息
  id: string;                            // 计划 ID (格式：plan_YYYYMMDDHHMMSS)
  taskId: string;                        // 所属任务 ID (外键)
  title: string;                         // 计划标题
  version: number;                       // 版本号 (从 1 开始)
  
  // 状态信息
  status: PlanStatus;                    // 计划状态
  type: 'frontend' | 'backend' | 'testing' | 'design' | 'research' | 'general';
  
  // 人员信息
  creator: string;                       // 创建人 (通常是李奥纳多)
  reviewer?: string;                     // 审核人 (通常是擎天柱)
  executors: string[];                   // 执行人列表
  
  // 时间信息
  createdAt: string;                     // 创建时间
  reviewedAt?: string;                   // 审核时间
  startedAt?: string;                    // 开始执行时间
  completedAt?: string;                  // 完成时间
  
  // 计划内容
  steps: PlanStep[];                     // 执行步骤列表
  estimatedTotalHours: number;           // 总预估工时
  actualTotalHours?: number;             // 总实际工时
  
  // 审核信息
  reviewComment?: string;                // 审核意见
  rejectionReason?: string;              // 拒绝原因
  
  // 从属关系元数据
  isBasedOn?: string;                    // 基于的计划 ID (版本迭代时)
  supersededBy?: string;                 // 被哪个计划替代
  
  // 扩展字段
  metadata?: {
    riskLevel?: 'low' | 'medium' | 'high';
    confidence?: number;                 // 信心指数 0-1
    alternatives?: string[];             // 备选方案描述
    [key: string]: any;
  };
}

// ============================================================================
// 从属关系接口
// ============================================================================

/**
 * Task-Plan 关系摘要
 * 
 * 用于快速查询任务与其计划的关联关系
 */
export interface TaskPlanRelation {
  taskId: string;
  taskTitle: string;
  taskStatus: TaskStatus;
  activePlanId?: string;
  activePlanStatus?: PlanStatus;
  totalPlans: number;
  approvedPlans: number;
  lastPlanCreatedAt: string;
}

/**
 * 计划执行进度
 */
export interface PlanProgress {
  planId: string;
  taskId: string;
  totalSteps: number;
  completedSteps: number;
  progressPercentage: number;
  currentStepIndex?: number;
  nextStepName?: string;
  estimatedRemainingHours: number;
}

// ============================================================================
// API 请求/响应模型
// ============================================================================

/**
 * 创建任务请求
 */
export interface CreateTaskRequest {
  title: string;
  description?: string;
  priority?: TaskPriority;
  assignee: string;
  deadline?: string;
  context?: Partial<TaskContext>;
  tags?: string[];
}

/**
 * 更新任务请求
 */
export interface UpdateTaskRequest {
  title?: string;
  description?: string;
  priority?: TaskPriority;
  status?: TaskStatus;
  progress?: number;
  assignee?: string;
  deadline?: string;
  context?: Partial<TaskContext>;
  tags?: string[];
}

/**
 * 创建开发计划请求
 */
export interface CreatePlanRequest {
  taskId: string;
  title?: string;
  type: DevelopmentPlan['type'];
  steps: Omit<PlanStep, 'status' | 'startedAt' | 'completedAt'>[];
  metadata?: DevelopmentPlan['metadata'];
}

/**
 * 更新开发计划请求
 */
export interface UpdatePlanRequest {
  title?: string;
  status?: PlanStatus;
  steps?: PlanStep[];
  reviewComment?: string;
  metadata?: DevelopmentPlan['metadata'];
}

/**
 * 审核计划请求
 */
export interface ReviewPlanRequest {
  approved: boolean;
  comment?: string;
  rejectionReason?: string;
}

/**
 * 任务响应 (包含嵌套计划)
 */
export interface TaskResponse extends Task {
  plans?: DevelopmentPlan[];             // 嵌套的计划列表
  activePlan?: DevelopmentPlan;          // 当前激活的计划
}

/**
 * 计划响应 (包含所属任务)
 */
export interface PlanResponse extends DevelopmentPlan {
  task?: Task;                           // 嵌套的所属任务
}

// ============================================================================
// 工具函数类型
// ============================================================================

/**
 * 计划生成器接口
 * 
 * 李奥纳多根据任务类型自动生成计划模板
 */
export interface PlanGenerator {
  generatePlanTemplate(task: Task): Omit<CreatePlanRequest, 'taskId'>;
}

/**
 * 任务 - 计划管理器接口
 */
export interface TaskPlanManager {
  // Task CRUD
  createTask(request: CreateTaskRequest): Promise<Task>;
  getTask(taskId: string, includePlans?: boolean): Promise<TaskResponse>;
  updateTask(taskId: string, request: UpdateTaskRequest): Promise<Task>;
  deleteTask(taskId: string): Promise<void>;
  listTasks(filters?: TaskFilters): Promise<Task[]>;
  
  // Plan CRUD
  createPlan(request: CreatePlanRequest): Promise<DevelopmentPlan>;
  getPlan(planId: string, includeTask?: boolean): Promise<PlanResponse>;
  updatePlan(planId: string, request: UpdatePlanRequest): Promise<DevelopmentPlan>;
  deletePlan(planId: string): Promise<void>;
  listPlans(filters?: PlanFilters): Promise<DevelopmentPlan[]>;
  
  // 从属关系管理
  setActivePlan(taskId: string, planId: string): Promise<Task>;
  reviewPlan(planId: string, request: ReviewPlanRequest): Promise<DevelopmentPlan>;
  getTaskPlanRelation(taskId: string): Promise<TaskPlanRelation>;
  getPlanProgress(planId: string): Promise<PlanProgress>;
  
  // 自动计划生成
  generatePlanForTask(taskId: string): Promise<DevelopmentPlan>;
}

/**
 * 任务查询过滤器
 */
export interface TaskFilters {
  status?: TaskStatus | TaskStatus[];
  priority?: TaskPriority | TaskPriority[];
  assignee?: string | string[];
  creator?: string;
  tags?: string[];
  hasActivePlan?: boolean;
  createdAfter?: string;
  createdBefore?: string;
  deadlineAfter?: string;
  deadlineBefore?: string;
  limit?: number;
  offset?: number;
  sortBy?: 'createdAt' | 'updatedAt' | 'deadline' | 'priority';
  sortOrder?: 'asc' | 'desc';
}

/**
 * 计划查询过滤器
 */
export interface PlanFilters {
  taskId?: string;
  status?: PlanStatus | PlanStatus[];
  type?: DevelopmentPlan['type'] | DevelopmentPlan['type'][];
  creator?: string;
  reviewer?: string;
  createdAfter?: string;
  createdBefore?: string;
  limit?: number;
  offset?: number;
  sortBy?: 'createdAt' | 'reviewedAt' | 'completedAt';
  sortOrder?: 'asc' | 'desc';
}

// ============================================================================
// 导出
// ============================================================================

export {
  TaskStatus,
  TaskPriority,
  PlanStatus,
  PlanStepStatus,
  TaskContext,
  ResourceLink,
  SubTask,
  Task,
  PlanStep,
  DevelopmentPlan,
  TaskPlanRelation,
  PlanProgress,
  CreateTaskRequest,
  UpdateTaskRequest,
  CreatePlanRequest,
  UpdatePlanRequest,
  ReviewPlanRequest,
  TaskResponse,
  PlanResponse,
  PlanGenerator,
  TaskPlanManager,
  TaskFilters,
  PlanFilters
};
