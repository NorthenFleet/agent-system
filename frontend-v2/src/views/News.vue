<template>
  <div class="news-page">
    <!-- 页面标题 + 统计 -->
    <div class="page-header">
      <div class="page-title">
        <h1>📰 新闻资讯</h1>
        <p class="page-desc">{{ news.length }} 条 · {{ categoryCount }} 个分类</p>
      </div>
      <el-input
        v-model="keyword"
        size="small"
        placeholder="搜索标题、来源或摘要"
        clearable
        class="search-input"
      />
    </div>

    <!-- Loading 状态 -->
    <div v-if="loading" class="loading-wrapper">
      <el-icon class="loading-spinner" :size="40"><Loading /></el-icon>
      <p class="loading-text">加载新闻资讯...</p>
    </div>

    <!-- 空状态 -->
    <el-empty
      v-else-if="filteredNews.length === 0 && !loading"
      description="暂无新闻资讯"
      :image-size="100"
    />

    <!-- 资讯卡片网格 -->
    <div v-else class="news-grid">
      <el-card
        v-for="item in filteredNews"
        :key="item.id"
        class="news-card"
        shadow="hover"
      >
        <div class="news-head">
          <el-tag size="small" :type="priorityType(item.priority)">{{ item.category || '资讯' }}</el-tag>
          <span class="news-date">{{ formatDate(item.published_at) }}</span>
        </div>
        <h3>{{ item.title }}</h3>
        <p>{{ item.summary || '暂无摘要' }}</p>
        <div class="news-foot">
          <span>{{ item.source || '未知来源' }}</span>
          <el-link v-if="item.url" :href="item.url" target="_blank" type="primary">查看原文</el-link>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getNews, type NewsItem } from '@/api/openclaw'

const news = ref<NewsItem[]>([])
const keyword = ref('')
const loading = ref(false)

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
  loading.value = true
  try {
    const data = await getNews(100)
    news.value = data.news
  } catch {
    ElMessage.error('新闻资讯加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(loadNews)
</script>

<style scoped>
.news-page {
  padding: 16px;
  min-height: 100%;
}

/* ===================== 页面头部 ===================== */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 12px;
}

.page-title h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 800;
  color: #e0e0e0;
}

.page-desc {
  margin: 4px 0 0;
  color: #888;
  font-size: 13px;
}

.search-input {
  width: 300px;
}

/* ===================== Loading ===================== */
.loading-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 0;
  color: #888;
}

.loading-spinner {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.loading-text {
  margin-top: 12px;
  font-size: 14px;
}

/* ===================== 卡片网格 ===================== */
.news-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

.news-card {
  border-radius: 10px;
  border: 1px solid #333;
  background: #1a1a1a;
  transition: transform 0.15s, box-shadow 0.15s;
  min-height: 210px;
}

.news-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 24px rgba(64, 158, 255, 0.15);
  border-color: #409eff;
}

:deep(.el-card__body) {
  padding: 16px;
}

/* 卡片头部 */
.news-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.news-date {
  color: #888;
  font-size: 13px;
}

.news-card h3 {
  color: #e0e0e0;
  font-size: 16px;
  line-height: 1.5;
  margin: 12px 0 8px;
}

.news-card p {
  color: #b0b0b0;
  line-height: 1.7;
  margin: 0 0 14px;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 卡片底部 */
.news-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-top: 8px;
  border-top: 1px solid #2a2a2a;
  font-size: 12px;
}

.news-foot span {
  color: #888;
  font-size: 13px;
}

/* ===================== 响应式 ===================== */
@media (max-width: 768px) {
  .news-page {
    padding: 12px;
  }

  .news-grid {
    grid-template-columns: 1fr;
  }

  .page-title h1 {
    font-size: 18px;
  }

  .search-input {
    width: 100%;
  }
}

@media (max-width: 480px) {
  .page-header {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
