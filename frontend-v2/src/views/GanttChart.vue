<template>
  <div class="gantt-page">
    <div class="gantt-header">
      <h2>甘特图视图</h2>
      <div class="gantt-controls">
        <el-select
          v-model="filterAgent"
          placeholder="按智能体过滤"
          clearable
          style="width: 160px"
          @change="loadGanttData"
        >
          <el-option label="全部" value="" />
          <el-option label="🟦 李奥纳多" value="leonardo" />
          <el-option label="🟥 拉斐尔" value="raphael" />
          <el-option label="🟪 多纳泰罗" value="donatello" />
          <el-option label="🟧 米开朗基罗" value="michelangelo" />
        </el-select>
      </div>
    </div>

    <el-card v-loading="loading">
      <div ref="chartRef" class="gantt-chart" />
    </el-card>

    <!-- 点击任务查看详情 -->
    <TaskDetail
      v-model="showDetail"
      :task="selectedTask"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import { getTasks } from '@/api/tasks'
import type { Task } from '@/stores/tasks'
import TaskDetail from '@/components/TaskDetail.vue'

const chartRef = ref<HTMLElement>()
const loading = ref(false)
const filterAgent = ref('')
const showDetail = ref(false)
const selectedTask = ref<Task | null>(null)

let chartInstance: echarts.ECharts | null = null

const statusColors: Record<string, string> = {
  pending: '#909399',
  assigned: '#c0c4cc',
  in_progress: '#e6a23c',
  review: '#409eff',
  testing: '#67c23a',
  done: '#67c23a',
  archived: '#c0c4cc'
}

const statusLabels: Record<string, string> = {
  pending: '待处理', assigned: '已分配', in_progress: '进行中',
  review: '审查中', testing: '测试中', done: '已完成', archived: '已归档'
}

async function loadGanttData() {
  loading.value = true
  try {
    const res = await getTasks({
      assignee: filterAgent.value || undefined,
      page_size: 100
    })

    const today = new Date()
    today.setHours(0, 0, 0, 0)

    const seriesData: Array<{
      name: string
      value: [number, number, number, number]
      itemStyle: { color: string }
      task: Task
    }> = []

    res.tasks.forEach((task, index) => {
      const start = task.start_date ? new Date(task.start_date) : today
      const end = task.due_date ? new Date(task.due_date) : new Date(today.getTime() + 7 * 24 * 60 * 60 * 1000)

      const startTs = start.getTime()
      const endTs = end.getTime()

      seriesData.push({
        name: task.title,
        value: [index, startTs, endTs, task.progress],
        itemStyle: { color: statusColors[task.status] || '#909399' },
        task
      })
    })

    if (!seriesData.length) {
      renderEmpty()
      return
    }

    const categoryData = seriesData.map(d => d.name)

    const option: EChartsOption = {
      tooltip: {
        formatter: (params: unknown) => {
          const p = params as { value: [number, number, number, number]; data: { task: Task; itemStyle: { color: string } } }
          const task = p.data.task
          const start = new Date(p.value[1]).toLocaleDateString('zh-CN')
          const end = new Date(p.value[2]).toLocaleDateString('zh-CN')
          return `
            <strong>${task.title}</strong><br/>
            状态: ${statusLabels[task.status] || task.status}<br/>
            负责人: ${task.assignee || '未分配'}<br/>
            进度: ${task.progress}%<br/>
            开始: ${start}<br/>
            截止: ${end}
          `
        }
      },
      grid: { top: 30, bottom: 30, left: 150, right: 30 },
      xAxis: {
        type: 'time',
        axisLabel: {
          formatter: '{MM}-{dd}',
          fontSize: 12
        },
        splitLine: { show: true, lineStyle: { type: 'dashed' } }
      },
      yAxis: {
        type: 'category',
        data: categoryData,
        inverse: true,
        axisLabel: {
          width: 140,
          overflow: 'truncate',
          fontSize: 12
        }
      },
      series: [{
        type: 'custom',
        renderItem: (params: { context: { lastIndex?: number }; coordSys: { height: number } }, api) => {
          const categoryIndex = api.value(0)
          const start = api.coord([api.value(1), categoryIndex])
          const end = api.coord([api.value(2), categoryIndex])
          const barHeight = Math.min(api.size([0, 1])[1] * 0.6, 24)

          const rect = {
            x: start[0],
            y: start[1] - barHeight / 2,
            width: Math.max(end[0] - start[0], 4),
            height: barHeight
          }

          return {
            type: 'group',
            children: [{
              type: 'rect',
              shape: rect,
              style: api.style()
            }]
          }
        },
        encode: {
          x: [1, 2],
          y: 0
        },
        data: seriesData
      }]
    }

    chartInstance?.setOption(option)

    // 点击事件
    chartInstance?.off('click')
    chartInstance?.on('click', (params: unknown) => {
      const p = params as { data: { task: Task } }
      if (p.data?.task) {
        selectedTask.value = p.data.task
        showDetail.value = true
      }
    })
  } catch {
    // 静默
  } finally {
    loading.value = false
  }
}

function renderEmpty() {
  const option: EChartsOption = {
    title: { text: '暂无任务数据', left: 'center', top: 'middle', textStyle: { color: '#c0c4cc', fontSize: 18 } },
    xAxis: { type: 'time', show: false },
    yAxis: { type: 'category', data: [], show: false },
    series: []
  }
  chartInstance?.setOption(option)
}

onMounted(() => {
  if (chartRef.value) {
    chartInstance = echarts.init(chartRef.value)
    loadGanttData()

    window.addEventListener('resize', () => chartInstance?.resize())
  }
})

onUnmounted(() => {
  chartInstance?.dispose()
  window.removeEventListener('resize', () => chartInstance?.resize())
})
</script>

<style scoped>
.gantt-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.gantt-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.gantt-header h2 {
  margin: 0;
  font-size: 18px;
}

.gantt-controls {
  display: flex;
  gap: 8px;
}

.gantt-chart {
  width: 100%;
  height: 500px;
}
</style>
