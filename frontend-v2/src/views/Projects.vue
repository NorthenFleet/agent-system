<template>
  <div class="projects-page">
    <el-row :gutter="18">
      <el-col :span="7">
        <el-card class="panel project-list-panel" shadow="hover">
          <template #header>
            <div class="panel-header">
              <span>项目</span>
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

      <el-col :span="17">
        <el-empty v-if="!selectedProject" description="暂无项目" />
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
                  <span>开发要点</span>
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

            <div class="doc-grid">
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
                <span>并行开发任务</span>
                <el-tag>{{ selectedProject.tasks.length }} 个</el-tag>
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
                <div class="point-list">
                  <div v-for="point in task.development_points" :key="point.id" class="point-row">
                    <el-tag :type="statusType(point.status)" size="small">{{ statusLabel(point.status) }}</el-tag>
                    <span>{{ point.title }}</span>
                    <small>{{ point.assigned_agent || task.assignee_agent || '未分配' }}</small>
                  </div>
                </div>
              </div>
            </div>
          </el-card>
        </template>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getProjects, type Project } from '@/api/projects'

const route = useRoute()
const loading = ref(false)
const projects = ref<Project[]>([])
const selectedProjectId = ref('')

const selectedProject = computed(() => projects.value.find(project => project.id === selectedProjectId.value) || projects.value[0])
const totalPoints = computed(() => selectedProject.value?.tasks.reduce((sum, task) => sum + task.development_points.length, 0) || 0)
const usageRequirements = computed(() => {
  const items = selectedProject.value?.design_doc?.usage_requirements || []
  return items.map(item => typeof item === 'string' ? item : JSON.stringify(item))
})

function statusType(status: string) {
  if (['done', 'completed', 'active'].includes(status)) return 'success'
  if (['in_progress', 'running'].includes(status)) return 'warning'
  if (['blocked', 'failed'].includes(status)) return 'danger'
  return 'info'
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    planning: '规划中',
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

function phaseLabel(phase: string): string {
  const map: Record<string, string> = {
    planning: '规划中',
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
    const data = await getProjects()
    projects.value = data.projects
    applyRouteSelection()
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
  if (!selectedProjectId.value && projects.value.length) {
    selectedProjectId.value = projects.value[0].id
  }
}

watch(() => route.query.project_id, applyRouteSelection)

onMounted(loadProjects)
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
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  background: #fff;
  padding: 12px;
  text-align: left;
  cursor: pointer;
}

.project-card.active {
  border-color: #409eff;
  background: #ecf5ff;
}

.project-card-title {
  font-weight: 700;
  color: #303133;
  margin-bottom: 4px;
}

.project-card-meta,
.muted {
  color: #909399;
  font-size: 13px;
  line-height: 1.6;
}

.project-title {
  font-size: 20px;
  font-weight: 800;
  color: #303133;
}

.metric-row {
  margin-bottom: 4px;
}

.metric {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 12px;
  display: grid;
  gap: 8px;
}

.metric span {
  color: #909399;
  font-size: 13px;
}

.metric strong {
  color: #303133;
  font-size: 22px;
}

.doc-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.doc-grid h3 {
  margin: 0 0 10px;
  font-size: 15px;
}

.clean-list {
  margin: 0;
  padding-left: 18px;
  color: #606266;
  line-height: 1.8;
}

.doc-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.task-list {
  display: grid;
  gap: 14px;
}

.task-card {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 14px;
  background: #fff;
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
  color: #303133;
}

.task-status {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #606266;
  font-weight: 700;
}

.point-list {
  display: grid;
  gap: 8px;
  margin-top: 12px;
}

.point-row {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr) 92px;
  gap: 10px;
  align-items: center;
  font-size: 13px;
  color: #606266;
}

.point-row small {
  color: #909399;
  text-align: right;
}
</style>
