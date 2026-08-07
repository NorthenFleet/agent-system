<template>
  <div v-if="layout" class="layout-panel">
    <section class="layout-card layout-summary">
      <header>
        <div><span>当前排版模板</span><h3>{{ layout.profile?.name || '尚未绑定模板' }}</h3></div>
        <el-tag :type="statusType" effect="plain">{{ statusLabel }}</el-tag>
      </header>
      <div class="layout-version-line">
        <strong>{{ layout.display.content }} · {{ layout.display.template }} · {{ layout.display.delivery }} · {{ publicationLabel }}</strong>
        <small v-if="layout.profile">权威源 SHA-256：{{ shortHash(layout.profile.authority_source.sha256) }} · 模板 SHA-256：{{ shortHash(layout.profile.template_sha256) }}</small>
      </div>
      <el-alert
        v-if="abstractPending"
        title="中文摘要、英文摘要或关键词尚未同步；当前可以生成格式校样，但只能保持草稿。"
        type="warning"
        :closable="false"
        show-icon
      />
      <el-alert
        v-if="layout.binding.status === 'stale'"
        :title="`排版结果需要重新生成：${(layout.binding.changed_reasons || []).join('、') || '正文或模板已变化'}`"
        type="error"
        :closable="false"
        show-icon
      />
      <div class="layout-actions">
        <el-select v-model="selectedProfile" placeholder="选择排版模板" @change="emitSave">
          <el-option v-for="profile in layout.profiles" :key="profile.id" :label="`${profile.name} · ${profile.version}`" :value="profile.id" />
        </el-select>
        <el-button :disabled="!layout.sample.pdf_path" @click="$emit('preview-sample')">预览模板样张</el-button>
        <el-button type="primary" :loading="busy === 'docx'" @click="$emit('export', 'docx')">生成 Word</el-button>
        <el-button :loading="busy === 'pdf'" @click="$emit('export', 'pdf')">预览同源 PDF</el-button>
        <el-button v-if="layout.binding.latest_delivery?.docx_path" text @click="$emit('download-delivery', 'docx')">下载当前交付稿</el-button>
      </div>
    </section>

    <div class="layout-columns">
      <section class="layout-card">
        <header><div><span>可编辑元数据</span><h3>封面信息</h3></div><el-button type="primary" plain :loading="saving" @click="emitSave">保存封面</el-button></header>
        <el-form label-position="top" class="cover-form">
          <el-form-item label="论文题目"><el-input v-model="cover.title" /></el-form-item>
          <div class="cover-row">
            <el-form-item label="作者"><el-input v-model="cover.author" /></el-form-item>
            <el-form-item label="导师"><el-input v-model="cover.advisor" /></el-form-item>
            <el-form-item label="导师职称"><el-input v-model="cover.advisor_title" /></el-form-item>
          </div>
          <div class="cover-row two">
            <el-form-item label="单位"><el-input v-model="cover.institution" /></el-form-item>
            <el-form-item label="日期"><el-input v-model="cover.date" /></el-form-item>
          </div>
        </el-form>
      </section>

      <section class="layout-card">
        <header><div><span>前置页面</span><h3>摘要、关键词与目录</h3></div></header>
        <div class="frontmatter-list">
          <div v-for="item in frontmatterItems" :key="item.key"><span>{{ item.label }}</span><el-tag size="small" :type="item.value === 'ready' || item.value === 'generated' ? 'success' : 'warning'" effect="plain">{{ frontmatterLabel(item.value) }}</el-tag></div>
        </div>
      </section>
    </div>

    <section v-if="layout.profile" class="layout-card">
      <header><div><span>模板合同</span><h3>格式规则</h3></div></header>
      <div class="rule-grid">
        <div><span>页面</span><strong>A4 · 上{{ layout.profile.page.margin_top_mm }}mm · 下{{ layout.profile.page.margin_bottom_mm }}mm · 左{{ layout.profile.page.margin_left_mm }}mm · 右{{ layout.profile.page.margin_right_mm }}mm</strong></div>
        <div><span>正文</span><strong>宋体 / Times New Roman · 10.5磅 · 固定18磅</strong></div>
        <div><span>一级标题</span><strong>黑体14磅 · 另起一页</strong></div>
        <div><span>二级标题</span><strong>黑体12磅</strong></div>
        <div><span>三级标题</span><strong>宋体10.5磅加粗</strong></div>
        <div><span>页眉页脚</span><strong>封面无页码 · 后续居中 - 页码 -</strong></div>
        <div><span>图表</span><strong>图题在下、表题在上、跨页重复表头</strong></div>
        <div><span>域</span><strong>真实目录、页码、题注与交叉引用</strong></div>
      </div>
    </section>

    <section class="layout-card audit-card">
      <header>
        <div><span>独立质量指标</span><h3>排版合规度</h3></div>
        <strong class="audit-score">{{ layout.audit ? layout.audit.compliance_score : '待审计' }}</strong>
      </header>
      <div v-if="layout.audit" class="audit-checks">
        <div v-for="check in layout.audit.checks" :key="check.key">
          <el-tag size="small" :type="check.passed ? 'success' : check.severity === 'blocker' ? 'danger' : 'warning'" effect="plain">{{ check.passed ? '通过' : check.severity === 'blocker' ? '阻断' : '警告' }}</el-tag>
          <span>{{ check.label }}</span><small>{{ check.detail }}</small>
        </div>
      </div>
      <el-empty v-else description="生成Word后将自动执行排版审计" :image-size="56" />
      <div v-if="layout.binding.delivery_history?.length" class="delivery-history">
        <h4>交付历史</h4>
        <div v-for="(item, index) in [...layout.binding.delivery_history].reverse()" :key="`${item.created_at}-${index}`">
          <strong>{{ item.layout_revision || 'R1' }} · 正文v{{ item.content_version }}</strong>
          <small>{{ item.created_at }} · 合规度{{ item.audit_score }}</small>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { DocumentLayoutState } from '@/api/writing'

const props = defineProps<{ layout?: DocumentLayoutState; busy?: string; saving?: boolean }>()
const emit = defineEmits<{
  save: [payload: { profile_id?: string; layout_revision: string; cover: Record<string, string> }]
  export: [format: 'docx' | 'pdf']
  'preview-sample': []
  'download-delivery': [format: 'docx' | 'pdf']
}>()

const selectedProfile = ref('')
const cover = reactive<Record<string, string>>({ title: '', author: '', advisor: '', advisor_title: '', institution: '', date: '' })

watch(() => props.layout, value => {
  selectedProfile.value = value?.binding.profile_id || value?.profile?.id || ''
  Object.assign(cover, { title: '', author: '', advisor: '', advisor_title: '', institution: '', date: '', ...(value?.cover || {}) })
}, { immediate: true, deep: true })

const abstractPending = computed(() => ['abstract_zh', 'abstract_en', 'keywords_zh', 'keywords_en'].some(key => props.layout?.frontmatter?.[key] !== 'ready'))
const statusType = computed(() => props.layout?.binding.status === 'aligned' ? 'success' : props.layout?.binding.status === 'stale' ? 'danger' : 'warning')
const statusLabel = computed(() => ({ aligned: '已绑定', stale: '需重排', missing: '未绑定' }[props.layout?.binding.status || 'missing']))
const publicationLabel = computed(() => ({ draft: '草稿', review: '评审中', approved: '已确认', published: '已发布' }[props.layout?.display.publication_status || 'draft'] || props.layout?.display.publication_status))
const frontmatterItems = computed(() => [
  { key: 'abstract_zh', label: '中文摘要', value: props.layout?.frontmatter.abstract_zh || 'pending' },
  { key: 'abstract_en', label: '英文摘要', value: props.layout?.frontmatter.abstract_en || 'pending' },
  { key: 'keywords_zh', label: '中文关键词', value: props.layout?.frontmatter.keywords_zh || 'pending' },
  { key: 'keywords_en', label: '英文关键词', value: props.layout?.frontmatter.keywords_en || 'pending' },
  { key: 'toc', label: '三级目录', value: props.layout?.frontmatter.toc || 'generated' }
])

function emitSave() {
  emit('save', { profile_id: selectedProfile.value, layout_revision: props.layout?.binding.layout_revision || 'R1', cover: { ...cover } })
}
function frontmatterLabel(value: string) { return value === 'ready' ? '已同步' : value === 'generated' ? '自动生成' : '待同步' }
function shortHash(value: string) { return value ? `${value.slice(0, 12)}…${value.slice(-8)}` : '未登记' }
</script>

<style scoped>
.layout-panel { display: grid; gap: 14px; }
.layout-card { border: 1px solid var(--line-color); border-radius: 6px; background: var(--card-bg); padding: 15px; }
.layout-card > header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.layout-card header span, .rule-grid span, .frontmatter-list span { color: var(--text-secondary); font-size: 11px; }
.layout-card h3 { margin: 3px 0 0; color: var(--text-primary); font-size: 15px; }
.layout-version-line { display: grid; gap: 5px; margin-bottom: 12px; }
.layout-version-line strong { color: var(--text-primary); }
.layout-version-line small { color: var(--text-secondary); overflow-wrap: anywhere; }
.layout-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.layout-actions .el-select { width: min(360px, 100%); }
.layout-columns { display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(280px, .7fr); gap: 14px; }
.cover-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.cover-row.two { grid-template-columns: 1.5fr 1fr; }
.frontmatter-list { display: grid; }
.frontmatter-list > div { display: flex; align-items: center; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid var(--line-color); }
.rule-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1px; background: var(--line-color); }
.rule-grid > div { display: grid; gap: 5px; padding: 12px; background: var(--card-bg); }
.rule-grid strong { color: var(--text-primary); font-size: 12px; }
.audit-score { color: var(--el-color-success); font-size: 28px; }
.audit-checks { display: grid; gap: 8px; }
.audit-checks > div { display: grid; grid-template-columns: auto 130px minmax(0, 1fr); align-items: center; gap: 8px; }
.audit-checks small { color: var(--text-secondary); }
.delivery-history { margin-top: 16px; border-top: 1px solid var(--line-color); }
.delivery-history > div { display: flex; justify-content: space-between; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--line-color); }
.delivery-history small { color: var(--text-secondary); }
@media (max-width: 900px) { .layout-columns, .rule-grid { grid-template-columns: 1fr; } }
@media (max-width: 640px) { .cover-row, .cover-row.two { grid-template-columns: 1fr; } .audit-checks > div { grid-template-columns: auto minmax(0, 1fr); } .audit-checks small { grid-column: 2; } }
</style>
