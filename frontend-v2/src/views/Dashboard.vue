<template>
  <div class="dashboard-page">
    <el-row :gutter="20">
      <el-col :span="6">
        <StatCard title="项目" :value="projectCount" icon="📁" color="#409eff" />
      </el-col>
      <el-col :span="6">
        <StatCard title="并行任务" :value="taskCount" icon="📋" color="#e6a23c" />
      </el-col>
      <el-col :span="6">
        <StatCard title="开发要点" :value="pointCount" icon="✅" color="#67c23a" />
      </el-col>
      <el-col :span="6">
        <StatCard title="智能体" :value="agentCount" icon="🤖" color="#909399" />
      </el-col>
    </el-row>

    <el-row :gutter="20">
      <el-col :span="12">
        <el-card class="chart-card" shadow="hover">
          <template #header>
            <span class="chart-title">任务状态分布</span>
          </template>
          <v-chart class="chart" :option="taskPieOption" autoresize />
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card class="chart-card" shadow="hover">
          <template #header>
            <span class="chart-title">统一数据源</span>
          </template>
          <v-chart class="chart" :option="dataSourceOption" autoresize />
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20">
      <el-col :span="14">
        <el-card class="panel-card" shadow="hover">
          <template #header>
            <div class="panel-header">
              <span>当前项目</span>
              <el-button type="primary" size="small" @click="$router.push('/projects')">进入项目管理</el-button>
            </div>
          </template>
          <el-table :data="projects" size="small" height="260">
            <el-table-column prop="name" label="项目" min-width="220" show-overflow-tooltip />
            <el-table-column label="状态" width="100">
              <template #default="{ row }">{{ statusLabel(row.status) }}</template>
            </el-table-column>
            <el-table-column label="任务" width="90" align="right">
              <template #default="{ row }">{{ row.tasks.length }}</template>
            </el-table-column>
            <el-table-column label="进度" width="180">
              <template #default="{ row }">
                <el-progress :percentage="Math.round(row.progress || 0)" />
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="10">
        <el-card class="panel-card" shadow="hover">
          <template #header>
            <div class="panel-header">
              <span>系统状态</span>
              <el-button size="small" @click="$router.push('/data-admin')">数据管理</el-button>
            </div>
          </template>
          <div class="status-list">
            <div class="status-row">
              <span>数据库</span>
              <el-tag :type="databaseReady ? 'success' : 'warning'">{{ databaseStatusLabel }}</el-tag>
            </div>
            <div class="status-row">
              <span>数据源</span>
              <strong>{{ dataSourceCount }}</strong>
            </div>
            <div class="status-row">
              <span>设备</span>
              <strong>{{ deviceCount }}</strong>
            </div>
            <div class="status-row">
              <span>审计日志</span>
              <strong>{{ auditLogCount }}</strong>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import StatCard from '@/components/common/StatCard.vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart } from 'echarts/charts'
import { LegendComponent, TooltipComponent } from 'echarts/components'
import { getProjects, type Project } from '@/api/projects'
import { getDataOverview, type DataOverview } from '@/api/dataAdmin'
import apiClient from '@/api/client'

use([CanvasRenderer, PieChart, TooltipComponent, LegendComponent])

interface AgentDashboard {
  agents: unknown[]
}

const projects = ref<Project[]>([])
const dataOverview = ref<DataOverview | null>(null)
const agents = ref<unknown[]>([])

const projectCount = computed(() => projects.value.length)
const taskCount = computed(() => projects.value.reduce((sum, project) => sum + project.tasks.length, 0))
const pointCount = computed(() => projects.value.reduce((sum, project) => sum + project.tasks.reduce((taskSum, task) => taskSum + task.development_points.length, 0), 0))
const agentCount = computed(() => agents.value.length || dataOverview.value?.totals.agents || 0)
const dataSourceCount = computed(() => dataOverview.value?.totals.data_sources || 0)
const deviceCount = computed(() => dataOverview.value?.totals.devices || 0)
const auditLogCount = computed(() => dataOverview.value?.totals.audit_logs || 0)
const databaseStatus = computed(() => dataOverview.value?.database.status || 'unknown')
const databaseStatusLabel = computed(() => statusLabel(databaseStatus.value))
const databaseReady = computed(() => databaseStatus.value === 'ready')

const taskStatusCounts = computed(() => {
  const counts: Record<string, number> = {}
  projects.value.flatMap(project => project.tasks).forEach(task => {
    counts[task.status] = (counts[task.status] || 0) + 1
  })
  return counts
})

const taskPieOption = computed(() => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 0, left: 'center' },
  series: [{
    name: '任务状态',
    type: 'pie',
    radius: ['42%', '70%'],
    itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
    data: Object.entries(taskStatusCounts.value).map(([name, value]) => ({ name: statusLabel(name), value }))
  }]
}))

const dataSourceOption = computed(() => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 0, left: 'center' },
  series: [{
    name: '数据源',
    type: 'pie',
    radius: ['42%', '70%'],
    itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
    data: [
      { name: '数据源', value: dataSourceCount.value },
      { name: '备份', value: dataOverview.value?.totals.storage_backups || 0 },
      { name: '迁移', value: dataOverview.value?.totals.schema_migrations || 0 },
    ]
  }]
}))

async function loadDashboard() {
  try {
    const [projectData, overviewData, agentData] = await Promise.all([
      getProjects(),
      getDataOverview(),
      apiClient.get<AgentDashboard>('/api/v3/agents/dashboard').then(r => r.data).catch(() => ({ agents: [] })),
    ])
    projects.value = projectData.projects
    dataOverview.value = overviewData
    agents.value = agentData.agents || []
  } catch {
    ElMessage.error('仪表盘数据加载失败')
  }
}

onMounted(loadDashboard)

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    ready: '就绪',
    unknown: '未知',
    active: '进行中',
    inactive: '停用',
    pending: '待处理',
    assigned: '已分配',
    in_progress: '进行中',
    review: '审查中',
    testing: '测试中',
    done: '已完成',
    completed: '已完成',
    archived: '已归档',
    blocked: '阻塞',
    failed: '失败'
  }
  return map[status] || status
}
</script>

<style scoped>
.dashboard-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.chart-card,
.panel-card {
  border-radius: 8px;
}

.chart {
  height: 300px;
}

.chart-title {
  font-weight: 700;
  color: #303133;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.status-list {
  display: grid;
  gap: 14px;
}

.status-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 12px;
  color: #606266;
}

.status-row strong {
  color: #303133;
  font-size: 18px;
}
</style>
