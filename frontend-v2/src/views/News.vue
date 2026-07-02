<template>
  <div class="news-page">
    <el-card class="panel" shadow="hover">
      <template #header>
        <div class="panel-header">
          <div>
            <span>新闻资讯</span>
            <div class="muted">{{ news.length }} 条 · {{ categoryCount }} 个分类</div>
          </div>
          <el-input v-model="keyword" size="small" placeholder="搜索标题、来源或摘要" clearable style="width: 300px" />
        </div>
      </template>

      <el-row :gutter="14">
        <el-col v-for="item in filteredNews" :key="item.id" :xs="24" :md="12">
          <el-card class="news-card" shadow="hover">
            <div class="news-head">
              <el-tag size="small" :type="priorityType(item.priority)">{{ item.category || '资讯' }}</el-tag>
              <span>{{ formatDate(item.published_at) }}</span>
            </div>
            <h3>{{ item.title }}</h3>
            <p>{{ item.summary || '暂无摘要' }}</p>
            <div class="news-foot">
              <span>{{ item.source || '未知来源' }}</span>
              <el-link v-if="item.url" :href="item.url" target="_blank" type="primary">查看原文</el-link>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getNews, type NewsItem } from '@/api/openclaw'

const news = ref<NewsItem[]>([])
const keyword = ref('')

const categoryCount = computed(() => new Set(news.value.map(item => item.category || '资讯')).size)
const filteredNews = computed(() => {
  const key = keyword.value.trim().toLowerCase()
  const rows = key
    ? news.value.filter(item => `${item.title} ${item.summary} ${item.source}`.toLowerCase().includes(key))
    : news.value
  return rows.slice(0, 80)
})

function priorityType(priority?: string) {
  if (priority === 'high') return 'danger'
  if (priority === 'medium') return 'warning'
  return 'info'
}

function formatDate(value?: string) {
  if (!value) return '未知时间'
  return value.replace('T', ' ').slice(0, 16)
}

async function loadNews() {
  try {
    const data = await getNews(100)
    news.value = data.news
  } catch {
    ElMessage.error('新闻资讯加载失败')
  }
}

onMounted(loadNews)
</script>

<style scoped>
.panel,
.news-card {
  border-radius: 8px;
}

.panel-header,
.news-head,
.news-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.muted,
.news-head span,
.news-foot span {
  color: #909399;
  font-size: 13px;
}

.news-card {
  margin-bottom: 14px;
  min-height: 210px;
}

.news-card h3 {
  color: #303133;
  font-size: 16px;
  line-height: 1.5;
  margin: 12px 0 8px;
}

.news-card p {
  color: #606266;
  line-height: 1.7;
  margin: 0 0 14px;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
