<template>
  <div class="file-preview">
    <!-- 加载状态 -->
    <div v-if="loading" class="preview-loading">
      <el-icon class="is-loading"><Loading /></el-icon>
      <span>加载中...</span>
    </div>

    <!-- 错误状态 -->
    <div v-else-if="error" class="preview-error">
      <el-icon><WarningFilled /></el-icon>
      <p>{{ error }}</p>
      <el-button size="small" @click="retry">重试</el-button>
    </div>

    <!-- 空状态 -->
    <el-empty v-else-if="!fileData" description="点击左侧目录选择文件" />

    <!-- 文件内容 -->
    <div v-else class="preview-content">
      <!-- 文件头信息 -->
      <div class="file-header">
        <h3 class="file-title">{{ fileData.name }}</h3>
        <div class="file-meta">
          <el-tag size="small" type="info">{{ fileData.ext }}</el-tag>
          <span v-if="fileData.size" class="meta-item">{{ formatSize(fileData.size) }}</span>
          <span v-if="fileData.mtime" class="meta-item">更新于 {{ formatDate(fileData.mtime) }}</span>
        </div>
      </div>

      <!-- Markdown 渲染 -->
      <div
        v-if="fileData.ext === 'md'"
        class="markdown-body"
        v-html="renderedMarkdown"
      />

      <!-- 图片预览 -->
      <div v-else-if="isImage(fileData.ext)" class="image-preview">
        <img :src="getImageUrl(fileData.path)" :alt="fileData.name" />
      </div>

      <!-- 文本文件 -->
      <pre v-else-if="isText(fileData.ext)" class="text-preview">{{ fileData.content }}</pre>

      <!-- 不支持的格式 -->
      <div v-else class="unsupported-preview">
        <el-icon :size="48"><Files /></el-icon>
        <p>此文件类型（.{{ fileData.ext }}）暂不支持预览</p>
        <p class="hint">请在本地 Obsidian 中查看</p>
      </div>

      <!-- 标签 -->
      <div v-if="fileData.tags && fileData.tags.length" class="tags-section">
        <span class="section-label">标签</span>
        <div class="tags-list">
          <el-tag
            v-for="tag in fileData.tags"
            :key="tag"
            size="small"
            type="success"
            effect="plain"
            class="tag-item"
          >#{{ tag }}</el-tag>
        </div>
      </div>

      <!-- 关联文档（双向链接） -->
      <div v-if="backlinks.length" class="backlinks-section">
        <span class="section-label">关联文档 ({{ backlinks.length }})</span>
        <div class="backlinks-list">
          <el-button
            v-for="(link, idx) in backlinks"
            :key="idx"
            text
            size="small"
            class="backlink-btn"
            @click="navigateToLink(link)"
          >
            <el-icon><Link /></el-icon>
            {{ link.link }}
            <span class="backlink-path">{{ link.name }}</span>
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import MarkdownIt from 'markdown-it'
import { Loading, WarningFilled, Files, Link } from '@element-plus/icons-vue'
import { getFile, getBacklinks, type FileContent } from '@/api/knowledge'

const emit = defineEmits<{
  (e: 'navigate', path: string): void
}>()

const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true,
  breaks: true
})

const loading = ref(false)
const error = ref('')
const fileData = ref<FileContent | null>(null)
const backlinks = ref<{ path: string; name: string; link: string }[]>([])

const currentPath = ref('')

const renderedMarkdown = computed(() => {
  if (!fileData.value) return ''
  // 将 [[wikilink]] 转换为可点击的 span
  let content = fileData.value.content
  content = content.replace(/\[\[([^\]]+)\]\]/g, (_match, linkText) => {
    return `<span class="wikilink" data-link="${linkText}">[[${linkText}]]</span>`
  })
  return md.render(content)
})

const isImage = (ext?: string) => ['png', 'jpg', 'jpeg', 'svg', 'gif', 'webp'].includes(ext || '')
const isText = (ext?: string) => ['txt', 'json', 'yaml', 'yml', 'csv', 'py', 'js', 'ts', 'html', 'xml'].includes(ext || '')

function getImageUrl(path: string) {
  return `/api/knowledge/file?path=${encodeURIComponent(path)}`
}

function formatSize(bytes: number) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function formatDate(iso: string) {
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

async function loadFile(path: string) {
  currentPath.value = path
  loading.value = true
  error.value = ''
  fileData.value = null
  backlinks.value = []

  try {
    fileData.value = await getFile(path)
    // 加载反向链接
    if (fileData.value.ext === 'md') {
      backlinks.value = await getBacklinks(path)
    }
  } catch (e: any) {
    error.value = e.message || '文件加载失败'
  } finally {
    loading.value = false
  }
}

function navigateToLink(link: { path: string; name: string; link: string }) {
  if (link.path) {
    emit('navigate', link.path)
  }
}

function retry() {
  if (currentPath.value) {
    loadFile(currentPath.value)
  }
}

defineExpose({ loadFile })
</script>

<style scoped>
.file-preview {
  height: 100%;
  overflow: auto;
  padding: 16px;
}

.preview-loading,
.preview-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 200px;
  gap: 12px;
  color: #909399;
}

.preview-error {
  color: #f56c6c;
}

.preview-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.file-header {
  border-bottom: 1px solid #e4e7ed;
  padding-bottom: 12px;
}

.file-title {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 600;
  color: #303133;
  word-break: break-word;
}

.file-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: #909399;
}

.meta-item {
  white-space: nowrap;
}

/* Markdown 渲染 */
.markdown-body {
  line-height: 1.7;
  color: #303133;
  font-size: 14px;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  margin-top: 24px;
  margin-bottom: 12px;
  font-weight: 600;
  border-bottom: 1px solid #eaecef;
  padding-bottom: 8px;
}

.markdown-body :deep(h1) { font-size: 24px; }
.markdown-body :deep(h2) { font-size: 20px; }
.markdown-body :deep(h3) { font-size: 16px; }

.markdown-body :deep(p) {
  margin: 12px 0;
}

.markdown-body :deep(code) {
  background: #f5f5f5;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
  color: #e83e8c;
}

.markdown-body :deep(pre) {
  background: #f6f8fa;
  padding: 16px;
  border-radius: 8px;
  overflow-x: auto;
}

.markdown-body :deep(pre code) {
  background: transparent;
  padding: 0;
  color: #303133;
}

.markdown-body :deep(blockquote) {
  border-left: 4px solid #409eff;
  padding: 8px 16px;
  margin: 12px 0;
  background: #f4f8fb;
  border-radius: 0 4px 4px 0;
  color: #606266;
}

.markdown-body :deep(img) {
  max-width: 100%;
  border-radius: 8px;
}

.markdown-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 12px 0;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid #e4e7ed;
  padding: 8px 12px;
  text-align: left;
}

.markdown-body :deep(th) {
  background: #f5f7fa;
  font-weight: 600;
}

/* Wikilink */
.markdown-body :deep(.wikilink) {
  color: #409eff;
  cursor: pointer;
  background: rgba(64, 158, 255, 0.1);
  padding: 2px 6px;
  border-radius: 4px;
  text-decoration: none;
  font-weight: 500;
}

.markdown-body :deep(.wikilink:hover) {
  background: rgba(64, 158, 255, 0.2);
  text-decoration: underline;
}

/* 图片预览 */
.image-preview {
  text-align: center;
}

.image-preview img {
  max-width: 100%;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

/* 文本预览 */
.text-preview {
  background: #f6f8fa;
  padding: 16px;
  border-radius: 8px;
  overflow-x: auto;
  font-size: 13px;
  line-height: 1.5;
  font-family: 'Fira Code', 'Consolas', monospace;
}

/* 不支持的格式 */
.unsupported-preview {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 16px;
  color: #909399;
}

.unsupported-preview p {
  margin: 8px 0 0;
}

.hint {
  font-size: 12px;
  color: #c0c4cc;
}

/* 标签 */
.tags-section,
.backlinks-section {
  border-top: 1px solid #e4e7ed;
  padding-top: 12px;
}

.section-label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 8px;
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tag-item {
  cursor: pointer;
}

/* 关联文档 */
.backlinks-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.backlink-btn {
  justify-content: flex-start;
  text-align: left;
  padding: 4px 8px;
  border-radius: 4px;
}

.backlink-btn:hover {
  background: rgba(64, 158, 255, 0.08);
}

.backlink-path {
  font-size: 11px;
  color: #909399;
  margin-left: 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 200px;
}
</style>
