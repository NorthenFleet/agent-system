<template>
  <div class="tools-page">
    <div class="page-header">
      <h2>🔧 工具中心</h2>
      <p class="subtitle">技能包与自动化工作流</p>
    </div>

    <!-- 技能包 -->
    <el-card class="section-card" shadow="hover">
      <template #header>
        <div class="section-header">
          <el-icon size="20"><Box /></el-icon>
          <h3>技能包</h3>
          <el-tag type="success" effect="plain">{{ skills.length }} 个技能</el-tag>
        </div>
      </template>

      <el-row :gutter="16">
        <el-col
          v-for="skill in skills"
          :key="skill.name"
          :xs="24" :sm="12" :md="8" :lg="6"
        >
          <el-card class="skill-card" shadow="hover">
            <div class="skill-icon">{{ skill.icon }}</div>
            <div class="skill-name">{{ skill.name }}</div>
            <div class="skill-desc">{{ skill.description }}</div>
            <div class="skill-tags">
              <el-tag
                v-for="tag in skill.tags"
                :key="tag"
                size="small"
                effect="plain"
                class="skill-tag"
              >{{ tag }}</el-tag>
            </div>
            <div class="skill-status" :class="skill.statusClass">
              {{ skill.statusText }}
            </div>
          </el-card>
        </el-col>
      </el-row>
    </el-card>

    <!-- 工作流 -->
    <el-card class="section-card" shadow="hover">
      <template #header>
        <div class="section-header">
          <el-icon size="20"><Connection /></el-icon>
          <h3>自动化工作流</h3>
          <el-tag type="primary" effect="plain">{{ workflows.length }} 个工作流</el-tag>
        </div>
      </template>

      <el-table :data="workflows" stripe style="width: 100%">
        <el-table-column prop="icon" label="" width="50" align="center">
          <template #default="{ row }">
            <span class="workflow-icon">{{ row.icon }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="工作流名称" min-width="180">
          <template #default="{ row }">
            <span class="workflow-name">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="说明" min-width="250" />
        <el-table-column prop="priority" label="优先级" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.priorityType" size="small">{{ row.priority }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.statusType" size="small" effect="plain">{{ row.statusText }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" align="center">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'active'"
              size="small"
              type="primary"
              @click="triggerWorkflow(row)"
            >
              触发
            </el-button>
            <el-button
              v-else-if="row.status === 'pending'"
              size="small"
              type="warning"
              @click="enableWorkflow(row)"
            >
              启用
            </el-button>
            <el-button v-else size="small" disabled>
              待创建
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 快捷操作 -->
    <el-card class="section-card" shadow="hover">
      <template #header>
        <div class="section-header">
          <el-icon size="20"><Star /></el-icon>
          <h3>快捷操作</h3>
        </div>
      </template>

      <el-row :gutter="16">
        <el-col :xs="24" :sm="12" :md="8" v-for="action in quickActions" :key="action.name">
          <el-button
            class="quick-action-btn"
            :type="action.type"
            size="large"
            @click="action.handler"
          >
            <span class="btn-icon">{{ action.icon }}</span>
            <div class="btn-text">
              <div class="btn-name">{{ action.name }}</div>
              <div class="btn-desc">{{ action.description }}</div>
            </div>
          </el-button>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Box, Connection, Star } from '@element-plus/icons-vue'

interface Skill {
  name: string
  icon: string
  description: string
  tags: string[]
  statusClass: string
  statusText: string
}

interface Workflow {
  name: string
  icon: string
  description: string
  priority: string
  priorityType: 'danger' | 'warning' | 'success' | 'info'
  status: 'active' | 'pending' | 'draft'
  statusType: 'success' | 'warning' | 'info'
  statusText: string
  handler?: () => void
}

interface QuickAction {
  name: string
  icon: string
  description: string
  type: 'primary' | 'success' | 'warning'
  handler: () => void
}

const skills = ref<Skill[]>([
  {
    name: '图表生成器',
    icon: '📊',
    description: '创建 SVG/HTML 或 Excalidraw 图表',
    tags: ['可视化', '架构图', '流程图'],
    statusClass: 'status-active',
    statusText: '已启用'
  },
  {
    name: '飞书文档',
    icon: '📄',
    description: '飞书文档读写操作',
    tags: ['飞书', '文档', '协作'],
    statusClass: 'status-active',
    statusText: '已启用'
  },
  {
    name: '飞书云盘',
    icon: '💾',
    description: '飞书云存储文件管理',
    tags: ['飞书', '文件', '云盘'],
    statusClass: 'status-active',
    statusText: '已启用'
  },
  {
    name: '飞书知识库',
    icon: '📚',
    description: '飞书知识库导航',
    tags: ['飞书', '知识库', 'Wiki'],
    statusClass: 'status-active',
    statusText: '已启用'
  },
  {
    name: '代码议题管理',
    icon: '🐛',
    description: '代码仓库议题与合并请求管理',
    tags: ['代码仓库', '议题', '合并请求'],
    statusClass: 'status-active',
    statusText: '已启用'
  },
  {
    name: '代码仓库工具',
    icon: '🔧',
    description: '代码仓库命令行操作',
    tags: ['代码仓库', '持续集成', '代码'],
    statusClass: 'status-active',
    statusText: '已启用'
  },
  {
    name: '健康检查',
    icon: '🩺',
    description: '主机安全审计与加固',
    tags: ['安全', '审计', '运维'],
    statusClass: 'status-active',
    statusText: '已启用'
  },
  {
    name: '内容摘要',
    icon: '📝',
    description: '内容摘要与总结',
    tags: ['摘要', '文档', '视频'],
    statusClass: 'status-active',
    statusText: '已启用'
  },
  {
    name: '技能创建器',
    icon: '🛠️',
    description: '创建和管理技能文件',
    tags: ['开发', '工具', '元技能'],
    statusClass: 'status-active',
    statusText: '已启用'
  },
  {
    name: '任务流编排',
    icon: '🔄',
    description: '多步骤任务流编排',
    tags: ['编排', '自动化', '任务'],
    statusClass: 'status-active',
    statusText: '已启用'
  },
  {
    name: '终端会话',
    icon: '🖥️',
    description: '控制 tmux 会话',
    tags: ['终端', '交互', '会话'],
    statusClass: 'status-active',
    statusText: '已启用'
  }
])

const workflows = ref<Workflow[]>([
  {
    name: '项目派发流',
    icon: '🚀',
    description: 'PM发起→任务拆解→分配→确认接收',
    priority: 'P0',
    priorityType: 'danger',
    status: 'pending',
    statusType: 'warning',
    statusText: '待启用'
  },
  {
    name: '进度巡检流',
    icon: '📊',
    description: '定时扫描看板→汇总异常→自动报告孙总',
    priority: 'P0',
    priorityType: 'danger',
    status: 'pending',
    statusType: 'warning',
    statusText: '待启用'
  },
  {
    name: '质量门禁流',
    icon: '🛡️',
    description: '任务完成→自动触发测试→通过才标记✅',
    priority: 'P0',
    priorityType: 'danger',
    status: 'pending',
    statusType: 'warning',
    statusText: '待启用'
  },
  {
    name: '跨项目依赖管理',
    icon: '🔗',
    description: '检测前置任务完成→自动触发下游启动',
    priority: 'P1',
    priorityType: 'warning',
    status: 'draft',
    statusType: 'info',
    statusText: '待创建'
  },
  {
    name: '异常升级流',
    icon: '⚠️',
    description: '任务超时/阻塞→逐级上报',
    priority: 'P1',
    priorityType: 'warning',
    status: 'draft',
    statusType: 'info',
    statusText: '待创建'
  },
  {
    name: '每日站会摘要',
    icon: '📋',
    description: '自动生成今日/昨日工作汇总',
    priority: 'P1',
    priorityType: 'warning',
    status: 'draft',
    statusType: 'info',
    statusText: '待创建'
  }
])

const quickActions = ref<QuickAction[]>([
  {
    name: '创建新项目',
    icon: '➕',
    description: '快速启动项目派发流程',
    type: 'primary',
    handler: () => {
      ElMessage.info('项目创建功能开发中...')
    }
  },
  {
    name: '手动巡检',
    icon: '🔍',
    description: '立即执行一次进度巡检',
    type: 'success',
    handler: () => {
      ElMessage.info('进度巡检功能待启用...')
    }
  },
  {
    name: '生成报告',
    icon: '📄',
    description: '生成项目状态报告',
    type: 'warning',
    handler: () => {
      ElMessage.info('报告生成功能开发中...')
    }
  }
])

function triggerWorkflow(row: Workflow) {
  ElMessage.success(`已触发工作流: ${row.name}`)
}

function enableWorkflow(row: Workflow) {
  ElMessage.success(`正在启用工作流: ${row.name}`)
}
</script>

<style scoped>
.tools-page {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 24px;
}

.page-header h2 {
  margin: 0 0 8px 0;
  font-size: 24px;
  color: #303133;
}

.subtitle {
  margin: 0;
  color: #909399;
  font-size: 14px;
}

.section-card {
  margin-bottom: 24px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-header h3 {
  margin: 0;
  font-size: 16px;
  color: #303133;
}

/* Skills 卡片 */
.skill-card {
  height: 100%;
  text-align: center;
  cursor: pointer;
  transition: transform 0.2s;
}

.skill-card:hover {
  transform: translateY(-4px);
}

.skill-icon {
  font-size: 32px;
  margin-bottom: 8px;
}

.skill-name {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 4px;
}

.skill-desc {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
  line-height: 1.4;
}

.skill-tags {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 4px;
  margin-bottom: 8px;
}

.skill-tag {
  font-size: 10px !important;
}

.skill-status {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
  display: inline-block;
}

.status-active {
  background: #f0f9eb;
  color: #67c23a;
}

/* 工作流 */
.workflow-icon {
  font-size: 20px;
}

.workflow-name {
  font-weight: 500;
  color: #303133;
}

/* 快捷操作 */
.quick-action-btn {
  width: 100%;
  height: auto;
  padding: 16px;
  text-align: left;
  display: flex;
  align-items: center;
  gap: 12px;
}

.btn-icon {
  font-size: 24px;
}

.btn-text {
  flex: 1;
}

.btn-name {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 2px;
}

.btn-desc {
  font-size: 12px;
  color: #909399;
}
</style>
