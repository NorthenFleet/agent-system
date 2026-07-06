<template>
  <div class="intelligence-page">
    <section class="page-head">
      <div>
        <h1>🌐 情报信息</h1>
        <p>面向特定领域的长期数据积累、历史沉淀和专题分析</p>
      </div>
      <el-input
        v-model="keyword"
        class="search-input"
        clearable
        placeholder="搜索领域、数据源或采集任务"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
    </section>

    <section class="metric-grid">
      <article class="metric-card">
        <span>专题领域</span>
        <strong>{{ filteredDomains.length }}</strong>
        <small>{{ activeDomains }} 个持续采集中</small>
      </article>
      <article class="metric-card">
        <span>长期数据源</span>
        <strong>{{ sourceCount }}</strong>
        <small>AIS、项目规划、外部资料等</small>
      </article>
      <article class="metric-card">
        <span>历史积累</span>
        <strong>{{ totalRecords }}</strong>
        <small>结构化记录与时间序列</small>
      </article>
    </section>

    <section class="section-panel">
      <div class="section-head">
        <div>
          <h2>专题情报库</h2>
          <p>每个专题都有独立的数据源、采集节奏、历史数据和分析目标</p>
        </div>
        <el-tag effect="plain">{{ filteredDomains.length }} 个专题</el-tag>
      </div>

      <div class="domain-grid">
        <article v-for="domain in filteredDomains" :key="domain.id" class="domain-card">
          <div class="card-top">
            <div class="title-wrap">
              <span class="icon-tile">{{ domain.icon }}</span>
              <div>
                <h3>{{ domain.name }}</h3>
                <p>{{ domain.description }}</p>
              </div>
            </div>
            <el-tag :type="statusType(domain.status)" size="small" effect="plain">
              {{ statusLabel(domain.status) }}
            </el-tag>
          </div>

          <div class="domain-meta">
            <span>数据源</span>
            <strong>{{ domain.sources.length }} 个</strong>
            <span>记录量</span>
            <strong>{{ domain.records }}</strong>
            <span>更新时间</span>
            <strong>{{ domain.updatedAt }}</strong>
          </div>

          <div class="chip-row">
            <el-tag v-for="source in domain.sources" :key="source" size="small" effect="plain">
              {{ source }}
            </el-tag>
          </div>

          <div class="analysis-block">
            <span>分析目标</span>
            <p>{{ domain.goal }}</p>
          </div>
        </article>
      </div>
    </section>

    <section class="section-panel">
      <div class="section-head">
        <div>
          <h2>采集与沉淀流程</h2>
          <p>情报信息强调连续采集、清洗入库、关联分析和长期回溯</p>
        </div>
      </div>

      <div class="pipeline-grid">
        <article v-for="step in pipeline" :key="step.name" class="pipeline-card">
          <span class="step-index">{{ step.index }}</span>
          <h3>{{ step.name }}</h3>
          <p>{{ step.description }}</p>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Search } from '@element-plus/icons-vue'

type DomainStatus = 'active' | 'planning' | 'paused'

interface IntelligenceDomain {
  id: string
  name: string
  icon: string
  description: string
  status: DomainStatus
  sources: string[]
  records: string
  recordValue: number
  updatedAt: string
  goal: string
}

const keyword = ref('')

const domains = ref<IntelligenceDomain[]>([
  {
    id: 'task-planning',
    name: '任务规划项目情报',
    icon: '📋',
    description: '长期记录任务规划、拆解、执行反馈和复盘结果',
    status: 'active',
    sources: ['项目管理', '任务列表', '智能体反馈', '复盘记录'],
    records: '12,480',
    recordValue: 12480,
    updatedAt: '持续更新',
    goal: '形成可追溯的项目规划知识库，支持项目经理复用历史任务拆解、风险识别和执行模式。'
  },
  {
    id: 'naval-ais',
    name: '海上军舰 AIS 情报',
    icon: '🌊',
    description: '围绕特定海域和目标舰船积累 AIS 轨迹与活动历史',
    status: 'planning',
    sources: ['AIS 数据', '海域网格', '舰船档案', '轨迹时间线'],
    records: '待接入',
    recordValue: 0,
    updatedAt: '规划中',
    goal: '长期沉淀舰船位置、航速、航向、靠泊和异常轨迹，形成历史活动画像。'
  },
  {
    id: 'knowledge-assets',
    name: '知识资产情报',
    icon: '🗂️',
    description: '沉淀资料、文档、知识节点与业务主题之间的关系',
    status: 'active',
    sources: ['知识库', '文档撰写', '项目资料', '会议摘要'],
    records: '3,260',
    recordValue: 3260,
    updatedAt: '每日同步',
    goal: '构建跨项目、跨智能体可复用的背景材料和证据链，减少重复调研。'
  },
  {
    id: 'external-watch',
    name: '外部环境专题',
    icon: '🛰️',
    description: '对指定行业、区域或组织进行长期跟踪，而不是一次性新闻浏览',
    status: 'paused',
    sources: ['RSS', '公开网页', '人工标注', '趋势摘要'],
    records: '860',
    recordValue: 860,
    updatedAt: '暂停采集',
    goal: '把每日碎片信息转化为长期趋势、实体画像和专题判断。'
  }
])

const pipeline = [
  { index: '01', name: '定义专题', description: '明确领域、目标对象、采集边界、时间尺度和分析用途。' },
  { index: '02', name: '连续采集', description: '按任务或定时器抓取结构化数据、文件、事件和外部来源。' },
  { index: '03', name: '清洗入库', description: '统一字段、去重、补充元数据，并保留原始证据引用。' },
  { index: '04', name: '历史分析', description: '按时间线、实体、地点和项目关系做检索、回溯与趋势判断。' }
]

const filteredDomains = computed(() => {
  const key = keyword.value.trim().toLowerCase()
  if (!key) return domains.value
  return domains.value.filter(domain => [
    domain.name,
    domain.description,
    domain.goal,
    domain.updatedAt,
    ...domain.sources
  ].some(value => value.toLowerCase().includes(key)))
})

const activeDomains = computed(() => domains.value.filter(domain => domain.status === 'active').length)
const sourceCount = computed(() => new Set(domains.value.flatMap(domain => domain.sources)).size)
const totalRecords = computed(() => domains.value.reduce((sum, domain) => sum + domain.recordValue, 0).toLocaleString())

function statusLabel(status: DomainStatus) {
  const labels: Record<DomainStatus, string> = {
    active: '采集中',
    planning: '规划中',
    paused: '暂停'
  }
  return labels[status]
}

function statusType(status: DomainStatus) {
  if (status === 'active') return 'success'
  if (status === 'planning') return 'warning'
  return 'info'
}
</script>

<style scoped>
.intelligence-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  color: var(--text-primary);
}

.page-head,
.metric-card,
.section-panel,
.domain-card,
.pipeline-card {
  background: var(--card-bg);
  border: 1px solid var(--line-color);
  border-radius: 8px;
}

.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px;
}

.page-head h1,
.section-head h2,
.domain-card h3,
.pipeline-card h3 {
  margin: 0;
  letter-spacing: 0;
}

.page-head h1 {
  font-size: 22px;
}

.page-head p,
.section-head p,
.title-wrap p,
.analysis-block p,
.pipeline-card p,
.metric-card small,
.domain-meta span {
  color: var(--text-secondary);
}

.page-head p,
.section-head p {
  margin: 6px 0 0;
  font-size: 13px;
}

.search-input {
  width: 320px;
}

.metric-grid,
.pipeline-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.metric-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px;
}

.metric-card span {
  color: var(--text-secondary);
  font-size: 13px;
}

.metric-card strong {
  font-size: 24px;
  line-height: 1.1;
}

.section-panel {
  padding: 16px;
}

.section-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.section-head h2 {
  font-size: 16px;
}

.domain-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 12px;
}

.domain-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  background: var(--card-bg-soft);
}

.card-top,
.title-wrap {
  display: flex;
  align-items: flex-start;
}

.card-top {
  justify-content: space-between;
  gap: 12px;
}

.title-wrap {
  min-width: 0;
  gap: 10px;
}

.title-wrap h3 {
  font-size: 15px;
}

.title-wrap p {
  margin: 5px 0 0;
  font-size: 12px;
  line-height: 1.5;
}

.icon-tile {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  background: rgba(var(--view-rgb), 0.14);
  border-radius: 7px;
}

.domain-meta {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 8px 10px;
  padding-top: 10px;
  border-top: 1px solid var(--line-color);
  font-size: 12px;
}

.domain-meta strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.analysis-block {
  margin-top: auto;
  padding: 10px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.045);
  border-radius: 7px;
}

.analysis-block span {
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 600;
}

.analysis-block p,
.pipeline-card p {
  margin: 6px 0 0;
  font-size: 13px;
  line-height: 1.6;
}

.pipeline-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.pipeline-card {
  padding: 14px;
  background: var(--card-bg-soft);
}

.step-index {
  display: inline-block;
  margin-bottom: 12px;
  color: rgb(var(--view-rgb));
  font-size: 12px;
  font-weight: 700;
}

:deep(.el-input__wrapper) {
  border-radius: 6px;
}

@media (max-width: 1100px) {
  .pipeline-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 820px) {
  .page-head {
    align-items: stretch;
    flex-direction: column;
  }

  .search-input {
    width: 100%;
  }

  .metric-grid,
  .pipeline-grid {
    grid-template-columns: 1fr;
  }

  .domain-grid {
    grid-template-columns: 1fr;
  }
}
</style>
