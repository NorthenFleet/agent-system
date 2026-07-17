<template>
  <div class="tools-page">
    <section class="tools-toolbar">
      <div>
        <h2>工具管理</h2>
        <p>统一查看技能工具、定时任务和调度管理状态</p>
      </div>
      <div class="toolbar-actions">
        <el-input
          v-model="keyword"
          class="search-input"
          clearable
          placeholder="搜索工具、任务、触发词"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-button type="primary" :loading="loading" @click="loadAll">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </section>

    <section class="metric-grid">
      <article class="metric-card">
        <span class="metric-label">技能工具</span>
        <strong>{{ skills.length }}</strong>
        <small>{{ enabledSkillCount }} 个已启用</small>
      </article>
      <article class="metric-card">
        <span class="metric-label">网络采集</span>
        <strong>{{ crawlerStatus?.ready ? '就绪' : '未连接' }}</strong>
        <small>{{ crawlerStatus?.provider || 'Crawl4AI' }}</small>
      </article>
      <article class="metric-card">
        <span class="metric-label">定时任务</span>
        <strong>{{ tasks.length }}</strong>
        <small>{{ activeTaskCount }} 个运行中</small>
      </article>
      <article class="metric-card">
        <span class="metric-label">调度管理</span>
        <strong>{{ managerText }}</strong>
        <small>{{ managerRoleText }}</small>
      </article>
    </section>

    <section class="tool-section crawler-section">
      <div class="section-head">
        <div>
          <h3>网络采集工具</h3>
          <p>按需求抓取公开网页，输出适合智能体分析的 Markdown、链接与媒体信息</p>
        </div>
        <el-tag :type="crawlerStatus?.ready ? 'success' : 'danger'" effect="plain">
          {{ crawlerStatus?.ready ? '服务就绪' : '服务未就绪' }}
        </el-tag>
      </div>

      <div class="crawler-layout">
        <div class="crawler-overview">
          <div class="card-title">
            <span class="icon-tile"><el-icon><Connection /></el-icon></span>
            <div>
              <h4>{{ crawlerStatus?.provider || 'Crawl4AI' }}</h4>
              <span>GitHub 开源 · Apache-2.0 · 本机部署</span>
            </div>
          </div>
          <p class="card-desc">{{ crawlerStatus?.message || '正在检查网络采集服务' }}</p>
          <div class="meta-list">
            <span>使用范围</span>
            <strong>全部模块 · 全部智能体</strong>
            <span>服务地址</span>
            <strong>{{ crawlerStatus?.base_url || 'http://127.0.0.1:11235' }}</strong>
            <span>项目仓库</span>
            <a :href="crawlerStatus?.repository" target="_blank" rel="noreferrer">unclecode/crawl4ai</a>
          </div>
        </div>

        <div class="crawler-console">
          <el-input v-model="crawlerUrl" placeholder="输入要抓取的公开网页 URL" clearable />
          <el-input v-model="crawlerQuery" placeholder="关注的问题（可选，用于提取相关内容）" clearable />
          <div class="crawler-actions">
            <span>试运行会直接调用本机 Crawl4AI，不生成兜底内容</span>
            <el-button type="primary" :loading="crawlLoading" :disabled="!crawlerStatus?.ready" @click="runCrawler">
              <el-icon><Promotion /></el-icon>
              开始抓取
            </el-button>
          </div>
        </div>
      </div>

      <div v-if="crawlerResult" class="crawler-result">
        <div class="result-head">
          <strong>{{ crawlerResult.title || crawlerResult.url }}</strong>
          <span>{{ crawlerResult.content_length.toLocaleString() }} 字符 · HTTP {{ crawlerResult.status_code || '-' }}</span>
        </div>
        <pre>{{ crawlerResult.content }}</pre>
      </div>
    </section>

    <section class="tool-section">
      <div class="section-head">
        <div>
          <h3>技能工具</h3>
          <p>智能体可调用的能力、触发词和依赖工具</p>
        </div>
        <el-tag effect="plain">{{ filteredSkills.length }} / {{ skills.length }}</el-tag>
      </div>

      <el-skeleton v-if="loading && !skills.length" :rows="5" animated />
      <el-empty v-else-if="!filteredSkills.length" description="暂无匹配的技能工具" />
      <div v-else class="card-grid">
        <article v-for="skill in filteredSkills" :key="skill.id || skill.name" class="tool-card">
          <div class="card-topline">
            <div class="card-title">
              <span class="icon-tile"><el-icon><Tools /></el-icon></span>
              <div>
                <h4>{{ skill.name }}</h4>
                <span>{{ skill.category || '未分类技能' }}</span>
              </div>
            </div>
            <el-tag :type="skillStatusType(skill)" size="small" effect="plain">
              {{ skillStatusLabel(skill) }}
            </el-tag>
          </div>
          <p class="card-desc">{{ skill.description || '暂无说明' }}</p>
          <div class="meta-list">
            <span>来源</span>
            <strong>{{ skill.source || '本地' }}</strong>
            <span>路径</span>
            <strong>{{ skill.path || '未配置' }}</strong>
          </div>
          <div v-if="skill.triggers?.length" class="chip-row">
            <el-tag v-for="trigger in skill.triggers.slice(0, 6)" :key="trigger" size="small" effect="plain">
              {{ trigger }}
            </el-tag>
          </div>
          <div v-if="skill.required_tools?.length" class="chip-row muted">
            <el-tag v-for="tool in skill.required_tools.slice(0, 5)" :key="tool" size="small" type="info" effect="plain">
              {{ tool }}
            </el-tag>
          </div>
        </article>
      </div>
    </section>

    <section class="tool-section">
      <div class="section-head">
        <div>
          <h3>定时任务</h3>
          <p>平台自动执行的巡检、通知和同步任务</p>
        </div>
        <el-tag effect="plain">{{ filteredTasks.length }} / {{ tasks.length }}</el-tag>
      </div>

      <el-skeleton v-if="loading && !tasks.length" :rows="5" animated />
      <el-empty v-else-if="!filteredTasks.length" description="暂无匹配的定时任务" />
      <div v-else class="card-grid">
        <article v-for="task in filteredTasks" :key="task.id || task.name" class="tool-card">
          <div class="card-topline">
            <div class="card-title">
              <span class="icon-tile"><el-icon><Calendar /></el-icon></span>
              <div>
                <h4>{{ task.name }}</h4>
                <span>{{ task.owner || '未指定负责人' }}</span>
              </div>
            </div>
            <el-tag :type="taskStatusType(task.status)" size="small" effect="plain">
              {{ taskStatusLabel(task.status) }}
            </el-tag>
          </div>
          <p class="card-desc">{{ task.description || '暂无说明' }}</p>
          <div class="meta-list">
            <span>计划</span>
            <strong>{{ task.schedule || '未配置' }}</strong>
            <span>下次执行</span>
            <strong>{{ task.next_run || '未排期' }}</strong>
            <span>上次执行</span>
            <strong>{{ task.last_run || '暂无记录' }}</strong>
          </div>
          <div class="task-footer">
            <span>成功率</span>
            <el-progress
              :percentage="taskSuccessRate(task)"
              :stroke-width="8"
              :show-text="false"
            />
            <strong>{{ taskSuccessRate(task) }}%</strong>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Calendar, Connection, Promotion, Refresh, Search, Tools } from '@element-plus/icons-vue'
import {
  crawlWebPage,
  getScheduledTasks,
  getSkills,
  getWebCrawlerStatus,
  type ScheduledTask,
  type SkillItem,
  type WebCrawlerResult,
  type WebCrawlerStatus
} from '@/api/openclaw'

const loading = ref(false)
const keyword = ref('')
const skills = ref<SkillItem[]>([])
const tasks = ref<ScheduledTask[]>([])
const managedBy = ref('')
const managerRole = ref('')
const crawlerStatus = ref<WebCrawlerStatus | null>(null)
const crawlerUrl = ref('')
const crawlerQuery = ref('')
const crawlLoading = ref(false)
const crawlerResult = ref<WebCrawlerResult | null>(null)

const normalizedKeyword = computed(() => keyword.value.trim().toLowerCase())

const filteredSkills = computed(() => {
  const q = normalizedKeyword.value
  if (!q) return skills.value
  return skills.value.filter((skill) => [
    skill.name,
    skill.description,
    skill.category,
    skill.source,
    skill.path,
    ...(skill.triggers || []),
    ...(skill.required_tools || [])
  ].some((value) => String(value || '').toLowerCase().includes(q)))
})

const filteredTasks = computed(() => {
  const q = normalizedKeyword.value
  if (!q) return tasks.value
  return tasks.value.filter((task) => [
    task.name,
    task.description,
    task.owner,
    task.schedule,
    task.status,
    task.next_run,
    task.last_run
  ].some((value) => String(value || '').toLowerCase().includes(q)))
})

const enabledSkillCount = computed(() => skills.value.filter((skill) => skill.enabled !== false && skill.status !== 'disabled').length)
const activeTaskCount = computed(() => tasks.value.filter((task) => ['active', 'running', 'enabled'].includes(task.status)).length)
const managerText = computed(() => managedBy.value || '未配置')
const managerRoleText = computed(() => managerRole.value || '暂无角色说明')

async function loadAll() {
  loading.value = true
  try {
    const [skillsData, scheduledData, crawlerData] = await Promise.all([
      getSkills(),
      getScheduledTasks(),
      getWebCrawlerStatus()
    ])
    skills.value = skillsData.skills || []
    tasks.value = scheduledData.tasks || []
    managedBy.value = scheduledData.managed_by || ''
    managerRole.value = scheduledData.manager_role || ''
    crawlerStatus.value = crawlerData
  } catch (error) {
    console.error(error)
    ElMessage.error('工具管理数据加载失败')
  } finally {
    loading.value = false
  }
}

async function runCrawler() {
  const url = crawlerUrl.value.trim()
  if (!url) {
    ElMessage.warning('请输入要抓取的网页 URL')
    return
  }
  crawlLoading.value = true
  crawlerResult.value = null
  try {
    crawlerResult.value = await crawlWebPage(url, crawlerQuery.value.trim())
    ElMessage.success('网页抓取完成')
  } catch (error: any) {
    console.error(error)
    ElMessage.error(error?.response?.data?.detail || '网页抓取失败')
  } finally {
    crawlLoading.value = false
  }
}

function skillStatusLabel(skill: SkillItem) {
  if (skill.enabled === false || skill.status === 'disabled') return '停用'
  if (skill.status === 'draft') return '草稿'
  if (skill.status === 'error') return '异常'
  return '启用'
}

function skillStatusType(skill: SkillItem) {
  if (skill.enabled === false || skill.status === 'disabled') return 'info'
  if (skill.status === 'error') return 'danger'
  if (skill.status === 'draft') return 'warning'
  return 'success'
}

function taskStatusLabel(status: string) {
  const labels: Record<string, string> = {
    active: '运行中',
    running: '运行中',
    enabled: '已启用',
    paused: '已暂停',
    disabled: '停用',
    failed: '异常',
    error: '异常',
    draft: '草稿'
  }
  return labels[status] || status || '未知'
}

function taskStatusType(status: string) {
  if (['active', 'running', 'enabled'].includes(status)) return 'success'
  if (['failed', 'error'].includes(status)) return 'danger'
  if (status === 'paused') return 'warning'
  return 'info'
}

function taskSuccessRate(task: ScheduledTask) {
  const value = Number(task.success_rate ?? 0)
  if (Number.isNaN(value)) return 0
  if (value <= 1) return Math.round(value * 100)
  return Math.max(0, Math.min(100, Math.round(value)))
}

onMounted(loadAll)
</script>

<style scoped>
.tools-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  color: var(--text-primary);
}

.tools-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px;
  background: var(--panel-bg);
  border: 1px solid var(--line-color);
  border-radius: 8px;
}

.tools-toolbar h2,
.section-head h3,
.card-title h4 {
  margin: 0;
  letter-spacing: 0;
}

.tools-toolbar h2 {
  font-size: 20px;
}

.tools-toolbar p,
.section-head p,
.card-title span,
.metric-card small,
.card-desc,
.meta-list span {
  color: var(--text-secondary);
}

.tools-toolbar p,
.section-head p {
  margin: 6px 0 0;
  font-size: 13px;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.search-input {
  width: 280px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.crawler-layout {
  display: grid;
  grid-template-columns: minmax(260px, 0.8fr) minmax(360px, 1.2fr);
  gap: 24px;
}

.crawler-overview,
.crawler-console {
  min-width: 0;
}

.crawler-console {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.crawler-actions,
.result-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.crawler-actions span,
.result-head span {
  color: var(--text-secondary);
  font-size: 12px;
}

.meta-list a {
  color: rgb(var(--view-rgb));
  text-decoration: none;
}

.crawler-result {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--line-color);
}

.crawler-result pre {
  max-height: 360px;
  margin: 12px 0 0;
  padding: 12px;
  overflow: auto;
  color: var(--text-primary);
  background: var(--page-bg);
  border: 1px solid var(--line-color);
  border-radius: 6px;
  white-space: pre-wrap;
  word-break: break-word;
  font: 12px/1.6 ui-monospace, SFMono-Regular, Menlo, monospace;
}

.metric-card,
.tool-section,
.tool-card {
  background: var(--card-bg);
  border: 1px solid var(--line-color);
  border-radius: 8px;
}

.metric-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px;
}

.metric-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.metric-card strong {
  font-size: 22px;
  line-height: 1.1;
}

.tool-section {
  padding: 16px;
}

.section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.section-head h3 {
  font-size: 16px;
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 12px;
}

.tool-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 210px;
  padding: 14px;
  background: var(--card-bg-soft);
}

.card-topline,
.card-title,
.task-footer {
  display: flex;
  align-items: center;
}

.card-topline {
  justify-content: space-between;
  gap: 10px;
}

.card-title {
  min-width: 0;
  gap: 10px;
}

.card-title h4 {
  max-width: 210px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 15px;
}

.card-title span {
  display: block;
  max-width: 210px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 4px;
  font-size: 12px;
}

.icon-tile {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  flex: 0 0 34px;
  color: rgb(var(--view-rgb));
  background: rgba(var(--view-rgb), 0.14);
  border-radius: 7px;
}

.card-desc {
  min-height: 40px;
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
}

.meta-list {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr);
  gap: 8px 10px;
  padding-top: 10px;
  border-top: 1px solid var(--line-color);
  font-size: 12px;
}

.meta-list strong {
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

.chip-row.muted {
  margin-top: -4px;
}

.task-footer {
  gap: 10px;
  margin-top: auto;
  color: var(--text-secondary);
  font-size: 12px;
}

.task-footer :deep(.el-progress) {
  flex: 1;
}

:deep(.el-input__wrapper),
:deep(.el-button) {
  border-radius: 6px;
}

:deep(.el-empty) {
  padding: 24px 0;
}

@media (max-width: 900px) {
  .tools-toolbar,
  .toolbar-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .search-input {
    width: 100%;
  }

  .metric-grid {
    grid-template-columns: 1fr;
  }

  .crawler-layout {
    grid-template-columns: 1fr;
  }

  .crawler-actions,
  .result-head {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
