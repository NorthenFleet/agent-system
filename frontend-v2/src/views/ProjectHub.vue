<template>
  <div class="project-hub-page">
    <section class="hub-summary">
      <div class="hub-summary-main">
        <h2>项目中枢</h2>
        <p>把程序开发、文档撰写、财务、知识引用和产品矩阵聚合到同一个项目视图。</p>
      </div>
      <div class="hub-metrics">
        <div class="metric">
          <span>项目</span>
          <strong>{{ projects.length }}</strong>
        </div>
        <div class="metric">
          <span>开发</span>
          <strong>{{ softwareProjects.length }}</strong>
        </div>
        <div class="metric">
          <span>文档</span>
          <strong>{{ documentProjects.length }}</strong>
        </div>
      </div>
    </section>

    <el-skeleton v-if="loading" :rows="8" animated />
    <section v-else class="project-grid">
      <article v-for="project in projects" :key="project.id" class="project-panel">
        <header class="project-panel-head">
          <div>
            <h3>{{ project.name }}</h3>
            <p>{{ project.description || projectTypeLabel(project) }}</p>
          </div>
          <el-tag :type="projectTypeValue(project) === 'document' ? 'warning' : 'primary'">
            {{ projectTypeLabel(project) }}
          </el-tag>
        </header>

        <div class="project-progress">
          <div class="progress-head">
            <span>{{ phaseLabel(project.current_phase || project.status) }}</span>
            <strong>{{ Math.round(project.progress || 0) }}%</strong>
          </div>
          <el-progress :percentage="Math.round(project.progress || 0)" :show-text="false" />
        </div>

        <div class="module-grid">
          <button
            v-for="module in modulesForProject(project)"
            :key="module.key"
            class="module-tile"
            :class="{ active: module.active }"
            :disabled="!module.active"
            @click="openModule(project, module.route)"
          >
            <span>{{ module.name }}</span>
            <strong>{{ module.value }}</strong>
          </button>
        </div>
      </article>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getProjects, type Project } from '@/api/projects'

interface ProjectModuleTile {
  key: string
  name: string
  value: string
  route: string
  active: boolean
}

const router = useRouter()
const loading = ref(false)
const projects = ref<Project[]>([])

const softwareProjects = computed(() => projects.value.filter(project => projectTypeValue(project) === 'software'))
const documentProjects = computed(() => projects.value.filter(project => projectTypeValue(project) === 'document'))

function projectTypeValue(project?: Project): 'software' | 'document' {
  const value = String(project?.project_type || project?.type || 'software').toLowerCase()
  return value === 'document' ? 'document' : 'software'
}

function projectTypeLabel(project?: Project) {
  return projectTypeValue(project) === 'document' ? '文档项目' : '开发项目'
}

function phaseLabel(phase?: string) {
  const map: Record<string, string> = {
    planning: '规划中',
    active: '进行中',
    completed: '已完成',
    done: '已完成',
    draft: '草稿',
    outline: '大纲阶段'
  }
  return map[phase || ''] || phase || '未设置'
}

function modulesForProject(project: Project): ProjectModuleTile[] {
  const type = projectTypeValue(project)
  const taskCount = project.tasks?.length || 0
  const chapterCount = project.document_spec?.chapters?.length || 0
  const assetCount = project.document_spec?.assets?.length || 0
  return [
    {
      key: 'development',
      name: '程序开发',
      value: type === 'software' ? `${taskCount} 任务` : '未启用',
      route: '/development',
      active: type === 'software'
    },
    {
      key: 'writing',
      name: '文档撰写',
      value: type === 'document' ? `${chapterCount} 章` : '未启用',
      route: '/writing',
      active: type === 'document'
    },
    {
      key: 'finance',
      name: '财务管理',
      value: '预算/报销',
      route: '/finance',
      active: true
    },
    {
      key: 'knowledge',
      name: '知识引用',
      value: type === 'document' ? `${assetCount} 图表` : '知识库',
      route: '/knowledge',
      active: true
    },
    {
      key: 'products',
      name: '产品矩阵',
      value: '产品侧',
      route: '/products',
      active: true
    }
  ]
}

function openModule(project: Project, route: string) {
  router.push({ path: route, query: { project_id: project.id } })
}

async function loadProjects() {
  loading.value = true
  try {
    const data = await getProjects()
    projects.value = data.projects || []
  } catch {
    ElMessage.error('项目数据加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(loadProjects)
</script>

<style scoped>
.project-hub-page {
  min-height: 100%;
}

.hub-summary {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px;
  align-items: stretch;
  margin-bottom: 18px;
  padding: 18px;
  border: 1px solid var(--view-color-border);
  border-radius: 8px;
  background: var(--panel-bg);
}

.hub-summary-main h2 {
  margin: 0 0 6px;
  color: var(--text-primary);
  font-size: 20px;
}

.hub-summary-main p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.6;
}

.hub-metrics {
  display: grid;
  grid-template-columns: repeat(3, 96px);
  gap: 10px;
}

.metric {
  display: grid;
  gap: 6px;
  align-content: center;
  padding: 12px;
  border: 1px solid var(--line-color);
  border-radius: 6px;
  background: var(--card-bg);
}

.metric span {
  color: var(--text-secondary);
  font-size: 12px;
}

.metric strong {
  color: var(--text-primary);
  font-size: 22px;
}

.project-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  gap: 16px;
}

.project-panel {
  display: grid;
  gap: 14px;
  padding: 16px;
  border: 1px solid var(--view-color-border);
  border-radius: 8px;
  background: var(--panel-bg);
}

.project-panel-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.project-panel-head h3 {
  margin: 0 0 6px;
  color: var(--text-primary);
  font-size: 16px;
}

.project-panel-head p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.5;
}

.project-progress {
  display: grid;
  gap: 8px;
}

.progress-head {
  display: flex;
  justify-content: space-between;
  color: var(--text-secondary);
  font-size: 12px;
}

.module-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(128px, 1fr));
  gap: 10px;
}

.module-tile {
  min-height: 72px;
  display: grid;
  gap: 6px;
  align-content: center;
  text-align: left;
  padding: 10px 12px;
  border: 1px solid var(--line-color);
  border-radius: 6px;
  color: var(--text-secondary);
  background: var(--card-bg);
  cursor: default;
}

.module-tile.active {
  color: var(--text-primary);
  border-color: var(--view-color-border);
  background: var(--view-color-faint);
  cursor: pointer;
}

.module-tile.active:hover {
  border-color: var(--view-color-strong-border);
  background: var(--view-color-soft);
}

.module-tile span {
  font-size: 12px;
}

.module-tile strong {
  font-size: 14px;
  font-weight: 700;
}

@media (max-width: 900px) {
  .hub-summary {
    grid-template-columns: 1fr;
  }

  .hub-metrics {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
