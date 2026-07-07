<template>
  <div class="projects-page">
    <el-row :gutter="18">
      <el-col :span="6">
        <el-card class="panel project-list-panel" shadow="hover">
          <template #header>
            <div class="panel-header">
              <span>{{ projectListTitle }}</span>
              <el-button size="small" type="primary" @click="loadProjects">刷新</el-button>
            </div>
          </template>

          <el-skeleton v-if="loading" :rows="8" animated />
          <div v-else class="project-list">
            <button
              v-for="project in projects"
              :key="project.id"
              class="project-card"
              :class="{ active: selectedProjectId === project.id }"
              @click="selectedProjectId = project.id"
            >
              <div class="project-card-title">{{ project.name }}</div>
              <div class="project-card-meta">
                {{ phaseLabel(project.current_phase || project.status) }} · {{ project.tasks.length }} 个任务
              </div>
              <el-progress :percentage="Math.round(project.progress || 0)" :show-text="false" />
            </button>
          </div>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-empty v-if="!selectedProject" :description="emptyProjectText" />
        <template v-else>
          <el-card class="panel" shadow="hover">
            <template #header>
              <div class="panel-header">
                <div>
                  <div class="project-title">{{ selectedProject.name }}</div>
                  <div class="muted">{{ selectedProject.description || '暂无项目描述' }}</div>
                </div>
                <el-tag :type="statusType(selectedProject.status)">{{ statusLabel(selectedProject.status) }}</el-tag>
              </div>
            </template>

            <el-row :gutter="12" class="metric-row">
              <el-col :span="6">
                <div class="metric">
                  <span>总进度</span>
                  <strong>{{ Math.round(selectedProject.progress || 0) }}%</strong>
                </div>
              </el-col>
              <el-col :span="6">
                <div class="metric">
                  <span>并行任务</span>
                  <strong>{{ selectedProject.tasks.length }}</strong>
                </div>
              </el-col>
              <el-col :span="6">
                <div class="metric">
                  <span>{{ pointLabel }}</span>
                  <strong>{{ totalPoints }}</strong>
                </div>
              </el-col>
              <el-col :span="6">
                <div class="metric">
                  <span>负责人</span>
                  <strong>{{ selectedProject.owner_agent || '未分配' }}</strong>
                </div>
              </el-col>
            </el-row>

            <el-divider />

            <div v-if="isDocumentProject" class="document-workspace">
              <div class="document-summary-grid">
                <div class="document-summary-item">
                  <span>文档类型</span>
                  <strong>{{ selectedProject.document_spec?.document_type || '未设置' }}</strong>
                </div>
                <div class="document-summary-item">
                  <span>写作目标</span>
                  <strong>{{ selectedProject.document_spec?.writing_goal || '暂无' }}</strong>
                </div>
                <div class="document-summary-item">
                  <span>目标读者</span>
                  <strong>{{ selectedProject.document_spec?.target_audience || '暂无' }}</strong>
                </div>
                <div class="document-summary-item">
                  <span>输出格式</span>
                  <strong>{{ selectedProject.document_spec?.output_format || 'Markdown / Word / PDF' }}</strong>
                </div>
              </div>

              <section class="document-section">
                <div class="document-section-head">
                  <div>
                    <h3>文档目录与章节计划</h3>
                    <p class="muted">按章节组织写作目标、主要内容、关键论点和负责智能体。</p>
                  </div>
                  <el-tag>{{ documentSections.length }} 章</el-tag>
                </div>
                <el-empty v-if="documentSections.length === 0" description="暂无目录结构" :image-size="56" />
                <div v-else class="document-section-list">
                  <article v-for="section in documentSections" :key="section.id || section.title" class="document-section-card">
                    <div class="document-card-head">
                      <strong>{{ section.title }}</strong>
                      <el-tag size="small" :type="statusType(section.status || 'planning')">
                        {{ statusLabel(section.status || 'planning') }}
                      </el-tag>
                    </div>
                    <p class="muted">{{ section.summary || section.main_content || section.content_brief || '暂无章节说明' }}</p>
                    <div v-if="section.key_points?.length" class="doc-tags">
                      <el-tag v-for="point in section.key_points" :key="point" size="small" type="info">{{ point }}</el-tag>
                    </div>
                    <div class="document-card-foot">
                      <span>负责智能体：{{ agentLabel(section.assigned_agent) }}</span>
                    </div>
                  </article>
                </div>
              </section>

              <section class="document-section">
                <div class="document-section-head">
                  <div>
                    <h3>图片/图表计划</h3>
                    <p class="muted">集中管理每章需要的图片、图表、表格和示意图。</p>
                  </div>
                  <el-tag>{{ documentAssets.length }} 个</el-tag>
                </div>
                <el-empty v-if="documentAssets.length === 0" description="暂无图片/图表计划" :image-size="56" />
                <div v-else class="document-asset-list">
                  <div v-for="asset in documentAssets" :key="asset.id || asset.title" class="document-asset-card">
                    <div>
                      <strong>{{ asset.title }}</strong>
                      <p class="muted">{{ asset.description || '暂无说明' }}</p>
                    </div>
                    <div class="document-asset-meta">
                      <el-tag size="small" type="info">{{ assetTypeLabel(asset.type) }}</el-tag>
                      <el-tag size="small" :type="statusType(asset.status || 'planning')">
                        {{ statusLabel(asset.status || 'planning') }}
                      </el-tag>
                      <span>{{ asset.chapter_title || '未绑定章节' }}</span>
                    </div>
                  </div>
                </div>
              </section>
            </div>

            <div v-else class="doc-grid">
              <div>
                <h3>使用需求</h3>
                <el-empty v-if="usageRequirements.length === 0" description="暂无使用需求" :image-size="56" />
                <ul v-else class="clean-list">
                  <li v-for="item in usageRequirements" :key="item">{{ item }}</li>
                </ul>
              </div>
              <div>
                <h3>设计文档</h3>
                <p class="muted">{{ selectedProject.design_doc?.summary || '暂无设计摘要' }}</p>
                <div class="doc-tags">
                  <el-tag type="info">数据结构</el-tag>
                  <el-tag type="info">系统架构</el-tag>
                  <el-tag type="info">系统功能</el-tag>
                  <el-tag type="info">API 接口</el-tag>
                </div>
              </div>
            </div>
          </el-card>

          <el-card class="panel tasks-panel" shadow="hover">
            <template #header>
              <div class="panel-header">
                <span>{{ isDocumentProject ? '并行写作任务' : 'Loop 自主迭代开发' }}</span>
                <div class="panel-header-actions">
                  <el-tag>{{ selectedProject.tasks.length }} 个任务</el-tag>
                  <el-tag type="success">{{ executablePointCount }} 个待执行子项</el-tag>
                  <el-tag v-if="!isDocumentProject" type="warning">{{ loopActiveCount }} 个 Codex 执行中</el-tag>
                  <el-button
                    size="small"
                    type="primary"
                    :loading="autoDispatchingProject"
                    @click="autoDispatchProject"
                  >
                    启动项目 Loop
                  </el-button>
                  <el-button size="small" :loading="loadingCodexJobs" @click="loadCodexJobs">刷新反馈</el-button>
                </div>
              </div>
            </template>

            <div class="task-list">
              <div v-for="task in selectedProject.tasks" :key="task.id" class="task-card">
                <div class="task-main">
                  <div>
                    <div class="task-title">{{ task.title }}</div>
                    <div class="muted">{{ task.description || '暂无任务描述' }}</div>
                  </div>
                  <div class="task-status">
                    <el-tag :type="statusType(task.status)" size="small">{{ statusLabel(task.status) }}</el-tag>
                    <span>{{ Math.round(task.progress || 0) }}%</span>
                  </div>
                </div>
                <el-progress :percentage="Math.round(task.progress || 0)" :color="progressColor" />
                <div class="execution-list">
                <div class="execution-list-head">
                  <strong>{{ isDocumentProject ? '执行子项看板' : 'Loop 执行子项' }}</strong>
                  <small>每个{{ pointLabel }}单独交给{{ isDocumentProject ? '文档协作智能体' : '忍者神龟开发组' }}，通过 Codex 执行、反馈、验证并进入下一轮</small>
                </div>
                  <div v-if="task.development_points.length === 0" class="muted">暂无可执行子项</div>
                  <div v-for="point in task.development_points" :key="point.id" class="execution-row">
                    <div class="execution-main">
                      <el-tag :type="statusType(point.status)" size="small">{{ statusLabel(point.status) }}</el-tag>
                      <div class="execution-copy">
                        <span>{{ point.title }}</span>
                        <small>执行智能体：{{ agentLabel(pointAgent(task, point)) }}</small>
                      </div>
                    </div>
                    <div class="execution-state">
                      <el-tag size="small" :type="codexStatusType(latestJobForPoint(point.id)?.status)">
                        {{ latestJobForPoint(point.id) ? codexStatusLabel(latestJobForPoint(point.id)!.status) : '未启动' }}
                      </el-tag>
                      <el-tag v-if="latestLoopForPoint(point.id)" size="small" type="warning">
                        协同 {{ loopStageLabel(latestLoopForPoint(point.id)!.current_stage) }}
                      </el-tag>
                      <span>{{ latestCodexFeedback(point.id) }}</span>
                    </div>
                    <div class="execution-actions">
                      <el-button
                        size="small"
                        :loading="creatingPointIds.has(point.id)"
                        :disabled="!isExecutablePoint(point) || hasActiveJob(point.id)"
                        @click="startPointCodexJob(task, point)"
                      >
                        {{ isExecutablePoint(point) ? '执行子项' : '已完成' }}
                      </el-button>
                      <el-button
                        size="small"
                        type="primary"
                        :loading="creatingLoopIds.has(point.id)"
                        :disabled="!isExecutablePoint(point) || hasActiveLoop(point.id)"
                        @click="startCollaborativePointLoop(task, point)"
                      >
                        协同 Loop
                      </el-button>
                      <el-button
                        v-if="latestJobForPoint(point.id)"
                        size="small"
                        @click="selectCodexJob(latestJobForPoint(point.id)!)"
                      >
                        查看反馈
                      </el-button>
                    </div>
                  </div>
                </div>
                <div class="codex-task-panel">
                  <div class="codex-task-head">
                    <div>
                      <strong>{{ isDocumentProject ? '任务派发控制' : 'Loop 迭代控制' }}</strong>
                      <small>{{ isDocumentProject ? '项目经理可一键派发本任务全部未完成子项，也可保留整任务指令' : '按开发要点自动创建 Codex Job，多轮读代码、修改、验证、反馈' }}</small>
                    </div>
                    <el-select v-model="taskCodexAgents[task.id]" size="small" style="width: 138px">
                      <el-option label="擎天柱" value="optimus" />
                      <el-option label="通天晓" value="ultra-magnus" />
                      <el-option label="千斤顶" value="wheeljack" />
                      <el-option label="救护车" value="ratchet" />
                      <el-option label="感知器" value="perceptor" />
                      <el-option label="李奥纳多" value="leonardo" />
                      <el-option label="多纳泰罗" value="donatello" />
                      <el-option label="拉斐尔" value="raphael" />
                      <el-option label="米开朗基罗" value="michelangelo" />
                    </el-select>
                  </div>
                  <el-input
                    v-model="taskCodexInstructions[task.id]"
                    type="textarea"
                    :rows="2"
                    resize="none"
                    :placeholder="defaultCodexInstruction(task)"
                  />
                  <div class="codex-task-actions">
                    <el-button
                      size="small"
                      type="primary"
                      :loading="creatingLoopIds.has(task.id)"
                      :disabled="hasActiveLoop(task.id)"
                      @click="startCollaborativeTaskLoop(task)"
                    >
                      启动协同 Loop
                    </el-button>
                    <el-button
                      size="small"
                      :loading="creatingTaskIds.has(task.id)"
                      @click="autoDispatchTask(task)"
                    >
                      启动任务 Loop
                    </el-button>
                    <el-button
                      size="small"
                      :loading="creatingTaskIds.has(task.id)"
                      @click="startProjectCodexJob(task)"
                    >
                      整任务迭代
                    </el-button>
                    <el-button size="small" :loading="loadingCodexJobs" @click="loadCodexJobs">刷新反馈</el-button>
                  </div>
                  <div v-if="jobsForTask(task.id).length" class="codex-job-list">
                    <button v-for="job in jobsForTask(task.id)" :key="job.id" class="codex-job" @click="selectCodexJob(job)">
                      <span>{{ agentLabel(job.agent_id) }} · {{ codexStatusLabel(job.status) }}</span>
                      <small>{{ formatTime(job.created_at) }} · {{ job.error || job.summary || job.instruction }}</small>
                    </button>
                  </div>
                  <div v-if="loopsForTask(task.id).length" class="codex-job-list">
                    <button v-for="loop in loopsForTask(task.id)" :key="loop.id" class="codex-job">
                      <span>{{ loop.title }} · {{ loopStatusLabel(loop.status) }}</span>
                      <small>
                        第 {{ loop.current_round || 0 }} / {{ loop.max_rounds }} 轮 ·
                        {{ loopStageLabel(loop.current_stage) }} ·
                        方案 {{ agentLabel(loop.planner_agent_id) }} → 开发 {{ agentLabel(loop.developer_agent_id) }} → 评估 {{ agentLabel(loop.evaluator_agent_id) }}
                      </small>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </el-card>
        </template>
      </el-col>

      <el-col :span="6">
        <aside v-if="selectedProject" class="right-rail">
          <el-card class="panel manager-panel" shadow="hover">
            <template #header>
              <div class="panel-header">
                <span>项目经理面板</span>
                <el-tag size="small" type="info">{{ managerAgent }}</el-tag>
              </div>
            </template>

            <div class="manager-section">
              <div class="section-title">下一步建议</div>
              <div v-if="managerSuggestions.length" class="suggestion-list">
                <div v-for="(item, index) in managerSuggestions.slice(0, 5)" :key="index" class="suggestion-item">
                  {{ suggestionText(item) }}
                </div>
              </div>
              <div v-else class="muted">暂无建议</div>
            </div>

            <div class="manager-section">
              <div class="section-title">未完成{{ pointLabel }}</div>
              <div v-if="openPoints.length" class="compact-list">
                <div v-for="point in openPoints.slice(0, 6)" :key="point.id || point.title">
                  {{ point.task_title ? point.task_title + ' / ' : '' }}{{ point.title }}
                </div>
              </div>
              <div v-else class="muted">暂无</div>
            </div>

            <div class="manager-section">
              <div class="section-title">智能体工作状态</div>
              <div v-if="activeAgents.length" class="agent-work-list">
                <div v-for="agent in activeAgents" :key="agent.id" class="agent-work-row">
                  <el-tag size="small" :type="agent.busy ? 'warning' : 'info'">{{ agent.busy ? '项目中' : '空闲' }}</el-tag>
                  <span>{{ agent.name }} · {{ agent.work || '待分配' }}</span>
                </div>
              </div>
              <div v-else class="muted">暂无</div>
            </div>
          </el-card>

          <el-card class="panel chat-panel" shadow="hover">
            <template #header>
              <div class="panel-header">
                <span>项目智能体对话</span>
                <el-select v-model="chatAgent" size="small" class="agent-select">
                  <el-option label="擎天柱" value="optimus" />
                  <el-option label="通天晓" value="ultra-magnus" />
                  <el-option label="千斤顶" value="wheeljack" />
                  <el-option label="救护车" value="ratchet" />
                  <el-option label="感知器" value="perceptor" />
                </el-select>
              </div>
            </template>

            <div class="chat-context muted">
              {{ isDocumentProject ? `文档上下文：${documentSections.length} 章，${documentAssets.length} 个图片/图表计划` : `开发上下文：${selectedProject.tasks.length} 个任务，${totalPoints} 个${pointLabel}` }}
            </div>
            <div v-if="chatMessages.length" class="chat-history">
              <div v-for="message in chatMessages.slice(-3)" :key="message.id || message.created_at || message.message" class="chat-message">
                <strong>{{ message.agent_id || message.role || 'system' }}</strong>
                <span>{{ message.message || message.content }}</span>
              </div>
            </div>
            <el-input
              v-model="chatText"
              type="textarea"
              :rows="4"
              resize="none"
              :placeholder="isDocumentProject ? '例如：让通天晓细化第三章目录，并补充图片建议' : '例如：让拉斐尔实现接口，让多纳泰罗补前端页面'"
            />
            <div class="chat-actions">
              <el-button size="small" :loading="chatLoading" @click="generateTaskFromChat">生成任务</el-button>
              <el-button size="small" type="primary" :loading="chatLoading" @click="sendChat">发送到项目上下文</el-button>
            </div>
          </el-card>

          <el-card class="panel project-links-panel" shadow="hover">
            <el-collapse v-model="rightPanelSections">
              <el-collapse-item :title="isDocumentProject ? '文档结构' : '设计文档'" name="docs">
                <div v-if="isDocumentProject" class="compact-list">
                  <div v-for="section in documentSections.slice(0, 8)" :key="section.id || section.title">
                    {{ section.title }} · {{ section.status || 'planning' }}
                  </div>
                  <div v-if="documentSections.length === 0" class="muted">暂无目录结构</div>
                </div>
                <div v-else class="compact-list">
                  <div>摘要：{{ selectedProject.design_doc?.summary || '暂无' }}</div>
                  <div>使用需求：{{ usageRequirements.length }} 条</div>
                  <div>任务：{{ selectedProject.tasks.length }} 个</div>
                </div>
              </el-collapse-item>
              <el-collapse-item title="知识上下文" name="knowledge">
                <div class="compact-list">
                  <div v-if="isDocumentProject">引用资料、章节材料、图片/图表计划将作为写作上下文。</div>
                  <div v-else>设计文档、任务、开发要点将作为开发上下文。</div>
                </div>
              </el-collapse-item>
              <el-collapse-item title="最近日志" name="logs">
                <div v-if="chatMessages.length" class="compact-list">
                  <div v-for="message in chatMessages.slice(-5)" :key="message.id || message.created_at || message.message">
                    {{ message.agent_id || message.role || 'system' }}：{{ message.message || message.content }}
                  </div>
                </div>
                <div v-else class="muted">暂无最近日志</div>
              </el-collapse-item>
              <el-collapse-item title="参考仓库" name="repos">
                <div class="repo-list">
                  <div v-for="repo in projectRepos" :key="repo.url" class="repo-item">
                    <div class="repo-item-main">
                      <a :href="repo.url" target="_blank" rel="noopener" class="repo-link">{{ repo.repo }}</a>
                      <span class="repo-desc">{{ repo.desc }}</span>
                    </div>
                    <el-tag size="small" :type="repoTypeTag(repo.tags)">{{ repo.tags?.join(' / ') || '参考' }}</el-tag>
                  </div>
                </div>
              </el-collapse-item>
            </el-collapse>
          </el-card>
        </aside>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createProjectAgentAction,
  getProjectChatContext,
  getProjectConversation,
  getProjects,
  sendProjectChat,
  type DevelopmentPoint,
  type Project,
  type ProjectChatContext,
  type ProjectChatMessage,
  type ProjectTask
} from '@/api/projects'
import {
  createCodexJob,
  createCodexLoop,
  getCodexJobLogs,
  listCodexJobs,
  listCodexLoops,
  type CodexJob,
  type CodexJobStatus,
  type CodexLoop
} from '@/api/codex'

const route = useRoute()
const loading = ref(false)
const loadingCodexJobs = ref(false)
const loadingCodexLoops = ref(false)
const projects = ref<Project[]>([])
const selectedProjectId = ref('')
const codexJobs = ref<CodexJob[]>([])
const codexLoops = ref<CodexLoop[]>([])
const projectContext = ref<ProjectChatContext | null>(null)
const chatMessages = ref<ProjectChatMessage[]>([])
const chatText = ref('')
const chatAgent = ref('optimus')
const workspaceProjectType = computed(() => route.meta.workspaceMode === 'writing' ? 'document' : 'software')
const isWritingWorkspace = computed(() => workspaceProjectType.value === 'document')
const projectListTitle = computed(() => isWritingWorkspace.value ? '文档项目' : '开发项目')
const emptyProjectText = computed(() => isWritingWorkspace.value ? '暂无文档项目' : '暂无开发项目')

// ---- 参考仓库数据 ----
const ALL_REPOS: { url: string; repo: string; desc: string; tags: string[] }[] = [
  { url: 'https://github.com/openclaw/openclaw', repo: 'openclaw/openclaw', desc: 'OpenClaw 官方源码', tags: ['平台'] },
  { url: 'https://github.com/ruvnet/ruflo', repo: 'ruvnet/ruflo', desc: 'Agent meta-harness，本次调研的主题', tags: ['Agent', '框架'] },
  { url: 'https://github.com/ruvnet/RuVector', repo: 'ruvnet/RuVector', desc: '向量数据库 + 嵌入检索引擎，Ruflo 底层智能层', tags: ['向量', '检索'] },
  { url: 'https://github.com/ruvnet/claude-flow', repo: 'ruvnet/claude-flow', desc: 'Ruflo 前身（已更名）', tags: ['Agent', '历史'] },
  { url: 'https://github.com/msitarzewski/agency-agents', repo: 'msitarzewski/agency-agents', desc: '多 Agent 协作框架', tags: ['Agent', '协作'] },
  { url: 'https://github.com/msitarzewski/agency-agents-app', repo: 'msitarzewski/agency-agents-app', desc: 'agency-agents 的配套应用', tags: ['Agent', '应用'] },
  { url: 'https://github.com/666ghj/MiroFish', repo: '666ghj/MiroFish', desc: '仿真框架', tags: ['仿真'] },
  { url: 'https://github.com/yuanye126/MiroFish', repo: 'yuanye126/MiroFish', desc: 'MiroFish fork 版本', tags: ['仿真'] },
  { url: 'https://github.com/camel-ai/oasis', repo: 'camel-ai/oasis', desc: 'CAMEL-AI 团队的 Oasis 多 Agent 平台', tags: ['Agent', '仿真'] },
  { url: 'https://github.com/anomalyco/opencode', repo: 'anomalyco/opencode', desc: '开源代码编辑器/IDE 相关', tags: ['工具'] },
]

const REPO_MAP: Record<string, string[]> = {
  '看板 V2': ['openclaw/openclaw', 'ruvnet/ruflo', 'ruvnet/RuVector', 'ruvnet/claude-flow', 'msitarzewski/agency-agents', 'msitarzewski/agency-agents-app'],
  'one-sim 仿真': ['ruvnet/ruflo', 'ruvnet/RuVector', 'ruvnet/claude-flow', '666ghj/MiroFish', 'yuanye126/MiroFish', 'camel-ai/oasis', 'msitarzewski/agency-agents', 'msitarzewski/agency-agents-app', 'anomalyco/opencode', 'openclaw/openclaw'],
  '博士论文': ['ruvnet/ruflo', 'ruvnet/RuVector', 'ruvnet/claude-flow', 'msitarzewski/agency-agents', 'msitarzewski/agency-agents-app', 'camel-ai/oasis', '666ghj/MiroFish', 'yuanye126/MiroFish', 'anomalyco/opencode', 'openclaw/openclaw'],
}

const projectRepos = computed(() => {
  const p = selectedProject.value
  if (!p) return []
  const keys = REPO_MAP[p.name] || Object.values(REPO_MAP).flat()
  const deduped = new Set(keys)
  return ALL_REPOS.filter(r => deduped.has(r.repo))
})

function repoTypeTag(tags?: string[]): 'primary' | 'success' | 'info' | 'warning' {
  if (!tags || tags.length === 0) return 'info'
  if (tags.includes('平台') || tags.includes('仿真')) return 'success'
  if (tags.includes('Agent') || tags.includes('框架')) return 'primary'
  return 'info'
}
const chatLoading = ref(false)
const rightPanelSections = ref(['docs', 'repos'])
const taskCodexAgents = reactive<Record<string, string>>({})
const taskCodexInstructions = reactive<Record<string, string>>({})
const creatingTaskIds = ref(new Set<string>())
const creatingPointIds = ref(new Set<string>())
const creatingLoopIds = ref(new Set<string>())
const autoDispatchingProject = ref(false)
let codexRefreshTimer: number | undefined

const selectedProject = computed(() => projects.value.find(project => project.id === selectedProjectId.value) || projects.value[0])
const isDocumentProject = computed(() => projectTypeValue(selectedProject.value) === 'document')
const pointLabel = computed(() => isDocumentProject.value ? '写作要点' : '开发要点')
const totalPoints = computed(() => selectedProject.value?.tasks.reduce((sum, task) => sum + (task.development_points?.length || 0), 0) || 0)
const executablePointCount = computed(() => (selectedProject.value?.tasks || []).reduce(
  (sum, task) => sum + (task.development_points || []).filter(point => isExecutablePoint(point) && !hasActiveJob(point.id)).length,
  0
))
const loopActiveCount = computed(() =>
  codexJobs.value.filter(job => ['queued', 'running'].includes(job.status)).length +
  codexLoops.value.filter(loop => ['queued', 'running'].includes(loop.status)).length
)
const usageRequirements = computed(() => {
  const items = selectedProject.value?.design_doc?.usage_requirements || []
  return items.map(item => typeof item === 'string' ? item : JSON.stringify(item))
})
const documentSections = computed(() => selectedProject.value?.document_spec?.chapters || [])
const documentAssets = computed(() => selectedProject.value?.document_spec?.assets || [])
const openPoints = computed(() => {
  const fromContext = projectContext.value?.open_points || []
  if (fromContext.length) return fromContext
  return (selectedProject.value?.tasks || []).flatMap(task =>
    (task.development_points || [])
      .filter(point => isExecutablePoint(point))
      .map(point => ({ ...point, task_title: task.title }))
  )
})
const managerAgent = computed(() => selectedProject.value?.project_manager_agent || selectedProject.value?.owner_agent || (isDocumentProject.value ? 'ultra-magnus' : 'optimus'))
const managerSuggestions = computed(() => {
  const suggestions = projectContext.value?.suggested_next_actions || []
  if (suggestions.length) return suggestions
  if (isDocumentProject.value) {
    return [
      '梳理总体目录结构，形成可执行的章节写作路线',
      '补充各章节主要内容、关键论点和图片/图表计划',
      '把引用资料绑定到章节或写作任务'
    ]
  }
  return [
    '根据设计文档拆分开发任务',
    '指派后端、前端、测试智能体并行推进',
    '把接口、数据结构和验收标准写入开发要点'
  ]
})
const activeAgents = computed(() => {
  const map = new Map<string, { id: string; name: string; busy: boolean; work: string }>()
  for (const job of codexJobs.value) {
    if (!['queued', 'running'].includes(job.status)) continue
    const work = executionLabel(job.task_id) || job.instruction.slice(0, 36)
    map.set(job.agent_id, { id: job.agent_id, name: agentLabel(job.agent_id), busy: true, work })
  }
  for (const task of selectedProject.value?.tasks || []) {
    const id = task.assignee_agent_id || task.assignee_agent || ''
    if (!id || map.has(id)) continue
    map.set(id, { id, name: agentLabel(id), busy: !['done', 'completed'].includes(task.status), work: task.title })
  }
  return Array.from(map.values()).slice(0, 6)
})

function projectTypeValue(project?: Project): 'software' | 'document' {
  const value = String(project?.project_type || project?.type || 'software').toLowerCase()
  return value === 'document' ? 'document' : 'software'
}

function suggestionText(item: { action?: string; reason?: string } | string): string {
  if (typeof item === 'string') return item
  return [item.action, item.reason].filter(Boolean).join(' · ') || '暂无建议'
}

function jobsForTask(taskId: string) {
  return codexJobs.value
    .filter(job => job.task_id === taskId)
    .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))
    .slice(0, 3)
}

function jobsForPoint(pointId: string) {
  return codexJobs.value
    .filter(job => job.task_id === pointId)
    .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))
}

function loopsForTask(taskId: string) {
  return codexLoops.value
    .filter(loop => loop.task_id === taskId)
    .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))
    .slice(0, 3)
}

function loopsForPoint(pointId: string) {
  return codexLoops.value
    .filter(loop => loop.task_id === pointId)
    .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))
}

function executionLabel(id?: string) {
  if (!id) return ''
  for (const task of selectedProject.value?.tasks || []) {
    if (task.id === id) return task.title
    const point = (task.development_points || []).find(item => item.id === id)
    if (point) return `${task.title} / ${point.title}`
  }
  return ''
}

function latestJobForPoint(pointId: string) {
  return jobsForPoint(pointId)[0]
}

function latestLoopForPoint(pointId: string) {
  return loopsForPoint(pointId)[0]
}

function latestCodexFeedback(pointId: string) {
  const job = latestJobForPoint(pointId)
  if (!job) return '等待项目经理派发'
  if (job.error) return job.error
  if (job.summary) return job.summary
  if (job.status === 'queued') return '已进入 Codex 队列'
  if (job.status === 'running') return 'Codex 正在执行'
  return job.instruction
}

function isExecutablePoint(point: DevelopmentPoint) {
  return !['done', 'completed', 'succeeded', 'cancelled'].includes(String(point.status || '').toLowerCase())
}

function hasActiveJob(pointId: string) {
  return jobsForPoint(pointId).some(job => ['queued', 'running'].includes(job.status))
}

function hasActiveLoop(taskId: string) {
  return codexLoops.value.some(loop => loop.task_id === taskId && ['queued', 'running'].includes(loop.status))
}

function defaultCodexAgent(task: ProjectTask) {
  return defaultCodexAgentForProject(task, selectedProject.value)
}

function defaultCodexAgentForProject(task: ProjectTask, project?: Project) {
  const text = `${task.title} ${task.description || ''} ${task.development_points.map(point => point.title).join(' ')}`
  if (projectTypeValue(project) === 'document') {
    if (/资料|引用|调研|文献|research|reference/i.test(text)) return 'ratchet'
    if (/架构|方案|系统建模|流程|architecture|model/i.test(text)) return 'wheeljack'
    if (/图片|图表|资讯|案例|情报|image|chart|diagram/i.test(text)) return 'perceptor'
    return 'ultra-magnus'
  }
  if (/测试|验收|验证|test|spec/i.test(text)) return 'michelangelo'
  if (/后端|接口|API|数据库|服务|router|python/i.test(text)) return 'raphael'
  if (/前端|页面|组件|样式|UI|Vue/i.test(text)) return 'donatello'
  return 'leonardo'
}

function pointAgent(task: ProjectTask, point: DevelopmentPoint) {
  const direct = point.assigned_agent || task.assignee_agent || task.assignee_agent_id || ''
  if (['leonardo', 'donatello', 'raphael', 'michelangelo', 'ultra-magnus', 'ratchet', 'perceptor', 'optimus', 'wheeljack'].includes(direct)) return direct
  const text = `${task.title} ${task.description || ''} ${point.title}`
  if (isDocumentProject.value) {
    if (/资料|引用|调研|文献|reference|research/i.test(text)) return 'ratchet'
    if (/架构|方案|系统建模|流程|architecture|model/i.test(text)) return 'wheeljack'
    if (/图片|图表|表格|案例|情报|image|chart|diagram/i.test(text)) return 'perceptor'
    return 'ultra-magnus'
  }
  if (/测试|验收|验证|test|spec|e2e/i.test(text)) return 'michelangelo'
  if (/后端|接口|API|数据库|服务|router|python|权限|数据/i.test(text)) return 'raphael'
  if (/前端|页面|组件|样式|UI|Vue|交互|看板/i.test(text)) return 'donatello'
  return 'leonardo'
}

function plannerAgent(task: ProjectTask, point?: DevelopmentPoint) {
  const text = `${task.title} ${task.description || ''} ${point?.title || ''}`
  if (/架构|方案|系统|数据结构|接口设计|architecture|design/i.test(text)) return 'wheeljack'
  return 'leonardo'
}

function defaultCodexInstruction(task: ProjectTask) {
  const project = selectedProject.value
  const points = task.development_points.map(point => `- ${point.title}（${statusLabel(point.status)}）`).join('\n')
  const documentProject = isDocumentProject.value
  return [
    `项目：${project?.name || '未命名项目'}`,
    `任务：${task.title}`,
    `说明：${task.description || '暂无'}`,
    points ? `${documentProject ? '写作要点' : '开发要点'}：\n${points}` : '',
    documentProject
      ? '请阅读当前文档结构、章节目标和引用材料，完成最小必要写作或资料整理，最后反馈更新内容、引用/图表建议和待审校风险。'
      : '请按 Loop 开发执行：阅读相关代码 -> 定位最小闭环 -> 修改实现 -> 运行构建/测试验证 -> 如失败继续修正一轮 -> 最后反馈改动文件、验证结果和风险。'
  ].filter(Boolean).join('\n')
}

function defaultPointCodexInstruction(task: ProjectTask, point: DevelopmentPoint) {
  const project = selectedProject.value
  if (isDocumentProject.value) {
    return [
      `项目：${project?.name || '未命名项目'}`,
      `父任务：${task.title}`,
      `写作子项：${point.title}`,
      `当前状态：${statusLabel(point.status)}`,
      `任务说明：${task.description || '暂无'}`,
      '执行要求：',
      '- 先阅读当前文档结构、章节目标和已有上下文。',
      '- 完成该写作要点所需的章节内容、资料整理、审校意见或图表建议。',
      '- 不要改动无关章节或无关项目内容。',
      '- 最后反馈：更新内容、引用/图表建议、完成情况、待审校风险。'
    ].join('\n')
  }
  return [
    `项目：${project?.name || '未命名项目'}`,
    `父任务：${task.title}`,
    `子项：${point.title}`,
    `当前状态：${statusLabel(point.status)}`,
    `任务说明：${task.description || '暂无'}`,
    '执行要求：',
    '- 先阅读相关代码和接口，不要做无关重构。',
    '- 完成该子项所需的最小代码修改。',
    '- 按 Loop 开发执行：实现后立即运行最贴近该子项的构建或测试命令。',
    '- 如果验证失败，基于错误继续修正一轮；仍失败则保留失败原因和下一步建议。',
    '- 最后反馈：改动文件、完成情况、验证结果、遗留风险。'
  ].join('\n')
}

async function loadCodexJobs() {
  loadingCodexJobs.value = true
  try {
    const res = await listCodexJobs()
    codexJobs.value = res.jobs || []
  } catch {
    codexJobs.value = []
  } finally {
    loadingCodexJobs.value = false
  }
}

async function loadCodexLoops() {
  loadingCodexLoops.value = true
  try {
    const res = await listCodexLoops()
    codexLoops.value = res.loops || []
  } catch {
    codexLoops.value = []
  } finally {
    loadingCodexLoops.value = false
  }
}

function startCodexLoopPolling() {
  stopCodexLoopPolling()
  codexRefreshTimer = window.setInterval(() => {
    if (loopActiveCount.value > 0) {
      loadCodexJobs()
      loadCodexLoops()
    }
  }, 5000)
}

async function startCollaborativeTaskLoop(task: ProjectTask) {
  if (hasActiveLoop(task.id)) {
    ElMessage.warning('该任务已有执行中的协同 Loop')
    return
  }
  const next = new Set(creatingLoopIds.value)
  next.add(task.id)
  creatingLoopIds.value = next
  try {
    await createCodexLoop({
      task_id: task.id,
      title: task.title,
      instruction: taskCodexInstructions[task.id]?.trim() || defaultCodexInstruction(task),
      developer_agent_id: taskCodexAgents[task.id] || task.assignee_agent || defaultCodexAgent(task),
      planner_agent_id: plannerAgent(task),
      evaluator_agent_id: 'michelangelo',
      max_rounds: 2
    })
    taskCodexInstructions[task.id] = ''
    ElMessage.success('已启动角色协同型 Loop：方案 → 开发 → 评估')
    await Promise.all([loadCodexJobs(), loadCodexLoops()])
  } catch {
    ElMessage.error('协同 Loop 启动失败')
  } finally {
    const done = new Set(creatingLoopIds.value)
    done.delete(task.id)
    creatingLoopIds.value = done
  }
}

async function startCollaborativePointLoop(task: ProjectTask, point: DevelopmentPoint) {
  if (hasActiveLoop(point.id)) {
    ElMessage.warning('该子项已有执行中的协同 Loop')
    return
  }
  const next = new Set(creatingLoopIds.value)
  next.add(point.id)
  creatingLoopIds.value = next
  try {
    await createCodexLoop({
      task_id: point.id,
      title: `${task.title} / ${point.title}`,
      instruction: defaultPointCodexInstruction(task, point),
      developer_agent_id: pointAgent(task, point),
      planner_agent_id: plannerAgent(task, point),
      evaluator_agent_id: 'michelangelo',
      max_rounds: 2
    })
    ElMessage.success('已启动子项协同 Loop')
    await Promise.all([loadCodexJobs(), loadCodexLoops()])
  } catch {
    ElMessage.error('子项协同 Loop 启动失败')
  } finally {
    const done = new Set(creatingLoopIds.value)
    done.delete(point.id)
    creatingLoopIds.value = done
  }
}

function stopCodexLoopPolling() {
  if (codexRefreshTimer) {
    window.clearInterval(codexRefreshTimer)
    codexRefreshTimer = undefined
  }
}

async function startProjectCodexJob(task: ProjectTask) {
  const agentId = taskCodexAgents[task.id] || task.assignee_agent || defaultCodexAgent(task)
  const instruction = taskCodexInstructions[task.id]?.trim() || defaultCodexInstruction(task)
  const next = new Set(creatingTaskIds.value)
  next.add(task.id)
  creatingTaskIds.value = next
  try {
    await createCodexJob({
      agent_id: agentId,
      task_id: task.id,
      instruction
    })
    taskCodexAgents[task.id] = agentId
    taskCodexInstructions[task.id] = ''
    ElMessage.success(`已交给 ${agentLabel(agentId)} 启动 Codex 迭代`)
    await loadCodexJobs()
  } catch {
    ElMessage.error('Codex 任务创建失败')
  } finally {
    const done = new Set(creatingTaskIds.value)
    done.delete(task.id)
    creatingTaskIds.value = done
  }
}

async function dispatchPointCodexJob(task: ProjectTask, point: DevelopmentPoint, notify = true) {
  const agentId = pointAgent(task, point)
  const next = new Set(creatingPointIds.value)
  next.add(point.id)
  creatingPointIds.value = next
  try {
    await createCodexJob({
      agent_id: agentId,
      task_id: point.id,
      instruction: defaultPointCodexInstruction(task, point)
    })
    if (notify) ElMessage.success(`已交给 ${agentLabel(agentId)} 迭代：${point.title}`)
  } finally {
    const done = new Set(creatingPointIds.value)
    done.delete(point.id)
    creatingPointIds.value = done
  }
}

async function startPointCodexJob(task: ProjectTask, point: DevelopmentPoint) {
  if (hasActiveJob(point.id)) {
    ElMessage.warning('该子项已有排队或执行中的 Codex 迭代')
    return
  }
  try {
    await dispatchPointCodexJob(task, point)
    await loadCodexJobs()
  } catch {
    ElMessage.error('子项派发失败')
  }
}

async function autoDispatchTask(task: ProjectTask) {
  const candidates = (task.development_points || []).filter(point => isExecutablePoint(point) && !hasActiveJob(point.id))
  if (!candidates.length) {
    ElMessage.info('该任务暂无需要启动 Loop 的子项')
    return
  }
  const next = new Set(creatingTaskIds.value)
  next.add(task.id)
  creatingTaskIds.value = next
  let successCount = 0
  try {
    for (const point of candidates) {
      await dispatchPointCodexJob(task, point, false)
      successCount += 1
    }
    ElMessage.success(`已启动 ${successCount} 个子项 Loop，交给${isDocumentProject.value ? '文档协作智能体' : '忍者神龟团队'}`)
    await loadCodexJobs()
  } catch {
    ElMessage.error(`已启动 ${successCount} 个子项，后续 Loop 启动失败`)
    await loadCodexJobs()
  } finally {
    const done = new Set(creatingTaskIds.value)
    done.delete(task.id)
    creatingTaskIds.value = done
  }
}

async function autoDispatchProject() {
  const project = selectedProject.value
  if (!project) return
  const candidates = project.tasks.flatMap(task =>
    (task.development_points || [])
      .filter(point => isExecutablePoint(point) && !hasActiveJob(point.id))
      .map(point => ({ task, point }))
  )
  if (!candidates.length) {
    ElMessage.info('当前项目暂无需要启动 Loop 的子项')
    return
  }
  autoDispatchingProject.value = true
  let successCount = 0
  try {
    for (const item of candidates) {
      await dispatchPointCodexJob(item.task, item.point, false)
      successCount += 1
    }
    ElMessage.success(`已启动 ${successCount} 个项目子项 Loop，交给${isDocumentProject.value ? '文档协作智能体' : '忍者神龟团队'}`)
    await loadCodexJobs()
  } catch {
    ElMessage.error(`已启动 ${successCount} 个子项，后续 Loop 启动失败`)
    await loadCodexJobs()
  } finally {
    autoDispatchingProject.value = false
  }
}

async function selectCodexJob(job: CodexJob) {
  const res = await getCodexJobLogs(job.id)
  const lines = (res.logs || []).join('').slice(-2000)
  ElMessageBox.alert(
    `${res.job.summary || lines || '暂无日志'}`,
    `${agentLabel(job.agent_id)} · ${codexStatusLabel(res.job.status)}`,
    { customClass: 'codex-log-dialog', confirmButtonText: '关闭' }
  )
  await loadCodexJobs()
}

function statusType(status: string) {
  if (['done', 'completed', 'active'].includes(status)) return 'success'
  if (['in_progress', 'running'].includes(status)) return 'warning'
  if (['blocked', 'failed'].includes(status)) return 'danger'
  return 'info'
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    planning: '规划中',
    planned: '规划中',
    active: '进行中',
    in_progress: '进行中',
    running: '运行中',
    todo: '待办',
    pending: '待处理',
    assigned: '已分配',
    review: '审查中',
    testing: '测试中',
    done: '已完成',
    completed: '已完成',
    blocked: '阻塞',
    failed: '失败',
    archived: '已归档'
  }
  return map[status] || status
}

function agentLabel(agentId?: string) {
  const map: Record<string, string> = {
    optimus: '擎天柱',
    'ultra-magnus': '通天晓',
    wheeljack: '千斤顶',
    ironhide: '铁皮',
    ratchet: '救护车',
    perceptor: '感知器',
    leonardo: '李奥纳多',
    donatello: '多纳泰罗',
    raphael: '拉斐尔',
    michelangelo: '米开朗基罗'
  }
  return agentId ? (map[agentId] || agentId) : '未分配'
}

function assetTypeLabel(type?: string) {
  const map: Record<string, string> = {
    image: '图片',
    chart: '图表',
    table: '表格',
    diagram: '示意图'
  }
  return type ? (map[type] || type) : '资产'
}

function codexStatusLabel(status: CodexJobStatus) {
  return {
    queued: '排队中',
    running: '执行中',
    succeeded: '已完成',
    failed: '失败',
    cancelled: '已取消'
  }[status] || status
}

function codexStatusType(status?: CodexJobStatus) {
  if (!status) return 'info'
  if (status === 'succeeded') return 'success'
  if (status === 'failed' || status === 'cancelled') return 'danger'
  if (status === 'running' || status === 'queued') return 'warning'
  return 'info'
}

function loopStatusLabel(status: string) {
  return {
    queued: '排队中',
    running: '协同中',
    succeeded: '已通过',
    failed: '未通过',
    cancelled: '已取消'
  }[status] || status
}

function loopStageLabel(stage: string) {
  return {
    queued: '等待启动',
    plan: '方案编写',
    develop: '开发实现',
    evaluate: '测试评估',
    done: '完成',
    failed: '待下一轮'
  }[stage] || stage
}

function formatTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '无记录'
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function phaseLabel(phase: string): string {
  const map: Record<string, string> = {
    planning: '规划中',
    outline: '大纲阶段',
    active: '进行中',
    agent_point_state_machine: '智能体要点状态机',
    'agent-point-state-machine': '智能体要点状态机'
  }
  return map[phase] || phase
}

function progressColor(percentage: number) {
  if (percentage >= 85) return '#67c23a'
  if (percentage >= 45) return '#409eff'
  return '#e6a23c'
}

async function loadProjects() {
  loading.value = true
  try {
    const data = await getProjects({ project_type: workspaceProjectType.value })
    projects.value = data.projects
    applyRouteSelection()
    for (const project of projects.value) {
      for (const task of project.tasks) {
        if (!taskCodexAgents[task.id]) {
          taskCodexAgents[task.id] = task.assignee_agent || task.assignee_agent_id || defaultCodexAgentForProject(task, project)
        }
      }
    }
  } catch {
    ElMessage.error('项目数据加载失败')
  } finally {
    loading.value = false
  }
}

function applyRouteSelection() {
  const routeProjectId = String(route.query.project_id || route.query.project || '')
  if (routeProjectId && projects.value.some(project => project.id === routeProjectId)) {
    selectedProjectId.value = routeProjectId
    return
  }
  if (!projects.value.some(project => project.id === selectedProjectId.value)) {
    selectedProjectId.value = projects.value[0]?.id || ''
  }
}

async function loadProjectSidecar(projectId: string) {
  if (!projectId) return
  try {
    const [context, conversation] = await Promise.all([
      getProjectChatContext(projectId).catch(() => null),
      getProjectConversation(projectId).catch(() => ({ messages: [], conversation: [] }))
    ])
    projectContext.value = context
    chatMessages.value = conversation.messages || conversation.conversation || []
  } catch {
    projectContext.value = null
    chatMessages.value = []
  }
}

async function sendChat() {
  const project = selectedProject.value
  const message = chatText.value.trim()
  if (!project || !message) {
    ElMessage.warning('请先输入要发送给项目智能体的内容')
    return
  }
  chatLoading.value = true
  try {
    await sendProjectChat(project.id, {
      agent_id: chatAgent.value,
      role: 'user',
      intent: 'project_collaboration',
      message
    })
    chatText.value = ''
    ElMessage.success('已发送到项目上下文')
    await loadProjectSidecar(project.id)
  } catch {
    ElMessage.error('发送失败')
  } finally {
    chatLoading.value = false
  }
}

async function generateTaskFromChat() {
  const project = selectedProject.value
  const message = chatText.value.trim()
  if (!project || !message) {
    ElMessage.warning('请先输入任务意图')
    return
  }
  chatLoading.value = true
  try {
    await createProjectAgentAction(project.id, {
      action_type: isDocumentProject.value ? 'writing_task' : 'development_task',
      agent_id: chatAgent.value,
      assignee_agent: chatAgent.value,
      task_title: message.slice(0, 36),
      task_type: isDocumentProject.value ? 'writing' : 'development',
      instruction: message,
      payload: {
        priority: 'medium',
        point_title: `${message.slice(0, 48)} - ${isDocumentProject.value ? '写作要点' : '开发要点'}`
      }
    })
    chatText.value = ''
    ElMessage.success('任务已生成')
    await loadProjects()
    if (project.id) await loadProjectSidecar(project.id)
  } catch {
    ElMessage.error('生成任务失败')
  } finally {
    chatLoading.value = false
  }
}

watch(() => route.query.project_id, applyRouteSelection)
watch(workspaceProjectType, () => {
  selectedProjectId.value = ''
  projectContext.value = null
  chatMessages.value = []
  loadProjects()
})
watch(() => selectedProject.value?.id, projectId => {
  if (projectId) loadProjectSidecar(projectId)
}, { immediate: true })

onMounted(loadProjects)
onMounted(loadCodexJobs)
onMounted(loadCodexLoops)
onMounted(startCodexLoopPolling)
onUnmounted(stopCodexLoopPolling)
</script>

<style scoped>
.projects-page {
  min-height: 100%;
}

.panel {
  border-radius: 8px;
  margin-bottom: 16px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.panel-header-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.project-list-panel {
  position: sticky;
  top: 0;
}

.project-list {
  display: grid;
  gap: 10px;
}

.project-card {
  width: 100%;
  border: 1px solid var(--view-color-border);
  border-radius: 8px;
  background: var(--card);
  padding: 12px;
  text-align: left;
  cursor: pointer;
}

.project-card.active {
  border-color: var(--view-color-strong-border);
  background: var(--view-color-panel);
}

.project-card-title {
  font-weight: 700;
  color: var(--text);
  margin-bottom: 4px;
}

.project-card-meta,
.muted {
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.project-title {
  font-size: 20px;
  font-weight: 800;
  color: var(--text);
}

.metric-row {
  margin-bottom: 4px;
}

.metric {
  border: 1px solid var(--view-color-border);
  border-radius: 8px;
  padding: 12px;
  display: grid;
  gap: 8px;
  background: var(--view-color-faint);
}

.metric span {
  color: var(--text-secondary);
  font-size: 13px;
}

.metric strong {
  color: var(--text);
  font-size: 22px;
}

.doc-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.document-workspace {
  display: grid;
  gap: 18px;
}

.document-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.document-summary-item {
  display: grid;
  gap: 6px;
  min-height: 78px;
  padding: 12px;
  border: 1px solid var(--view-color-border);
  border-radius: 8px;
  background: var(--view-color-faint);
}

.document-summary-item span {
  color: var(--text-secondary);
  font-size: 12px;
}

.document-summary-item strong {
  color: var(--text);
  font-size: 14px;
  line-height: 1.5;
  word-break: break-word;
}

.document-section {
  display: grid;
  gap: 12px;
}

.document-section-head,
.document-card-head,
.document-card-foot,
.document-asset-card,
.document-asset-meta {
  display: flex;
  align-items: center;
  gap: 10px;
}

.document-section-head,
.document-card-head,
.document-card-foot,
.document-asset-card {
  justify-content: space-between;
}

.document-section-head h3 {
  margin: 0 0 4px;
  font-size: 15px;
}

.document-section-list,
.document-asset-list {
  display: grid;
  gap: 10px;
}

.document-section-card,
.document-asset-card {
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--view-color-border);
  border-radius: 8px;
  background: var(--view-color-faint);
}

.document-section-card {
  display: grid;
  gap: 8px;
}

.document-card-head strong,
.document-asset-card strong {
  color: var(--text);
  font-size: 14px;
}

.document-card-foot {
  color: var(--text-secondary);
  font-size: 12px;
}

.document-asset-card > div:first-child {
  min-width: 0;
}

.document-asset-meta {
  flex-wrap: wrap;
  justify-content: flex-end;
  color: var(--text-secondary);
  font-size: 12px;
}

.doc-grid h3 {
  margin: 0 0 10px;
  font-size: 15px;
}

.clean-list {
  margin: 0;
  padding-left: 18px;
  color: var(--text-secondary);
  line-height: 1.8;
}

.doc-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.right-rail {
  position: sticky;
  top: 0;
}

.manager-panel,
.chat-panel,
.project-links-panel {
  margin-bottom: 16px;
}

.manager-section {
  display: grid;
  gap: 8px;
  padding: 10px 0;
  border-bottom: 1px solid var(--view-color-border);
}

.manager-section:last-child {
  border-bottom: 0;
  padding-bottom: 0;
}

.section-title {
  color: var(--text);
  font-size: 13px;
  font-weight: 800;
}

.suggestion-list,
.compact-list,
.agent-work-list,
.chat-history {
  display: grid;
  gap: 8px;
}

.suggestion-item,
.chat-message {
  padding: 9px 10px;
  border: 1px solid var(--view-color-border);
  border-radius: 8px;
  background: var(--view-color-faint);
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.5;
}

.compact-list {
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.agent-work-row {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  color: var(--text-secondary);
  font-size: 13px;
}

.agent-work-row span,
.chat-message span {
  overflow: hidden;
  text-overflow: ellipsis;
}

.agent-select {
  width: 112px;
}

.chat-context,
.chat-history {
  margin-bottom: 10px;
}

.chat-message {
  display: grid;
  gap: 4px;
}

.chat-message strong {
  color: var(--text);
}

.chat-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 10px;
}

.task-list {
  display: grid;
  gap: 14px;
}

.task-card {
  border: 1px solid var(--view-color-border);
  border-radius: 8px;
  padding: 14px;
  background: var(--view-color-faint);
}

.task-main {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.task-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
}

.task-status {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-secondary);
  font-weight: 700;
}

.execution-list {
  display: grid;
  gap: 10px;
  margin-top: 14px;
}

.execution-list-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.execution-list-head strong {
  color: var(--text);
  font-size: 14px;
}

.execution-list-head small {
  color: var(--text-secondary);
  font-size: 12px;
}

.execution-row {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(180px, 0.85fr) auto;
  gap: 12px;
  align-items: center;
  min-height: 58px;
  padding: 10px;
  border: 1px solid var(--view-color-border);
  border-radius: 8px;
  background: var(--view-color-faint);
}

.execution-main,
.execution-state,
.execution-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.execution-copy,
.execution-state {
  min-width: 0;
}

.execution-copy {
  display: grid;
  gap: 3px;
}

.execution-copy span,
.execution-state span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.execution-copy span {
  font-size: 13px;
  color: var(--text);
  font-weight: 700;
}

.execution-copy small,
.execution-state span {
  color: var(--text-secondary);
}

.execution-copy small {
  color: var(--text-secondary);
  font-size: 12px;
}

.execution-state span {
  font-size: 12px;
}

.execution-actions {
  justify-content: flex-end;
  min-width: 150px;
}

.codex-task-panel {
  display: grid;
  gap: 10px;
  margin-top: 14px;
  padding: 12px;
  border: 1px solid var(--view-color-border);
  border-radius: 8px;
  background: var(--view-color-faint);
}

.codex-task-head,
.codex-task-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.codex-task-head strong,
.codex-task-head small {
  display: block;
}

.codex-task-head strong {
  color: var(--text);
  font-size: 14px;
}

.codex-task-head small {
  margin-top: 3px;
  color: var(--text-secondary);
  font-size: 12px;
}

.codex-job-list {
  display: grid;
  gap: 8px;
}

.codex-job {
  display: grid;
  gap: 4px;
  width: 100%;
  padding: 9px 10px;
  border: 1px solid var(--view-color-border);
  border-radius: 6px;
  background: var(--card);
  color: var(--text);
  text-align: left;
  cursor: pointer;
}

.codex-job:hover {
  border-color: var(--view-color-strong-border);
  background: var(--view-color-panel);
}

.codex-job span,
.codex-job small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.codex-job span {
  font-size: 13px;
  font-weight: 700;
}

.codex-job small {
  color: var(--text-secondary);
  font-size: 12px;
}

.repo-list {
  display: grid;
  gap: 10px;
  padding: 4px 0;
}

.repo-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid var(--view-color-border);
  border-radius: 6px;
  background: var(--view-color-faint);
}

.repo-item-main {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.repo-link {
  color: var(--view-color-strong);
  font-size: 13px;
  font-weight: 700;
  text-decoration: none;
  word-break: break-all;
}

.repo-link:hover {
  text-decoration: underline;
}

.repo-desc {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:global(.codex-log-dialog .el-message-box__message) {
  max-height: 56vh;
  overflow: auto;
  white-space: pre-wrap;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  line-height: 1.6;
}
</style>
