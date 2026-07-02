<template>
  <div class="community-page">
    <el-row :gutter="16" class="stats-row">
      <el-col :span="6"><el-card class="stat-card" shadow="hover"><span>消息</span><strong>{{ messages.length }}</strong></el-card></el-col>
      <el-col :span="6"><el-card class="stat-card" shadow="hover"><span>主题</span><strong>{{ topics.length }}</strong></el-card></el-col>
      <el-col :span="6"><el-card class="stat-card" shadow="hover"><span>活跃主题</span><strong>{{ stats.active_topics || 0 }}</strong></el-card></el-col>
      <el-col :span="6"><el-card class="stat-card" shadow="hover"><span>活跃智能体</span><strong>{{ stats.active_agents || uniqueAgents }}</strong></el-card></el-col>
    </el-row>

    <el-row :gutter="18">
      <el-col :span="12">
        <el-card class="panel" shadow="hover">
          <template #header>
            <div class="panel-header">
              <span>活动消息</span>
              <el-button size="small" type="primary" @click="loadCommunity">刷新</el-button>
            </div>
          </template>
          <div class="message-list">
            <div v-for="message in messages" :key="messageKey(message)" class="message-card">
              <div class="message-head">
                <strong>{{ message.agent_name || message.agent_id }}</strong>
                <span>{{ message.time_str || '未知时间' }}</span>
              </div>
              <p>{{ message.message || drinkText(message) }}</p>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card class="panel" shadow="hover">
          <template #header>
            <div class="panel-header">
              <span>讨论主题</span>
              <el-tag>{{ topics.length }} 个</el-tag>
            </div>
          </template>
          <div class="topic-list">
            <div v-for="topic in topics" :key="topic.id" class="topic-card">
              <div class="topic-title">{{ topic.title }}</div>
              <div class="muted">{{ topic.content || '暂无内容' }}</div>
              <div class="topic-meta">
                <span>{{ topic.agent_emoji || '' }} {{ topic.agent_name || '未知' }}</span>
                <span>{{ topic.post_count || 0 }} 回复 · {{ topic.views || 0 }} 浏览</span>
              </div>
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
import { getBarMessages, getCommunityStats, getForumTopics, type BarMessage, type ForumTopic } from '@/api/openclaw'

const messages = ref<BarMessage[]>([])
const topics = ref<ForumTopic[]>([])
const stats = ref<Record<string, number>>({})

const uniqueAgents = computed(() => new Set(messages.value.map(message => message.agent_id)).size)

function drinkText(message: BarMessage) {
  return message.action === 'drink' ? `领取饮品：${message.drink || '未知'}` : '暂无消息'
}

function messageKey(message: BarMessage) {
  return `${message.agent_id}-${message.timestamp}-${message.message || message.action || ''}`
}

async function loadCommunity() {
  try {
    const [messageData, topicData, statData] = await Promise.all([
      getBarMessages(80),
      getForumTopics(),
      getCommunityStats().catch(() => ({})),
    ])
    messages.value = messageData.messages.slice().reverse()
    topics.value = topicData.topics
    stats.value = statData as Record<string, number>
  } catch {
    ElMessage.error('社区数据加载失败')
  }
}

onMounted(loadCommunity)
</script>

<style scoped>
.community-page {
  display: grid;
  gap: 16px;
}

.stat-card,
.panel {
  border-radius: 8px;
}

.stat-card :deep(.el-card__body) {
  display: grid;
  gap: 8px;
}

.stat-card span,
.muted,
.message-head span,
.topic-meta {
  color: #909399;
  font-size: 13px;
}

.stat-card strong {
  color: #303133;
  font-size: 24px;
}

.panel-header,
.message-head,
.topic-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.message-list,
.topic-list {
  display: grid;
  gap: 12px;
  max-height: 640px;
  overflow: auto;
}

.message-card,
.topic-card {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 12px;
}

.message-card p {
  margin: 8px 0 0;
  color: #606266;
  line-height: 1.6;
}

.topic-title {
  color: #303133;
  font-weight: 700;
  margin-bottom: 6px;
}
</style>
