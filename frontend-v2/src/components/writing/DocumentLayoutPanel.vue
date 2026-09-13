<template>
  <div v-if="layout" class="layout-panel">
    <section class="layout-card layout-summary">
      <header>
        <div><span>当前 Word 输出模板</span><h3>{{ layout.profile?.name || '尚未选择真实 Word 模板' }}</h3></div>
        <el-tag :type="statusType" effect="plain">{{ statusLabel }}</el-tag>
      </header>
      <div class="layout-version-line">
        <strong>{{ layout.display.content }} · {{ layout.display.template }} · {{ layout.display.delivery }} · {{ publicationLabel }}</strong>
        <small v-if="layout.profile">来源：{{ layout.profile.authority_source.document_title || layout.profile.authority_source.filename || '已登记 Word' }} · {{ shortHash(layout.profile.template_sha256) }}</small>
      </div>
      <el-alert v-if="layout.binding.status === 'stale'" :title="`交付稿需要重新生成：${(layout.binding.changed_reasons || []).join('、') || '正文或模板已变化'}`" type="error" :closable="false" show-icon />
      <el-alert v-if="layout.profile" title="正文只提供内容；页面、样式、页眉页脚、表格与编号均以选中的真实 Word 模板为准。" type="info" :closable="false" show-icon />
      <div class="layout-actions">
        <input ref="referenceInput" type="file" accept=".docx" hidden @change="chooseReference" />
        <el-button @click="referenceInput?.click()">上传新的 Word 模板</el-button>
        <el-button :disabled="!layout.profile" type="primary" :loading="busy === 'docx'" @click="$emit('export', 'docx')">生成 Word</el-button>
        <el-button :disabled="!layout.profile" :loading="busy === 'pdf'" @click="$emit('export', 'pdf')">预览同源 PDF</el-button>
        <el-button v-if="layout.binding.latest_delivery?.docx_path" text @click="$emit('download-delivery', 'docx')">下载当前交付稿</el-button>
      </div>
    </section>

    <section class="layout-card template-library">
      <header>
        <div><span>Word 输出模板</span><h3>历史 Word 版式库</h3></div>
        <el-radio-group v-model="templateScope" size="small">
          <el-radio-button value="same">{{ currentTypeLabel }}优先（{{ layout.template_catalog?.same_type_count || 0 }}）</el-radio-button>
          <el-radio-button value="all">全部模板（{{ layout.template_catalog?.total_count || 0 }}）</el-radio-button>
        </el-radio-group>
      </header>
      <p class="template-note">默认展示历史 Word 的前三个真实页面；后续可按实际页面标记为封面、目录/前置页或正文。没有独立目录页时不会虚构目录。</p>
      <div v-if="visibleProfiles.length" class="template-grid">
        <article v-for="profile in visibleProfiles" :key="profile.id" class="template-card" :class="{ selected: selectedProfile === profile.id }">
          <div class="template-card-head">
            <div><strong>{{ profile.name }}</strong><small>{{ documentTypeLabel(profile) }} · {{ profile.version }}</small></div>
            <el-tag size="small" :type="selectedProfile === profile.id ? 'success' : 'info'" effect="plain">{{ selectedProfile === profile.id ? '当前选用' : '可选' }}</el-tag>
          </div>
          <div class="template-pages">
            <figure v-for="page in profile.preview?.showcase_pages || []" :key="`${profile.id}-${page.page}`">
              <img v-if="templatePreviewUrls[`${profile.id}:${page.page}`]" :src="templatePreviewUrls[`${profile.id}:${page.page}`]" :alt="`${profile.name} 第${page.page}页`" />
              <div v-else class="template-page-empty">真实预览待加载</div>
              <figcaption>第 {{ page.page }} 页 · {{ page.label }}</figcaption>
            </figure>
            <el-empty v-if="!profile.preview?.showcase_pages?.length" description="未生成真实预览" :image-size="38" />
          </div>
          <div class="template-meta">来源：{{ profile.authority_source.document_title || profile.authority_source.filename || '历史 Word' }}</div>
          <div class="template-card-actions">
            <el-button text :disabled="!profile.preview?.pdf_path" @click="$emit('preview-template', profile.id)">查看完整 Word 样张</el-button>
            <el-button :type="selectedProfile === profile.id ? 'success' : 'primary'" plain :disabled="selectedProfile === profile.id" @click="selectProfile(profile.id)">{{ selectedProfile === profile.id ? '已选择' : '选择此模板' }}</el-button>
          </div>
        </article>
      </div>
      <el-empty v-else description="该文种尚未上传真实 Word 模板；请先上传现有 Word，系统不会用通用论文格式替代。" :image-size="62" />
    </section>

    <div class="layout-columns">
      <section class="layout-card">
        <header><div><span>前置内容</span><h3>摘要、关键词与目录</h3></div></header>
        <div class="frontmatter-list"><div v-for="item in frontmatterItems" :key="item.key"><span>{{ item.label }}</span><el-tag size="small" :type="item.value === 'ready' || item.value === 'generated' ? 'success' : 'warning'" effect="plain">{{ frontmatterLabel(item.value) }}</el-tag></div></div>
      </section>
      <section class="layout-card">
        <header><div><span>模板合同</span><h3>生成约束</h3></div></header>
        <div class="rule-grid"><div><span>页面与字体</span><strong>来自选中 Word，不套用通用规则</strong></div><div><span>页眉页脚</span><strong>与原 Word 同源保留</strong></div><div><span>模板版本</span><strong>{{ layout.profile?.version || '待选择' }}</strong></div><div><span>交付状态</span><strong>{{ layout.binding.status === 'stale' ? '正文或模板已更新，需重排' : '模板与正文已绑定' }}</strong></div></div>
      </section>
    </div>

    <section class="layout-card audit-card">
      <header><div><span>独立质量指标</span><h3>排版合规度</h3></div><strong class="audit-score">{{ layout.audit ? layout.audit.compliance_score : '待审计' }}</strong></header>
      <div v-if="layout.audit" class="audit-checks"><div v-for="check in layout.audit.checks" :key="check.key"><el-tag size="small" :type="check.passed ? 'success' : check.severity === 'blocker' ? 'danger' : 'warning'" effect="plain">{{ check.passed ? '通过' : check.severity === 'blocker' ? '阻断' : '警告' }}</el-tag><span>{{ check.label }}</span><small>{{ check.detail }}</small></div></div>
      <el-empty v-else description="生成候选 Word 后将执行模板一致性审计" :image-size="56" />
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { DocumentLayoutProfile, DocumentLayoutState } from '@/api/writing'

const props = defineProps<{ layout?: DocumentLayoutState; busy?: string; saving?: boolean; templatePreviewUrls?: Record<string, string> }>()
const emit = defineEmits<{ save: [payload: { profile_id?: string; layout_revision: string; cover: Record<string, string> }]; export: [format: 'docx' | 'pdf']; 'preview-template': [profileId: string]; 'download-delivery': [format: 'docx' | 'pdf']; 'upload-reference': [file: File] }>()
const selectedProfile = ref('')
const templateScope = ref<'same' | 'all'>('same')
const referenceInput = ref<HTMLInputElement>()
watch(() => props.layout, value => { selectedProfile.value = value?.binding.profile_id || value?.profile?.id || '' }, { immediate: true, deep: true })

const documentType = computed(() => props.layout?.template_catalog?.document_type || '')
const currentTypeLabel = computed(() => ({ lesson_plan: '教案', course_plan: '课程教学计划', thesis: '论文', practice_guide: '实作指导书', assessment: '考核方案' }[documentType.value] || '当前文种'))
const visibleProfiles = computed(() => (props.layout?.profiles || []).filter(profile => templateScope.value === 'all' || profile.applies_to.document_types.includes(documentType.value)))
const templatePreviewUrls = computed(() => props.templatePreviewUrls || {})
const statusType = computed(() => props.layout?.binding.status === 'aligned' ? 'success' : props.layout?.binding.status === 'stale' ? 'danger' : 'warning')
const statusLabel = computed(() => ({ aligned: '已绑定', stale: '需重排', missing: '未绑定' }[props.layout?.binding.status || 'missing']))
const publicationLabel = computed(() => ({ draft: '草稿', review: '评审中', approved: '已确认', published: '已发布' }[props.layout?.display.publication_status || 'draft'] || props.layout?.display.publication_status))
const frontmatterItems = computed(() => [{ key: 'abstract_zh', label: '中文摘要', value: props.layout?.frontmatter.abstract_zh || 'pending' }, { key: 'abstract_en', label: '英文摘要', value: props.layout?.frontmatter.abstract_en || 'pending' }, { key: 'keywords_zh', label: '中文关键词', value: props.layout?.frontmatter.keywords_zh || 'pending' }, { key: 'keywords_en', label: '英文关键词', value: props.layout?.frontmatter.keywords_en || 'pending' }, { key: 'toc', label: '目录', value: props.layout?.frontmatter.toc || 'generated' }])
function selectProfile(profileId: string) { selectedProfile.value = profileId; emit('save', { profile_id: profileId, layout_revision: props.layout?.binding.layout_revision || 'R1', cover: {} }) }
function chooseReference(event: Event) { const input = event.target as HTMLInputElement; const file = input.files?.[0]; if (file) emit('upload-reference', file); input.value = '' }
function documentTypeLabel(profile: DocumentLayoutProfile) { return profile.applies_to.document_types.map(type => ({ lesson_plan: '教案', course_plan: '课程教学计划', thesis: '论文', practice_guide: '实作指导书', assessment: '考核方案' }[type] || type)).join(' / ') }
function frontmatterLabel(value: string) { return value === 'ready' ? '已同步' : value === 'generated' ? '自动生成' : '待同步' }
function shortHash(value: string) { return value ? `${value.slice(0, 12)}…${value.slice(-8)}` : '未登记' }
</script>

<style scoped>
.layout-panel { display:grid; gap:14px; }.layout-card { border:1px solid var(--line-color); border-radius:6px; background:var(--card-bg); padding:15px; }.layout-card > header,.template-card-head,.template-card-actions { display:flex; align-items:center; justify-content:space-between; gap:12px; }.layout-card header span,.rule-grid span,.frontmatter-list span,.template-card small,.template-meta { color:var(--text-secondary); font-size:11px; }.layout-card h3 { margin:3px 0 0; color:var(--text-primary); font-size:15px; }.layout-version-line { display:grid; gap:5px; margin-bottom:12px; }.layout-version-line small { color:var(--text-secondary); overflow-wrap:anywhere; }.layout-actions { display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; }.template-note { margin:0 0 12px; color:var(--text-secondary); line-height:1.6; }.template-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:12px; }.template-card { border:1px solid var(--line-color); border-radius:6px; padding:12px; display:grid; gap:10px; }.template-card.selected { border-color:var(--el-color-success); box-shadow:0 0 0 1px var(--el-color-success-light-5); }.template-card-head > div { display:grid; gap:4px; }.template-pages { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:7px; }.template-pages figure { margin:0; min-width:0; }.template-pages img,.template-page-empty { display:block; width:100%; height:145px; object-fit:cover; object-position:top; border:1px solid var(--line-color); border-radius:3px; background:#fff; }.template-page-empty { display:grid; place-items:center; color:var(--text-secondary); font-size:11px; text-align:center; }.template-pages figcaption { margin-top:4px; color:var(--text-secondary); font-size:10px; line-height:1.35; }.template-meta { overflow-wrap:anywhere; }.layout-columns { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }.frontmatter-list { display:grid; }.frontmatter-list > div { display:flex; align-items:center; justify-content:space-between; padding:10px 0; border-bottom:1px solid var(--line-color); }.rule-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:1px; background:var(--line-color); }.rule-grid > div { display:grid; gap:5px; padding:12px; background:var(--card-bg); }.rule-grid strong { color:var(--text-primary); font-size:12px; }.audit-score { color:var(--el-color-success); font-size:28px; }.audit-checks { display:grid; gap:8px; }.audit-checks > div { display:grid; grid-template-columns:auto 130px minmax(0,1fr); align-items:center; gap:8px; }.audit-checks small { color:var(--text-secondary); } @media (max-width:900px) { .layout-columns,.rule-grid { grid-template-columns:1fr; } } @media (max-width:640px) { .template-pages { grid-template-columns:1fr; }.template-pages img,.template-page-empty { height:180px; }.audit-checks > div { grid-template-columns:auto minmax(0,1fr); }.audit-checks small { grid-column:2; } }
</style>
