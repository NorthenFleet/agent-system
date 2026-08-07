<template>
  <section class="software-workspace-panel">
    <header class="workspace-head">
      <div>
        <span class="workspace-eyebrow">ENGINEERING WORKSPACE</span>
        <h3>研发文档与执行态势</h3>
        <p>仓库文档是设计事实源；项目任务和 Codex Job 是进度与机器状态事实源。</p>
      </div>
      <el-tooltip content="刷新仓库文档与执行状态">
        <el-button :icon="Refresh" circle :loading="loading" aria-label="刷新研发工作区" @click="loadWorkspace" />
      </el-tooltip>
    </header>

    <div class="workspace-progress-grid">
      <div class="workspace-stat progress-stat">
        <span>总体开发进度</span>
        <strong>{{ Math.round(project.progress || calculatedProgress) }}%</strong>
        <el-progress :percentage="Math.round(project.progress || calculatedProgress)" :show-text="false" />
      </div>
      <div class="workspace-stat">
        <span>任务完成</span>
        <strong>{{ taskSummary.done }} / {{ taskSummary.total }}</strong>
        <small>{{ taskSummary.running }} 进行 · {{ taskSummary.blocked }} 阻塞</small>
      </div>
      <div class="workspace-stat">
        <span>开发子项</span>
        <strong>{{ pointSummary.done }} / {{ pointSummary.total }}</strong>
        <small>{{ pointSummary.running }} 执行 · {{ pointSummary.todo }} 待办</small>
      </div>
      <div class="workspace-stat machine-stat">
        <span>研发执行机</span>
        <strong><i :class="['status-dot', machineOnline ? 'online' : 'offline']" />{{ machineLabel }}</strong>
        <small>{{ machineHost }} · {{ runnerLabel }}</small>
      </div>
    </div>

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-skeleton v-if="loading && !workspace" :rows="8" animated />

    <template v-else-if="workspace">
      <div class="repository-strip">
        <div><Connection /><span>{{ workspace.repository.branch || 'detached' }}</span></div>
        <div><Document /><span>{{ workspace.total_documents }} 份研发文档</span></div>
        <div><Cpu /><span>{{ workspace.repository.commit || '未知版本' }}</span></div>
        <div :class="{ warning: workspace.repository.dirty_count > 0 }">
          <Warning v-if="workspace.repository.dirty_count > 0" /><CircleCheck v-else />
          <span>{{ workspace.repository.dirty_count > 0 ? `${workspace.repository.dirty_count} 项未提交变更` : '工作区干净' }}</span>
        </div>
        <code :title="workspace.repository.path">{{ workspace.repository.path }}</code>
      </div>

      <div class="coverage-grid">
        <button
          v-for="item in workspace.coverage"
          :key="item.key"
          type="button"
          :class="['coverage-item', { active: categoryFilter === item.key, missing: item.count === 0 }]"
          @click="toggleCategory(item.key)"
        >
          <span>{{ item.label }}</span>
          <strong>{{ item.count }}</strong>
        </button>
      </div>

      <div class="document-browser">
        <aside class="document-tree-pane">
          <div class="pane-title">
            <div>
              <strong>{{ workspaceMode === 'documents' ? '项目文档树' : '源码管理' }}</strong>
              <small v-if="workspaceMode === 'documents'">{{ categoryFilter ? categoryLabel(categoryFilter) : '全部真实目录' }}</small>
              <small v-else>{{ gitRepositories.length }} 个子项目仓库 · {{ gitStatus?.repository_name || '选择仓库' }}</small>
            </div>
            <div class="pane-actions">
              <el-tooltip content="项目文档">
                <el-button
                  :icon="FolderOpened"
                  circle
                  size="small"
                  :type="workspaceMode === 'documents' ? 'primary' : ''"
                  aria-label="项目文档"
                  @click="workspaceMode = 'documents'"
                />
              </el-tooltip>
              <el-tooltip content="源码管理">
                <el-button
                  :icon="Share"
                  circle
                  size="small"
                  :type="workspaceMode === 'git' ? 'primary' : ''"
                  aria-label="源码管理"
                  @click="openGitWorkspace"
                />
              </el-tooltip>
              <el-input
                v-if="workspaceMode === 'documents'"
                v-model="treeFilter"
                size="small"
                placeholder="筛选文档"
                clearable
                :prefix-icon="Search"
              />
              <el-tooltip v-else content="刷新 Git 状态">
                <el-button :icon="Refresh" circle size="small" aria-label="刷新 Git 状态" :loading="gitLoading" @click="loadGitRepositories" />
              </el-tooltip>
            </div>
          </div>
          <div v-if="workspaceMode === 'documents'" class="workspace-tree">
            <SoftwareDocumentTreeNode
              :nodes="workspace.tree"
              :selected-path="selectedDocument?.path || ''"
              :text-filter="treeFilter"
              :category-filter="categoryFilter"
              @select="selectTreeNode"
            />
          </div>
          <div v-else v-loading="gitLoading" class="git-source-control">
            <el-alert v-if="gitError" :title="gitError" type="error" :closable="false" show-icon />
            <div v-if="gitRepositories.length" class="git-repository-list">
              <button
                v-for="repository in gitRepositories"
                :key="repository.repository_id"
                type="button"
                :class="{ active: selectedGitRepositoryId === repository.repository_id, unavailable: repository.error }"
                @click="selectGitRepository(repository)"
              >
                <span class="repository-icon"><Share /><i v-if="repository.total_changes">{{ repository.total_changes }}</i></span>
                <span class="repository-copy">
                  <strong>{{ repository.repository_name }}</strong>
                  <small>{{ repository.error || repository.branch || 'detached' }}</small>
                </span>
                <span class="repository-sync">↑{{ repository.ahead }} ↓{{ repository.behind }}</span>
              </button>
            </div>
            <template v-if="gitStatus">
              <el-alert
                v-if="gitStatus.truncated"
                :title="`${gitStatus.repository_name} 有 ${gitStatus.total_changes} 项改动，仅显示前 ${gitStatus.changes.length} 项，请先完善该仓库的 .gitignore。`"
                type="warning"
                :closable="false"
                show-icon
              />
              <div class="git-branch-summary">
                <div><Share /><strong>{{ gitStatus.repository_name }} · {{ gitStatus.branch || 'detached' }}</strong></div>
                <span v-if="gitStatus.upstream">{{ gitStatus.upstream }}</span>
                <small>↑ {{ gitStatus.ahead }} · ↓ {{ gitStatus.behind }}</small>
              </div>
              <div class="commit-editor">
                <el-input
                  v-model="commitMessage"
                  type="textarea"
                  :rows="3"
                  maxlength="2000"
                  show-word-limit
                  placeholder="提交说明"
                  resize="none"
                  @keydown.meta.enter.prevent="commitStagedChanges"
                  @keydown.ctrl.enter.prevent="commitStagedChanges"
                />
                <el-button
                  type="primary"
                  :icon="Check"
                  :disabled="!commitMessage.trim() || stagedChanges.length === 0"
                  :loading="gitCommitting"
                  @click="commitStagedChanges"
                >提交已暂存 ({{ gitStatus.staged_count }})</el-button>
              </div>

              <section class="change-group">
                <header>
                  <span>已暂存的更改 <b>{{ gitStatus.staged_count }}</b></span>
                  <el-tooltip content="全部取消暂存">
                    <el-button
                      :icon="Minus"
                      text
                      circle
                      size="small"
                      aria-label="全部取消暂存"
                      :disabled="stagedChanges.length === 0 || gitStatus.truncated"
                      @click="unstagePaths(stagedChanges.map(item => item.path))"
                    />
                  </el-tooltip>
                </header>
                <div
                  v-for="change in stagedChanges"
                  :key="`staged-${change.path}`"
                  role="button"
                  tabindex="0"
                  :class="['change-row', { active: selectedGitPath === change.path && selectedGitStaged }]"
                  @click="openGitDiff(change, true)"
                  @keydown.enter="openGitDiff(change, true)"
                >
                  <span class="change-name"><Document /><span><strong>{{ fileName(change.path) }}</strong><small>{{ directoryName(change.path) }}</small></span></span>
                  <i :class="['change-code', `status-${change.index_code.toLowerCase()}`]">{{ change.index_code }}</i>
                  <el-tooltip content="取消暂存">
                    <el-button :icon="Minus" text circle size="small" aria-label="取消暂存" @click.stop="unstagePaths([change.path])" />
                  </el-tooltip>
                </div>
                <div v-if="stagedChanges.length === 0" class="empty-change-group">暂无已暂存更改</div>
              </section>

              <section class="change-group">
                <header>
                  <span>更改 <b>{{ gitStatus.unstaged_count }}</b></span>
                  <el-tooltip :content="gitStatus.truncated ? '改动过多，请逐项暂存' : '全部暂存'">
                    <el-button
                      :icon="Plus"
                      text
                      circle
                      size="small"
                      aria-label="全部暂存"
                      :disabled="unstagedChanges.length === 0 || gitStatus.truncated"
                      @click="stagePaths(unstagedChanges.map(item => item.path))"
                    />
                  </el-tooltip>
                </header>
                <div
                  v-for="change in unstagedChanges"
                  :key="`unstaged-${change.path}`"
                  role="button"
                  tabindex="0"
                  :class="['change-row', { active: selectedGitPath === change.path && !selectedGitStaged }]"
                  @click="openGitDiff(change, false)"
                  @keydown.enter="openGitDiff(change, false)"
                >
                  <span class="change-name"><Document /><span><strong>{{ fileName(change.path) }}</strong><small>{{ directoryName(change.path) }}</small></span></span>
                  <i :class="['change-code', `status-${gitDisplayCode(change, false).toLowerCase()}`]">{{ gitDisplayCode(change, false) }}</i>
                  <el-tooltip content="暂存更改">
                    <el-button :icon="Plus" text circle size="small" aria-label="暂存更改" @click.stop="stagePaths([change.path])" />
                  </el-tooltip>
                </div>
                <div v-if="unstagedChanges.length === 0" class="empty-change-group">工作区没有未暂存更改</div>
              </section>

              <section class="recent-commits">
                <header><Clock /><span>最近提交</span></header>
                <div v-for="commit in gitStatus.commits.slice(0, 6)" :key="commit.hash" class="commit-row">
                  <code>{{ commit.hash }}</code>
                  <span><strong>{{ commit.subject }}</strong><small>{{ commit.author }} · {{ formatGitTime(commit.date) }}</small></span>
                </div>
              </section>
            </template>
          </div>
        </aside>

        <article class="document-preview-pane">
          <div v-if="workspaceMode === 'documents'" class="pane-title preview-title">
            <div>
              <strong>{{ selectedDocument?.name || '选择一份项目文档' }}</strong>
              <small>{{ selectedDocument?.path || '从左侧目录查看设计、数据结构、功能逻辑和接口文档' }}</small>
            </div>
            <el-tag v-if="selectedDocument" size="small" type="info">
              {{ categoryLabel(selectedDocument.category) }}
            </el-tag>
          </div>
          <div v-else class="pane-title preview-title">
            <div>
              <strong>{{ selectedGitPath || '选择一项更改查看差异' }}</strong>
              <small>{{ selectedGitPath ? `${gitStatus?.repository_name || ''} · ${selectedGitStaged ? '暂存区与 HEAD 的差异' : '工作区与暂存区的差异'}` : '从左侧选择子项目仓库和文件改动' }}</small>
            </div>
            <el-tag v-if="selectedGitPath" size="small" :type="selectedGitStaged ? 'success' : 'warning'">
              {{ selectedGitStaged ? '已暂存' : '未暂存' }}
            </el-tag>
          </div>
          <div v-if="workspaceMode === 'documents'" v-loading="documentLoading" class="document-preview-scroll">
            <el-empty v-if="!selectedDocument && !documentLoading" description="请选择文档" :image-size="54" />
            <div
              v-else-if="selectedDocument && isMarkdown"
              class="markdown-preview"
              v-html="renderedDocument"
            />
            <pre v-else-if="selectedDocument" class="code-preview"><code>{{ selectedDocument.content }}</code></pre>
            <div v-if="selectedDocument?.truncated" class="preview-truncated">文档较大，当前显示前 300,000 个字符。</div>
          </div>
          <div v-else v-loading="gitDiffLoading" class="git-diff-scroll">
            <el-empty v-if="!selectedGitPath && !gitDiffLoading" description="请选择一项更改" :image-size="54" />
            <el-alert v-else-if="gitDiff?.binary" title="二进制文件无法显示文本差异" type="info" :closable="false" show-icon />
            <pre v-else-if="gitDiff" class="diff-preview"><code><span
              v-for="(line, index) in diffLines"
              :key="index"
              :class="diffLineClass(line)"
            ><i>{{ index + 1 }}</i>{{ line || ' ' }}</span></code></pre>
            <div v-if="gitDiff?.truncated" class="preview-truncated">差异较大，当前显示前 400,000 个字符。</div>
          </div>
        </article>
      </div>

      <section class="execution-machine-section">
        <div class="section-title-row">
          <div>
            <strong>开发子任务机状态</strong>
            <small>每个开发要点与最近一次 Codex 执行记录对应；未派发项保留为待调度。</small>
          </div>
          <el-tag :type="machineOnline ? 'success' : 'danger'">{{ machineOnline ? '执行机在线' : '执行机不可用' }}</el-tag>
        </div>
        <div class="execution-table-wrap">
          <table class="execution-table">
            <thead>
              <tr>
                <th>任务 / 开发子项</th>
                <th>智能体</th>
                <th>业务状态</th>
                <th>执行状态</th>
                <th>执行机器</th>
                <th>最近更新</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in executionRows" :key="row.id">
                <td>
                  <strong>{{ row.pointTitle }}</strong>
                  <small>{{ row.taskTitle }}</small>
                </td>
                <td>{{ agentLabel(row.agent) }}</td>
                <td><el-tag size="small" :type="statusTag(row.businessStatus)">{{ statusLabel(row.businessStatus) }}</el-tag></td>
                <td>
                  <el-tag size="small" :type="jobStatusTag(row.job?.status)">{{ jobStatusLabel(row.job?.status) }}</el-tag>
                  <small v-if="row.job?.error" class="job-error" :title="row.job.error">{{ row.job.error }}</small>
                </td>
                <td>
                  <strong>{{ row.job ? machineLabel : '待调度' }}</strong>
                  <small>{{ row.job ? machineHost : '尚未分配执行机' }}</small>
                </td>
                <td>{{ formatTime(row.job?.updated_at) }}</td>
              </tr>
              <tr v-if="executionRows.length === 0">
                <td colspan="6" class="empty-row">暂无开发子项</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import MarkdownIt from 'markdown-it'
import { ElMessage } from 'element-plus'
import {
  Check, CircleCheck, Clock, Connection, Cpu, Document, FolderOpened,
  Minus, Plus, Refresh, Search, Share, Warning
} from '@element-plus/icons-vue'
import SoftwareDocumentTreeNode from '@/components/SoftwareDocumentTreeNode.vue'
import {
  commitProjectSoftwareFiles,
  getProjectSoftwareGitDiff,
  getProjectSoftwareGitRepositories,
  getProjectSoftwareDocument,
  getProjectSoftwareWorkspace,
  stageProjectSoftwareFiles,
  unstageProjectSoftwareFiles,
  type Project,
  type SoftwareDocumentContent,
  type SoftwareDocumentNode,
  type SoftwareGitChange,
  type SoftwareGitDiff,
  type SoftwareGitStatus,
  type SoftwareWorkspace
} from '@/api/projects'
import type { CodexJob, CodexStatus } from '@/api/codex'

const props = defineProps<{
  project: Project
  jobs: CodexJob[]
  codexStatus: CodexStatus | null
}>()

const markdown = new MarkdownIt({ html: false, linkify: true, breaks: false })
const loading = ref(false)
const documentLoading = ref(false)
const error = ref('')
const workspace = ref<SoftwareWorkspace | null>(null)
const selectedDocument = ref<SoftwareDocumentContent | null>(null)
const treeFilter = ref('')
const categoryFilter = ref('')
const workspaceMode = ref<'documents' | 'git'>('documents')
const gitLoading = ref(false)
const gitDiffLoading = ref(false)
const gitCommitting = ref(false)
const gitError = ref('')
const gitRepositories = ref<SoftwareGitStatus[]>([])
const selectedGitRepositoryId = ref('')
const gitStatus = ref<SoftwareGitStatus | null>(null)
const gitDiff = ref<SoftwareGitDiff | null>(null)
const selectedGitPath = ref('')
const selectedGitStaged = ref(false)
const commitMessages = ref<Record<string, string>>({})

const terminalStatuses = new Set(['done', 'completed'])
const runningStatuses = new Set(['in_progress', 'running', 'review', 'testing', 'assigned'])

const taskSummary = computed(() => summarizeStatuses(props.project.tasks.map(task => task.status)))
const allPoints = computed(() => props.project.tasks.flatMap(task => task.development_points || []))
const pointSummary = computed(() => summarizeStatuses(allPoints.value.map(point => point.status)))
const calculatedProgress = computed(() => {
  if (!allPoints.value.length) return 0
  return (pointSummary.value.done / allPoints.value.length) * 100
})
const machineOnline = computed(() => Boolean(props.codexStatus?.available && workspace.value?.machine.status === 'online'))
const machineLabel = computed(() => workspace.value?.machine.name || (props.codexStatus?.runner_mode === 'ssh' ? '远程执行机' : 'Mac mini'))
const machineHost = computed(() => workspace.value?.machine.host || props.codexStatus?.remote_host || 'localhost')
const runnerLabel = computed(() => props.codexStatus?.runner_mode === 'ssh' ? 'SSH Codex Runner' : '本地 Codex Runner')
const isMarkdown = computed(() => ['md', 'mdx'].includes(selectedDocument.value?.extension || ''))
const renderedDocument = computed(() => markdown.render(selectedDocument.value?.content || ''))
const commitMessage = computed({
  get: () => commitMessages.value[selectedGitRepositoryId.value] || '',
  set: value => {
    if (selectedGitRepositoryId.value) commitMessages.value[selectedGitRepositoryId.value] = value
  }
})
const stagedChanges = computed(() => gitStatus.value?.changes.filter(change => change.staged) || [])
const unstagedChanges = computed(() => gitStatus.value?.changes.filter(change => change.unstaged) || [])
const diffLines = computed(() => (gitDiff.value?.content || '').split('\n'))

const executionRows = computed(() => props.project.tasks.flatMap(task => {
  const points = task.development_points || []
  if (!points.length) {
    const job = latestJob(task.id)
    return [{
      id: task.id,
      taskTitle: task.title,
      pointTitle: '任务级执行',
      agent: task.assignee_agent_id || task.assignee_agent || '',
      businessStatus: task.status,
      job
    }]
  }
  return points.map(point => ({
    id: point.id,
    taskTitle: task.title,
    pointTitle: point.title,
    agent: point.assigned_agent || task.assignee_agent_id || task.assignee_agent || '',
    businessStatus: point.status,
    job: latestJob(point.id)
  }))
}))

function summarizeStatuses(statuses: string[]) {
  return statuses.reduce((summary, status) => {
    summary.total += 1
    if (terminalStatuses.has(status)) summary.done += 1
    else if (status === 'blocked' || status === 'failed') summary.blocked += 1
    else if (runningStatuses.has(status)) summary.running += 1
    else summary.todo += 1
    return summary
  }, { total: 0, done: 0, running: 0, blocked: 0, todo: 0 })
}

function latestJob(id: string) {
  return props.jobs
    .filter(job => job.task_id === id)
    .sort((a, b) => String(b.updated_at || b.created_at).localeCompare(String(a.updated_at || a.created_at)))[0]
}

async function loadWorkspace() {
  loading.value = true
  error.value = ''
  try {
    workspace.value = await getProjectSoftwareWorkspace(props.project.id)
    if (!selectedDocument.value) {
      const preferred = workspace.value.documents.find(item => item.path === 'docs/architecture/CODEX_DEVELOPMENT_MAP.md')
        || workspace.value.documents.find(item => item.path === 'docs/architecture/system-architecture.md')
        || workspace.value.documents.find(item => item.path === 'README.md')
        || workspace.value.documents[0]
      if (preferred) await loadDocument(preferred.path)
    }
  } catch (cause: any) {
    workspace.value = null
    error.value = cause?.response?.data?.detail || cause?.message || '研发仓库读取失败'
  } finally {
    loading.value = false
  }
}

async function loadDocument(path: string) {
  documentLoading.value = true
  try {
    selectedDocument.value = await getProjectSoftwareDocument(props.project.id, path)
  } catch (cause: any) {
    error.value = cause?.response?.data?.detail || '文档读取失败'
  } finally {
    documentLoading.value = false
  }
}

async function openGitWorkspace() {
  workspaceMode.value = 'git'
  if (!gitRepositories.value.length) await loadGitRepositories()
}

async function loadGitRepositories() {
  gitLoading.value = true
  gitError.value = ''
  try {
    const result = await getProjectSoftwareGitRepositories(props.project.id)
    gitRepositories.value = result.repositories
    const selected = gitRepositories.value.find(item => item.repository_id === selectedGitRepositoryId.value)
      || gitRepositories.value[0]
    if (selected) selectGitRepository(selected)
  } catch (cause: any) {
    gitError.value = gitErrorMessage(cause, 'Git 仓库列表读取失败')
  } finally {
    gitLoading.value = false
  }
}

function selectGitRepository(repository: SoftwareGitStatus) {
  selectedGitRepositoryId.value = repository.repository_id
  gitStatus.value = repository
  selectedGitPath.value = ''
  selectedGitStaged.value = false
  gitDiff.value = null
  gitError.value = repository.error || ''
}

function setActiveGitStatus(status: SoftwareGitStatus) {
  gitStatus.value = status
  const index = gitRepositories.value.findIndex(item => item.repository_id === status.repository_id)
  if (index >= 0) gitRepositories.value[index] = status
  else gitRepositories.value.push(status)
}

async function openGitDiff(change: SoftwareGitChange, staged: boolean) {
  selectedGitPath.value = change.path
  selectedGitStaged.value = staged
  gitDiffLoading.value = true
  gitError.value = ''
  try {
    gitDiff.value = await getProjectSoftwareGitDiff(props.project.id, selectedGitRepositoryId.value, change.path, staged)
  } catch (cause: any) {
    gitDiff.value = null
    gitError.value = gitErrorMessage(cause, 'Git 差异读取失败')
  } finally {
    gitDiffLoading.value = false
  }
}

async function stagePaths(paths: string[]) {
  if (!paths.length) return
  gitLoading.value = true
  gitError.value = ''
  try {
    setActiveGitStatus(await stageProjectSoftwareFiles(props.project.id, selectedGitRepositoryId.value, paths))
    ElMessage.success(paths.length === 1 ? '已暂存更改' : `已暂存 ${paths.length} 项更改`)
    await refreshSelectedGitDiff()
  } catch (cause: any) {
    gitError.value = gitErrorMessage(cause, '暂存失败')
    ElMessage.error(gitError.value)
  } finally {
    gitLoading.value = false
  }
}

async function unstagePaths(paths: string[]) {
  if (!paths.length) return
  gitLoading.value = true
  gitError.value = ''
  try {
    setActiveGitStatus(await unstageProjectSoftwareFiles(props.project.id, selectedGitRepositoryId.value, paths))
    ElMessage.success(paths.length === 1 ? '已取消暂存' : `已取消暂存 ${paths.length} 项更改`)
    await refreshSelectedGitDiff()
  } catch (cause: any) {
    gitError.value = gitErrorMessage(cause, '取消暂存失败')
    ElMessage.error(gitError.value)
  } finally {
    gitLoading.value = false
  }
}

async function commitStagedChanges() {
  const message = commitMessage.value.trim()
  if (!message || !stagedChanges.value.length) return
  gitCommitting.value = true
  gitError.value = ''
  try {
    const status = await commitProjectSoftwareFiles(props.project.id, selectedGitRepositoryId.value, message)
    setActiveGitStatus(status)
    commitMessage.value = ''
    selectedGitPath.value = ''
    gitDiff.value = null
    ElMessage.success(`${status.repository_name} 提交成功：${status.commit}`)
    await loadWorkspace()
  } catch (cause: any) {
    gitError.value = gitErrorMessage(cause, '提交失败')
    ElMessage.error(gitError.value)
  } finally {
    gitCommitting.value = false
  }
}

async function refreshSelectedGitDiff() {
  if (!selectedGitPath.value || !gitStatus.value) return
  const change = gitStatus.value.changes.find(item => item.path === selectedGitPath.value)
  if (!change) {
    selectedGitPath.value = ''
    gitDiff.value = null
    return
  }
  const staged = selectedGitStaged.value ? change.staged : !change.unstaged && change.staged
  if (!change.staged && !change.unstaged) return
  await openGitDiff(change, staged)
}

function gitErrorMessage(cause: any, fallback: string) {
  const detail = cause?.response?.data?.detail || cause?.message || fallback
  const labels: Record<string, string> = {
    nothing_staged: '没有已暂存的更改', invalid_git_path: '无效的 Git 文件路径',
    git_path_not_changed: '该文件已不在更改列表中', invalid_commit_message: '提交说明无效',
    staged_changes_outside_workspace: '上级仓库中存在当前项目之外的已暂存文件，请先在命令行取消这些文件的暂存后再提交'
  }
  return labels[detail] || detail
}

function gitDisplayCode(change: SoftwareGitChange, staged: boolean) {
  if (staged) return change.index_code.trim() || 'M'
  return change.index_code === '?' ? '?' : (change.worktree_code.trim() || 'M')
}

function fileName(path: string) {
  return path.split('/').pop() || path
}

function directoryName(path: string) {
  const parts = path.split('/')
  parts.pop()
  return parts.join('/') || '.'
}

function diffLineClass(line: string) {
  if (line.startsWith('+++') || line.startsWith('---')) return 'diff-file'
  if (line.startsWith('+')) return 'diff-add'
  if (line.startsWith('-')) return 'diff-delete'
  if (line.startsWith('@@')) return 'diff-hunk'
  if (line.startsWith('diff ') || line.startsWith('index ')) return 'diff-meta'
  return ''
}

function formatGitTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(date)
}

function selectTreeNode(node: SoftwareDocumentNode) {
  if (node.kind === 'file' && node.path) loadDocument(node.path)
}

function toggleCategory(category: string) {
  categoryFilter.value = categoryFilter.value === category ? '' : category
}

function categoryLabel(category?: string) {
  return workspace.value?.coverage.find(item => item.key === category)?.label || '研发文档'
}

function statusTag(status: string): 'success' | 'warning' | 'danger' | 'info' {
  if (terminalStatuses.has(status)) return 'success'
  if (status === 'blocked' || status === 'failed') return 'danger'
  if (runningStatuses.has(status)) return 'warning'
  return 'info'
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    done: '已完成', completed: '已完成', in_progress: '进行中', running: '运行中',
    review: '审查中', testing: '测试中', blocked: '阻塞', failed: '失败',
    assigned: '已分配', todo: '待办', pending: '待处理', planning: '规划中'
  }
  return labels[status] || status || '未知'
}

function jobStatusTag(status?: string): 'success' | 'warning' | 'danger' | 'info' {
  if (status === 'succeeded') return 'success'
  if (status === 'failed' || status === 'cancelled') return 'danger'
  if (status === 'running' || status === 'queued') return 'warning'
  return 'info'
}

function jobStatusLabel(status?: string) {
  const labels: Record<string, string> = {
    succeeded: '执行成功', failed: '执行失败', cancelled: '已取消', running: '执行中', queued: '排队中'
  }
  return status ? (labels[status] || status) : '未派发'
}

function agentLabel(agent?: string) {
  const labels: Record<string, string> = {
    optimus: '擎天柱', wheeljack: '千斤顶', leonardo: '李奥纳多', donatello: '多纳泰罗',
    raphael: '拉斐尔', michelangelo: '米开朗基罗', ironhide: '铁皮'
  }
  return agent ? (labels[agent] || agent) : '未分配'
}

function formatTime(value?: string | null) {
  if (!value) return '尚无执行记录'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false
  }).format(date)
}

watch(() => props.project.id, () => {
  selectedDocument.value = null
  categoryFilter.value = ''
  treeFilter.value = ''
  workspaceMode.value = 'documents'
  gitRepositories.value = []
  selectedGitRepositoryId.value = ''
  gitStatus.value = null
  gitDiff.value = null
  selectedGitPath.value = ''
  commitMessages.value = {}
  loadWorkspace()
})
onMounted(loadWorkspace)
</script>

<style scoped>
.software-workspace-panel {
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px solid var(--el-border-color);
}

.workspace-head,
.section-title-row,
.pane-title,
.repository-strip,
.workspace-stat strong,
.tree-node {
  display: flex;
  align-items: center;
}

.workspace-head,
.section-title-row,
.pane-title {
  justify-content: space-between;
  gap: 16px;
}

.workspace-head h3,
.workspace-head p {
  margin: 0;
}

.workspace-head h3 { margin-top: 3px; font-size: 17px; }
.workspace-head p { margin-top: 5px; color: var(--el-text-color-secondary); font-size: 12px; }
.workspace-eyebrow { color: var(--el-color-primary); font-size: 10px; font-weight: 700; }

.workspace-progress-grid {
  display: grid;
  grid-template-columns: 1.3fr repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin: 14px 0;
}

.workspace-stat {
  min-height: 78px;
  padding: 12px;
  border: 1px solid var(--el-border-color);
  background: var(--el-fill-color-light);
  border-radius: 6px;
}

.workspace-stat > span,
.workspace-stat small { display: block; color: var(--el-text-color-secondary); font-size: 11px; }
.workspace-stat strong { gap: 7px; margin-top: 5px; font-size: 20px; }
.workspace-stat small { margin-top: 5px; }
.progress-stat :deep(.el-progress) { margin-top: 7px; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--el-color-danger); }
.status-dot.online { background: var(--el-color-success); box-shadow: 0 0 0 3px color-mix(in srgb, var(--el-color-success) 18%, transparent); }

.repository-strip {
  gap: 18px;
  min-height: 38px;
  padding: 0 12px;
  border: 1px solid var(--el-border-color);
  border-radius: 5px;
  background: var(--el-bg-color-page);
  overflow: hidden;
}

.repository-strip > div { display: flex; align-items: center; gap: 5px; flex: none; font-size: 11px; }
.repository-strip svg { width: 13px; }
.repository-strip code { margin-left: auto; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 10px; }
.repository-strip .warning { color: var(--el-color-warning); }

.coverage-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 6px;
  margin: 10px 0;
}

.coverage-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  min-width: 0;
  height: 36px;
  padding: 0 9px;
  color: var(--el-text-color-regular);
  border: 1px solid var(--el-border-color);
  border-radius: 5px;
  background: transparent;
  cursor: pointer;
}

.coverage-item span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; }
.coverage-item strong { color: var(--el-color-primary); }
.coverage-item.active { border-color: var(--el-color-primary); background: var(--el-color-primary-light-9); }
.coverage-item.missing { opacity: .55; }

.document-browser {
  display: grid;
  grid-template-columns: minmax(250px, 30%) minmax(0, 1fr);
  height: 600px;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  overflow: hidden;
}

.document-tree-pane,
.document-preview-pane { min-width: 0; min-height: 0; background: var(--el-bg-color); }
.document-tree-pane { border-right: 1px solid var(--el-border-color); }
.pane-title { min-height: 55px; padding: 9px 12px; border-bottom: 1px solid var(--el-border-color); }
.pane-title > div:first-child { min-width: 0; }
.pane-title strong, .pane-title small { display: block; }
.pane-title small { margin-top: 3px; color: var(--el-text-color-secondary); font-size: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pane-title :deep(.el-input) { width: 118px; }
.pane-actions { display: flex; align-items: center; gap: 5px; flex: none; }
.pane-actions :deep(.el-button + .el-button) { margin-left: 0; }
.workspace-tree { height: calc(100% - 55px); padding: 8px; overflow: auto; background: transparent; }

.git-source-control { height: calc(100% - 55px); overflow: auto; background: var(--el-bg-color); }
.git-source-control :deep(.el-alert) { border-radius: 0; }
.git-repository-list { display: grid; gap: 1px; padding: 6px; border-bottom: 1px solid var(--el-border-color); background: var(--el-bg-color-page); }
.git-repository-list button { display: grid; grid-template-columns: 30px minmax(0, 1fr) auto; align-items: center; gap: 7px; min-height: 48px; padding: 6px 8px; border: 1px solid transparent; border-radius: 4px; color: var(--el-text-color-primary); text-align: left; background: transparent; cursor: pointer; }
.git-repository-list button:hover { background: var(--el-fill-color); }
.git-repository-list button.active { border-color: var(--el-color-primary); background: var(--el-color-primary-light-9); }
.git-repository-list button.unavailable { color: var(--el-color-danger); }
.repository-icon { position: relative; display: grid; place-items: center; width: 26px; height: 26px; }
.repository-icon > svg { width: 17px; color: var(--el-color-primary); }
.repository-icon > i { position: absolute; right: -4px; bottom: -3px; display: grid; place-items: center; min-width: 17px; height: 17px; padding: 0 3px; border: 2px solid var(--el-bg-color-page); border-radius: 9px; color: white; background: var(--el-color-warning); font-size: 8px; font-style: normal; }
.repository-copy { min-width: 0; }
.repository-copy strong, .repository-copy small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.repository-copy strong { font-size: 11px; }
.repository-copy small { margin-top: 3px; color: var(--el-text-color-secondary); font-size: 9px; }
.repository-sync { color: var(--el-text-color-secondary); font-size: 9px; }
.git-branch-summary { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 4px 8px; padding: 10px 12px; border-bottom: 1px solid var(--el-border-color-lighter); }
.git-branch-summary > div { display: flex; align-items: center; gap: 6px; min-width: 0; }
.git-branch-summary svg { width: 14px; color: var(--el-color-primary); }
.git-branch-summary strong, .git-branch-summary span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; }
.git-branch-summary > span { color: var(--el-text-color-secondary); text-align: right; }
.git-branch-summary small { grid-column: 1 / -1; color: var(--el-text-color-secondary); font-size: 10px; }
.commit-editor { display: grid; gap: 7px; padding: 10px 12px; border-bottom: 1px solid var(--el-border-color); }
.commit-editor :deep(.el-textarea__inner) { font-family: inherit; font-size: 11px; }
.commit-editor :deep(.el-button) { width: 100%; margin: 0; }
.change-group { border-bottom: 1px solid var(--el-border-color); }
.change-group > header, .recent-commits > header { display: flex; align-items: center; justify-content: space-between; min-height: 34px; padding: 0 8px 0 12px; color: var(--el-text-color-regular); font-size: 10px; font-weight: 700; }
.change-group > header b { display: inline-grid; place-items: center; min-width: 18px; height: 18px; margin-left: 4px; border-radius: 50%; color: var(--el-text-color-secondary); background: var(--el-fill-color); font-size: 9px; }
.change-row { display: grid; grid-template-columns: minmax(0, 1fr) 18px 25px; align-items: center; gap: 3px; min-height: 42px; padding: 4px 5px 4px 12px; border-top: 1px solid var(--el-border-color-lighter); cursor: pointer; outline: none; }
.change-row:hover, .change-row.active, .change-row:focus-visible { background: var(--el-fill-color-light); }
.change-row.active { box-shadow: inset 2px 0 var(--el-color-primary); }
.change-name { display: flex; align-items: center; gap: 7px; min-width: 0; }
.change-name > svg { flex: none; width: 13px; color: var(--el-text-color-secondary); }
.change-name > span { min-width: 0; }
.change-name strong, .change-name small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.change-name strong { font-size: 10px; font-weight: 500; }
.change-name small { margin-top: 2px; color: var(--el-text-color-secondary); font-size: 9px; }
.change-code { font-size: 10px; font-style: normal; font-weight: 700; text-align: center; }
.status-m, .status-r { color: var(--el-color-warning); }
.status-a, .status-\? { color: var(--el-color-success); }
.status-d, .status-u { color: var(--el-color-danger); }
.empty-change-group { padding: 11px 12px; border-top: 1px solid var(--el-border-color-lighter); color: var(--el-text-color-secondary); font-size: 10px; }
.recent-commits { padding-bottom: 8px; }
.recent-commits > header { justify-content: flex-start; gap: 6px; }
.recent-commits > header svg { width: 13px; }
.commit-row { display: grid; grid-template-columns: 54px minmax(0, 1fr); gap: 7px; padding: 6px 12px; }
.commit-row code { color: var(--el-color-primary); font-size: 9px; }
.commit-row span { min-width: 0; }
.commit-row strong, .commit-row small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.commit-row strong { font-size: 10px; font-weight: 500; }
.commit-row small { margin-top: 2px; color: var(--el-text-color-secondary); font-size: 9px; }

.document-preview-scroll { height: calc(100% - 55px); overflow: auto; }
.git-diff-scroll { height: calc(100% - 55px); overflow: auto; background: #101820; }
.git-diff-scroll :deep(.el-alert) { margin: 14px; width: auto; }
.diff-preview { min-width: 100%; margin: 0; padding: 8px 0 40px; color: #c5d0dc; background: #101820; font: 11px/1.55 ui-monospace, SFMono-Regular, Menlo, monospace; white-space: pre; }
.diff-preview code { display: block; width: max-content; min-width: 100%; }
.diff-preview span { display: block; min-height: 17px; padding-right: 12px; }
.diff-preview span > i { display: inline-block; width: 48px; margin-right: 10px; padding-right: 8px; color: #607080; font-style: normal; text-align: right; user-select: none; border-right: 1px solid #253342; }
.diff-preview .diff-add { color: #b9e6c6; background: rgb(46 160 67 / 18%); }
.diff-preview .diff-delete { color: #ffc1c1; background: rgb(248 81 73 / 17%); }
.diff-preview .diff-hunk { color: #8bc4ff; background: rgb(56 139 253 / 12%); }
.diff-preview .diff-meta, .diff-preview .diff-file { color: #8d9baa; }
.markdown-preview { max-width: 920px; padding: 24px 30px 60px; color: var(--el-text-color-primary); font-size: 13px; line-height: 1.75; }
.markdown-preview :deep(h1) { font-size: 24px; border-bottom: 1px solid var(--el-border-color); padding-bottom: 10px; }
.markdown-preview :deep(h2) { margin-top: 28px; font-size: 19px; }
.markdown-preview :deep(h3) { margin-top: 22px; font-size: 16px; }
.markdown-preview :deep(pre), .code-preview { padding: 14px; border: 1px solid var(--el-border-color); border-radius: 5px; background: var(--el-fill-color-light); overflow: auto; }
.markdown-preview :deep(code), .code-preview { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; }
.markdown-preview :deep(table) { width: 100%; border-collapse: collapse; }
.markdown-preview :deep(th), .markdown-preview :deep(td) { padding: 7px 9px; border: 1px solid var(--el-border-color); text-align: left; }
.markdown-preview :deep(a) { color: var(--el-color-primary); }
.code-preview { min-height: 100%; margin: 0; border: 0; border-radius: 0; white-space: pre-wrap; }
.preview-truncated { padding: 8px 14px; color: var(--el-color-warning); font-size: 11px; }

.execution-machine-section { margin-top: 14px; border: 1px solid var(--el-border-color); border-radius: 6px; overflow: hidden; }
.section-title-row { min-height: 58px; padding: 8px 12px; border-bottom: 1px solid var(--el-border-color); }
.section-title-row strong, .section-title-row small { display: block; }
.section-title-row small { margin-top: 4px; color: var(--el-text-color-secondary); font-size: 10px; }
.execution-table-wrap { overflow-x: auto; }
.execution-table { width: 100%; min-width: 880px; border-collapse: collapse; font-size: 11px; }
.execution-table th { color: var(--el-text-color-secondary); background: var(--el-fill-color-light); font-weight: 500; text-align: left; }
.execution-table th, .execution-table td { padding: 9px 11px; border-bottom: 1px solid var(--el-border-color-lighter); vertical-align: top; }
.execution-table td strong, .execution-table td small { display: block; }
.execution-table td small { margin-top: 3px; color: var(--el-text-color-secondary); }
.execution-table .job-error { max-width: 220px; color: var(--el-color-danger); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.empty-row { height: 70px; color: var(--el-text-color-secondary); text-align: center; }

@media (max-width: 1100px) {
  .workspace-progress-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .coverage-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .repository-strip { flex-wrap: wrap; padding: 8px 12px; }
  .repository-strip code { width: 100%; margin-left: 0; }
}

@media (max-width: 720px) {
  .workspace-head { align-items: flex-start; }
  .workspace-progress-grid { grid-template-columns: 1fr; }
  .coverage-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .document-browser { grid-template-columns: 1fr; height: auto; }
  .document-tree-pane { height: 330px; border-right: 0; border-bottom: 1px solid var(--el-border-color); }
  .document-preview-pane { height: 540px; }
  .markdown-preview { padding: 18px 16px 40px; }
}
</style>
