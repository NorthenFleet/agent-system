<template>
  <div class="intelligence-page">
    <section class="page-head">
      <div>
        <h1>🌐 情报信息</h1>
        <p>面向特定领域的长期数据积累、空间态势、历史沉淀和专题分析</p>
      </div>
      <el-input
        v-model="keyword"
        class="search-input"
        clearable
        placeholder="搜索领域、数据源、位置或新闻"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
    </section>

    <nav class="topic-tabs" aria-label="情报专题视图">
      <el-tabs v-model="activeTopicTab">
        <el-tab-pane label="情报态势" name="overview" />
        <el-tab-pane label="2026 美加墨世界杯" name="world-cup-2026" />
      </el-tabs>
    </nav>

    <WorldCup2026Topic v-if="activeTopicTab === 'world-cup-2026'" />

    <template v-else>
    <section class="space-grid">
      <IntelligenceGlobe
        ref="globeRef"
        v-model:show-vessels="showAisLayer"
        v-model:show-tracks="showTrackLayer"
        v-model:show-news="showNewsLayer"
        v-model:show-events="showEventLayer"
        :items="spatialItems"
        :tracks="globeTracks"
        :active-key="activeSpatialKey"
        @select="focusSpatialItem"
      />

      <aside class="linked-panel">
        <div class="section-head compact">
          <div>
            <h2>空间与新闻联动</h2>
            <p>{{ activeSummary }}</p>
          </div>
        </div>
        <div class="linked-list">
          <article
            v-for="item in spatialItems"
            :key="item.key"
            class="linked-card"
            :class="{ active: activeSpatialKey === item.key }"
            @click="focusSpatialItem(item)"
          >
            <div>
              <strong>{{ item.name }}</strong>
              <span>{{ spatialTypeLabel(item.type) }} · {{ item.locationLabel }}</span>
            </div>
            <el-tag size="small" :type="spatialTypeTag(item.type)" effect="plain">
              {{ item.countLabel }}
            </el-tag>
          </article>
        </div>
        <div v-if="activeVessel" class="vessel-detail">
          <div class="detail-title">
            <strong>{{ activeVessel.name }}</strong>
            <el-tag size="small" :type="vesselStatusType(activeVessel.status)" effect="plain">
              {{ vesselStatusLabel(activeVessel.status) }}
            </el-tag>
          </div>
          <div class="detail-grid">
            <span>MMSI</span><strong>{{ activeVessel.mmsi }}</strong>
            <span>航速</span><strong>{{ currentVesselPoint(activeVessel)?.speed || '--' }} kn</strong>
            <span>航向</span><strong>{{ currentVesselPoint(activeVessel)?.course || '--' }}°</strong>
            <span>坐标</span><strong>{{ vesselCoordinate(activeVessel) }}</strong>
          </div>
        </div>
      </aside>
    </section>

    <section class="metric-grid">
      <article class="metric-card">
        <span>专题领域</span>
        <strong>{{ filteredDomains.length }}</strong>
        <small>{{ activeDomains }} 个持续采集中</small>
      </article>
      <article class="metric-card">
        <span>AIS 舰艇</span>
        <strong>{{ aisVessels.length }}</strong>
        <small>{{ trackPointCount }} 个历史轨迹点</small>
      </article>
      <article class="metric-card">
        <span>空间点位</span>
        <strong>{{ spatialItems.length }}</strong>
        <small>专题、事件、舰艇与新闻统一显示</small>
      </article>
      <article class="metric-card">
        <span>联动新闻</span>
        <strong>{{ relatedNews.length }}</strong>
        <small>来自新闻资讯模块的位置数据</small>
      </article>
      <article class="metric-card alert-metric">
        <span>未处置预警</span>
        <strong>{{ openAlertCount }}</strong>
        <small>{{ filteredEvents.length }} 条空间情报事件</small>
      </article>
    </section>

    <section class="section-panel event-panel">
      <div class="section-head">
        <div>
          <h2>空间情报事件</h2>
          <p>把专题、AIS 航迹和人工判断沉淀为可定位、可分级、可处置的事件时间线</p>
        </div>
        <div class="event-actions">
          <el-select v-model="eventSeverityFilter" size="small" aria-label="事件级别筛选">
            <el-option label="全部级别" value="" />
            <el-option label="紧急" value="critical" />
            <el-option label="高" value="high" />
            <el-option label="中" value="medium" />
            <el-option label="低" value="low" />
            <el-option label="信息" value="info" />
          </el-select>
          <el-select v-model="eventStatusFilter" size="small" aria-label="事件状态筛选">
            <el-option label="全部状态" value="" />
            <el-option label="待处置" value="open" />
            <el-option label="监视中" value="monitoring" />
            <el-option label="已解决" value="resolved" />
          </el-select>
          <el-button size="small" type="primary" @click="openEventDialog()">
            <el-icon><Plus /></el-icon>
            新增事件
          </el-button>
        </div>
      </div>
      <div v-if="filteredEvents.length" class="event-timeline">
        <article
          v-for="event in filteredEvents"
          :key="event.id"
          class="event-card"
          :class="[`severity-${event.severity}`, { active: activeSpatialKey === `event:${event.id}` }]"
          @click="focusEvent(event)"
        >
          <div class="event-marker"></div>
          <div class="event-body">
            <div class="event-title-line">
              <div>
                <el-tag size="small" :type="eventSeverityType(event.severity)" effect="plain">
                  {{ eventSeverityLabel(event.severity) }}
                </el-tag>
                <span>{{ formatDate(event.occurredAt) }}</span>
              </div>
              <div class="event-card-actions">
                <el-tag size="small" :type="eventStatusType(event.status)" effect="plain">
                  {{ eventStatusLabel(event.status) }}
                </el-tag>
                <el-tooltip content="编辑事件">
                  <el-button circle size="small" aria-label="编辑事件" @click.stop="openEventDialog(event)">
                    <el-icon><Edit /></el-icon>
                  </el-button>
                </el-tooltip>
              </div>
            </div>
            <h3>{{ event.title }}</h3>
            <p>{{ event.summary || '暂无事件摘要' }}</p>
            <div class="event-meta">
              <span>{{ event.locationName }}</span>
              <span v-if="event.topicName">专题：{{ event.topicName }}</span>
              <span v-if="event.vesselName">目标：{{ event.vesselName }}</span>
              <span>置信度 {{ Math.round(event.confidence * 100) }}%</span>
              <span v-if="event.assigneeAgentId">处置：{{ event.assigneeAgentId }}</span>
            </div>
            <div class="event-footer">
              <span>来源：{{ event.source }}</span>
              <el-button
                v-if="event.status !== 'resolved'"
                size="small"
                text
                type="success"
                @click.stop="resolveEvent(event)"
              >标记已解决</el-button>
            </div>
          </div>
        </article>
      </div>
      <el-empty v-else description="当前筛选条件下没有情报事件" :image-size="80" />
    </section>

    <el-dialog v-model="eventDialogOpen" :title="eventForm.id ? '编辑情报事件' : '新增情报事件'" width="760px">
      <div class="event-form">
        <el-input v-model="eventForm.title" placeholder="事件标题" />
        <el-input v-model="eventForm.summary" type="textarea" :rows="3" placeholder="事件摘要与判断依据" />
        <div class="event-form-row three">
          <el-select v-model="eventForm.severity" placeholder="严重级别">
            <el-option label="紧急" value="critical" />
            <el-option label="高" value="high" />
            <el-option label="中" value="medium" />
            <el-option label="低" value="low" />
            <el-option label="信息" value="info" />
          </el-select>
          <el-select v-model="eventForm.status" placeholder="处置状态">
            <el-option label="待处置" value="open" />
            <el-option label="监视中" value="monitoring" />
            <el-option label="已解决" value="resolved" />
          </el-select>
          <el-input v-model="eventForm.category" placeholder="事件类型" />
        </div>
        <div class="event-form-row">
          <el-select v-model="eventForm.topicId" clearable placeholder="关联专题">
            <el-option v-for="topic in domains" :key="topic.id" :label="topic.name" :value="topic.id" />
          </el-select>
          <el-select v-model="eventForm.vesselId" clearable placeholder="关联 AIS 舰艇">
            <el-option v-for="vessel in aisVessels" :key="vessel.id" :label="vessel.name" :value="vessel.id" />
          </el-select>
        </div>
        <div class="event-form-row location">
          <el-input v-model="eventForm.locationName" placeholder="位置名称" />
          <el-input v-model.number="eventForm.lat" type="number" :min="-90" :max="90" step="0.0001" placeholder="纬度" />
          <el-input v-model.number="eventForm.lng" type="number" :min="-180" :max="180" step="0.0001" placeholder="经度" />
        </div>
        <div class="event-form-row">
          <el-input v-model="eventForm.occurredAt" type="datetime-local" placeholder="发生时间" />
          <el-input v-model="eventForm.source" placeholder="来源" />
        </div>
        <div class="event-form-row">
          <el-input v-model.number="eventForm.confidence" type="number" :min="0" :max="1" step="0.05" placeholder="置信度 0-1" />
          <el-input v-model="eventForm.assigneeAgentId" placeholder="处置智能体 ID" />
        </div>
        <el-input v-model="eventForm.evidenceUrl" placeholder="证据链接（可选）" />
      </div>
      <template #footer>
        <el-button v-if="eventForm.id" type="danger" plain @click="removeEvent">删除事件</el-button>
        <el-button @click="eventDialogOpen = false">取消</el-button>
        <el-button type="primary" :loading="eventSaving" @click="submitEvent">保存</el-button>
      </template>
    </el-dialog>

    <section class="section-panel">
      <div class="section-head">
        <div>
          <h2>AIS 舰艇坐标与航迹</h2>
          <p>已接入后端 AIS 数据库，支持舰艇点、航迹线、状态、航速航向和时间点切换</p>
        </div>
        <div class="ais-actions">
          <el-button size="small" type="primary" plain @click="aisImportOpen = true">导入 AIS</el-button>
          <div class="time-control">
            <span>{{ selectedTrackTime }}</span>
            <el-slider v-model="trackTimeIndex" :min="0" :max="maxTrackIndex" :show-tooltip="false" size="small" />
          </div>
        </div>
      </div>
      <div class="vessel-grid">
        <article
          v-for="vessel in aisVessels"
          :key="vessel.id"
          class="vessel-card"
          :class="{ active: activeVesselId === vessel.id }"
          @click="focusVessel(vessel)"
        >
          <div class="vessel-head">
            <div>
              <h3>{{ vessel.name }}</h3>
              <span>{{ vessel.type }} · {{ vessel.area }}</span>
            </div>
            <el-tag size="small" :type="vesselStatusType(vessel.status)" effect="plain">
              {{ vesselStatusLabel(vessel.status) }}
            </el-tag>
          </div>
          <div class="domain-meta">
            <span>MMSI</span><strong>{{ vessel.mmsi }}</strong>
            <span>最新点</span><strong>{{ vesselCoordinate(vessel) }}</strong>
            <span>轨迹点</span><strong>{{ vessel.track.length }} 个</strong>
          </div>
        </article>
      </div>
      <div class="source-panel">
        <div class="source-head">
          <div>
            <h3>AIS 数据源</h3>
            <span>{{ aisSources.length }} 个外部源，手动同步后进入同一套去重入库流程</span>
          </div>
          <el-button size="small" plain @click="openSourceDialog()">添加源</el-button>
        </div>
        <div v-if="aisSources.length" class="source-grid">
          <article v-for="source in aisSources" :key="source.id" class="source-card">
            <div>
              <strong>{{ source.name }}</strong>
              <span>{{ source.format.toUpperCase() }} · {{ source.url }}</span>
            </div>
            <div class="source-state">
              <el-tag size="small" :type="source.last_status === 'error' ? 'danger' : source.last_status === 'ok' ? 'success' : 'info'" effect="plain">
                {{ source.last_status || 'idle' }}
              </el-tag>
              <span>{{ source.last_message || '尚未同步' }}</span>
            </div>
            <div class="source-actions">
              <el-button size="small" text @click="syncSource(source)">同步</el-button>
              <el-button size="small" text @click="openSourceDialog(source)">编辑</el-button>
              <el-button size="small" text type="danger" @click="removeSource(source)">删除源</el-button>
            </div>
          </article>
        </div>
        <el-empty v-else description="暂无 AIS 外部数据源" :image-size="72" />
      </div>
    </section>

    <el-dialog v-model="aisImportOpen" title="AIS 数据导入" width="720px">
      <div class="import-form">
        <div class="import-row">
          <el-select v-model="aisImportFormat" size="small">
            <el-option label="CSV" value="csv" />
            <el-option label="JSON" value="json" />
          </el-select>
          <el-input v-model="aisImportSource" size="small" placeholder="数据源标识" />
        </div>
        <el-input
          v-model="aisImportContent"
          type="textarea"
          :rows="12"
          placeholder="CSV: mmsi,timestamp,lat,lng,speed,course,name,vessel_type,area,status"
        />
        <div v-if="aisImportResult" class="import-result">
          <span>写入 {{ aisImportResult.inserted }} 条</span>
          <span>跳过 {{ aisImportResult.skipped }} 条</span>
          <span v-if="aisImportResult.rows !== undefined">读取 {{ aisImportResult.rows }} 行</span>
        </div>
      </div>
      <template #footer>
        <el-button @click="aisImportOpen = false">取消</el-button>
        <el-button type="primary" :loading="aisImporting" @click="submitAisImport">导入</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="sourceDialogOpen" title="AIS 外部数据源" width="720px">
      <div class="source-form">
        <el-input v-model="sourceForm.name" placeholder="数据源名称" />
        <el-input v-model="sourceForm.url" placeholder="HTTP CSV/JSON URL" />
        <div class="source-form-row">
          <el-select v-model="sourceForm.format">
            <el-option label="CSV" value="csv" />
            <el-option label="JSON" value="json" />
          </el-select>
          <el-input-number v-model="sourceForm.poll_interval_seconds" :min="60" :step="300" controls-position="right" />
        </div>
        <el-input
          v-model="sourceHeadersText"
          type="textarea"
          :rows="5"
          placeholder='请求头 JSON，例如 {"Authorization":"Bearer token"}'
        />
      </div>
      <template #footer>
        <el-button @click="sourceDialogOpen = false">取消</el-button>
        <el-button type="primary" :loading="sourceSaving" @click="saveSource">保存</el-button>
      </template>
    </el-dialog>

    <section class="section-panel">
      <div class="section-head">
        <div>
          <h2>专题情报库</h2>
          <p>每个专题都有独立的数据源、采集节奏、历史数据、空间范围和分析目标</p>
        </div>
        <div class="domain-actions">
          <el-tag effect="plain">{{ filteredDomains.length }} 个专题</el-tag>
          <el-button size="small" type="primary" @click="openTopicDialog()">
            <el-icon><Plus /></el-icon>
            新增专题
          </el-button>
        </div>
      </div>

      <div class="domain-grid">
        <article
          v-for="domain in filteredDomains"
          :key="domain.id"
          class="domain-card"
          :class="{ active: activeDomainId === domain.id }"
          @click="focusDomain(domain)"
        >
          <div class="card-top">
            <div class="title-wrap">
              <span class="icon-tile">{{ domain.icon }}</span>
              <div>
                <h3>{{ domain.name }}</h3>
                <p>{{ domain.description }}</p>
              </div>
            </div>
            <div class="card-status-actions">
              <el-tag :type="statusType(domain.status)" size="small" effect="plain">
                {{ statusLabel(domain.status) }}
              </el-tag>
              <el-tooltip content="编辑专题">
                <el-button circle size="small" aria-label="编辑专题" @click.stop="openTopicDialog(domain)">
                  <el-icon><Edit /></el-icon>
                </el-button>
              </el-tooltip>
            </div>
          </div>

          <div class="domain-meta">
            <span>空间范围</span>
            <strong>{{ domain.locationName }}</strong>
            <span>记录量</span>
            <strong>{{ domain.records }}</strong>
            <span>更新时间</span>
            <strong>{{ domain.updatedAt }}</strong>
          </div>

          <div class="chip-row">
            <el-tag v-for="source in domain.sources" :key="source" size="small" effect="plain">
              {{ source }}
            </el-tag>
          </div>

          <div class="analysis-block">
            <span>分析目标</span>
            <p>{{ domain.goal }}</p>
          </div>
        </article>
      </div>
    </section>

    <el-dialog v-model="topicDialogOpen" :title="topicForm.id ? '编辑情报专题' : '新增情报专题'" width="720px">
      <div class="topic-form">
        <div class="topic-form-title">
          <el-input v-model="topicForm.icon" maxlength="4" placeholder="图标" />
          <el-input v-model="topicForm.name" placeholder="专题名称" />
          <el-select v-model="topicForm.status" placeholder="状态">
            <el-option label="采集中" value="active" />
            <el-option label="规划中" value="planning" />
            <el-option label="暂停" value="paused" />
          </el-select>
        </div>
        <el-input v-model="topicForm.description" type="textarea" :rows="2" placeholder="专题说明" />
        <div class="topic-form-location">
          <el-input v-model="topicForm.locationName" placeholder="位置名称，例如 上海 / 项目中心" />
          <el-input v-model.number="topicForm.lat" type="number" :min="-90" :max="90" step="0.0001" placeholder="纬度" />
          <el-input v-model.number="topicForm.lng" type="number" :min="-180" :max="180" step="0.0001" placeholder="经度" />
        </div>
        <div class="topic-form-records">
          <el-input v-model="topicForm.records" placeholder="记录量显示，例如 12,480" />
          <el-input v-model.number="topicForm.recordValue" type="number" :min="0" step="1" placeholder="记录数值" />
          <el-input v-model="topicForm.updatedAt" placeholder="更新频率，例如 每日同步" />
        </div>
        <el-input v-model="topicSourcesText" placeholder="数据来源，使用逗号分隔" />
        <el-input v-model="topicRelatedLocationsText" placeholder="关联新闻位置键，使用逗号分隔" />
        <el-input v-model="topicForm.goal" type="textarea" :rows="3" placeholder="分析目标" />
      </div>
      <template #footer>
        <el-button v-if="topicForm.id" type="danger" plain @click="removeTopic">删除专题</el-button>
        <el-button @click="topicDialogOpen = false">取消</el-button>
        <el-button type="primary" :loading="topicSaving" @click="submitTopic">保存</el-button>
      </template>
    </el-dialog>

    <section class="section-panel">
      <div class="section-head">
        <div>
          <h2>关联新闻资讯</h2>
          <p>新闻资讯是每日要闻；在这里按空间位置接入，用来辅助长期情报判断</p>
        </div>
        <el-tag effect="plain">{{ relatedNews.length }} 条</el-tag>
      </div>
      <div v-if="relatedNews.length" class="news-grid">
        <article v-for="item in relatedNews" :key="item.id" class="news-card" @click="focusNews(item)">
          <div class="news-line">
            <el-tag size="small" :type="item.priority === 'high' ? 'danger' : 'info'" effect="plain">
              {{ item.category || '资讯' }}
            </el-tag>
            <span>{{ formatDate(item.published_at) }}</span>
          </div>
          <h3>{{ item.title }}</h3>
          <p>{{ item.summary || '暂无摘要' }}</p>
          <div class="news-foot">
            <span>{{ item.source || '未知来源' }}</span>
            <span>{{ locationName(item.location) }}</span>
          </div>
        </article>
      </div>
      <el-empty v-else description="暂无空间关联新闻" :image-size="90" />
    </section>

    <section class="section-panel">
      <div class="section-head">
        <div>
          <h2>采集与沉淀流程</h2>
          <p>情报信息强调连续采集、清洗入库、空间归档、关联分析和长期回溯</p>
        </div>
      </div>

      <div class="pipeline-grid">
        <article v-for="step in pipeline" :key="step.name" class="pipeline-card">
          <span class="step-index">{{ step.index }}</span>
          <h3>{{ step.name }}</h3>
          <p>{{ step.description }}</p>
        </article>
      </div>
    </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Edit, Plus, Search } from '@element-plus/icons-vue'
import IntelligenceGlobe from '@/components/intelligence/IntelligenceGlobe.vue'
import WorldCup2026Topic from '@/components/intelligence/WorldCup2026Topic.vue'
import type { GlobeSpatialItem, GlobeSpatialType, GlobeTrack } from '@/globe/types'
import {
  deleteAisSource,
  deleteIntelligenceEvent,
  deleteIntelligenceTopic,
  getAisVessels,
  getAisSources,
  getLocationNews,
  getIntelligenceTopics,
  getIntelligenceEvents,
  getNews,
  getNewsLocations,
  importAisPayload,
  saveAisSource,
  saveIntelligenceTopic,
  saveIntelligenceEvent,
  syncAisSource,
  updateIntelligenceEventStatus,
  type AisImportResult,
  type AisSource,
  type AisTrackPoint as ApiAisTrackPoint,
  type AisVessel as ApiAisVessel,
  type IntelligenceTopic,
  type IntelligenceEvent,
  type NewsItem,
  type NewsLocation
} from '@/api/openclaw'

type DomainStatus = 'active' | 'planning' | 'paused'
type SpatialType = GlobeSpatialType
type VesselStatus = 'underway' | 'loitering' | 'silent' | 'unknown'

type IntelligenceDomain = IntelligenceTopic

const activeTopicTab = ref('overview')

type SpatialItem = GlobeSpatialItem

interface AisTrackPoint {
  timestamp?: string
  time: string
  lat: number
  lng: number
  speed: number
  course: number
}

interface AisVessel {
  id: string
  name: string
  mmsi: string
  type: string
  area: string
  status: VesselStatus
  track: AisTrackPoint[]
}

const keyword = ref('')
const globeRef = ref<InstanceType<typeof IntelligenceGlobe> | null>(null)
const activeSpatialKey = ref('domain:task-planning')
const activeDomainId = ref('task-planning')
const news = ref<NewsItem[]>([])
const newsLocations = ref<Record<string, NewsLocation>>({})
const showAisLayer = ref(true)
const showTrackLayer = ref(true)
const showNewsLayer = ref(true)
const showEventLayer = ref(true)
const trackTimeIndex = ref(0)
const activeVesselId = ref('ddg-172')
const aisImportOpen = ref(false)
const aisImporting = ref(false)
const aisImportFormat = ref<'csv' | 'json'>('csv')
const aisImportSource = ref('manual-import')
const aisImportContent = ref('')
const aisImportResult = ref<AisImportResult | null>(null)
const aisSources = ref<AisSource[]>([])
const sourceDialogOpen = ref(false)
const sourceSaving = ref(false)
const sourceHeadersText = ref('{}')
const sourceForm = ref<Partial<AisSource>>({
  name: '',
  url: '',
  format: 'csv',
  poll_interval_seconds: 3600,
  enabled: true
})
const topicDialogOpen = ref(false)
const topicSaving = ref(false)
const topicSourcesText = ref('')
const topicRelatedLocationsText = ref('')
const topicForm = ref<Partial<IntelligenceDomain>>({})
const intelligenceEvents = ref<IntelligenceEvent[]>([])
const eventSeverityFilter = ref('')
const eventStatusFilter = ref('')
const eventDialogOpen = ref(false)
const eventSaving = ref(false)
const eventForm = ref<Partial<IntelligenceEvent>>({})

const domains = ref<IntelligenceDomain[]>([])

const pipeline = [
  { index: '01', name: '定义专题', description: '明确领域、目标对象、空间范围、采集边界、时间尺度和分析用途。' },
  { index: '02', name: '连续采集', description: '按任务或定时器抓取结构化数据、文件、事件、AIS 轨迹和外部来源。' },
  { index: '03', name: '空间归档', description: '统一经纬度、实体、时间和来源字段，并保留原始证据引用。' },
  { index: '04', name: '历史分析', description: '按时间线、实体、地点和项目关系做检索、回溯与趋势判断。' }
]

const aisVessels = ref<AisVessel[]>([])

const filteredDomains = computed(() => {
  const key = keyword.value.trim().toLowerCase()
  if (!key) return domains.value
  return domains.value.filter(domain => [
    domain.name,
    domain.description,
    domain.goal,
    domain.updatedAt,
    domain.locationName,
    ...domain.sources
  ].some(value => value.toLowerCase().includes(key)))
})

const filteredEvents = computed(() => {
  const key = keyword.value.trim().toLowerCase()
  return intelligenceEvents.value.filter(event => {
    if (eventSeverityFilter.value && event.severity !== eventSeverityFilter.value) return false
    if (eventStatusFilter.value && event.status !== eventStatusFilter.value) return false
    if (!key) return true
    return [
      event.title,
      event.summary,
      event.locationName,
      event.source,
      event.topicName || '',
      event.vesselName || '',
      event.assigneeAgentId || ''
    ].some(value => value.toLowerCase().includes(key))
  })
})

const openAlertCount = computed(() => intelligenceEvents.value.filter(event =>
  event.status !== 'resolved' && ['high', 'critical'].includes(event.severity)
).length)

const spatialItems = computed<SpatialItem[]>(() => {
  const domainItems = filteredDomains.value.map(domain => ({
    key: `domain:${domain.id}`,
    type: 'domain' as const,
    id: domain.id,
    name: domain.name,
    lat: domain.lat,
    lng: domain.lng,
    locationLabel: domain.locationName,
    countLabel: domain.records
  }))
  const seen = new Set<string>()
  const newsItems = news.value
    .filter(() => showNewsLayer.value)
    .filter(item => item.location && newsLocations.value[item.location])
    .filter(item => {
      const key = item.location || ''
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
    .map(item => {
      const locationKey = item.location || ''
      const location = newsLocations.value[locationKey]
      const count = news.value.filter(row => row.location === locationKey).length
      return {
        key: `news:${locationKey}`,
        type: 'news' as const,
        id: locationKey,
        name: location.name,
        lat: location.lat,
        lng: location.lng,
        locationLabel: `${location.country || '未知区域'} · 新闻热点`,
        countLabel: `${count} 条`
      }
    })
  const vesselItems = showAisLayer.value
    ? aisVessels.value.flatMap<SpatialItem>(vessel => {
      const point = currentVesselPoint(vessel) || vessel.track[vessel.track.length - 1]
      if (!point) return []
      return [{
        key: `vessel:${vessel.id}`,
        type: 'vessel' as const,
        id: vessel.id,
        name: vessel.name,
        lat: point.lat,
        lng: point.lng,
        locationLabel: `${vessel.area} · ${point.speed} kn / ${point.course}°`,
        countLabel: `${vessel.track.length} 点`
      }]
    })
    : []
  const eventItems = showEventLayer.value
    ? filteredEvents.value.map(event => ({
      key: `event:${event.id}`,
      type: 'event' as const,
      id: event.id,
      name: event.title,
      lat: event.lat,
      lng: event.lng,
      locationLabel: `${event.locationName} · ${eventSeverityLabel(event.severity)}`,
      countLabel: eventStatusLabel(event.status)
    }))
    : []
  return [...domainItems, ...eventItems, ...vesselItems, ...newsItems]
})

const globeTracks = computed<GlobeTrack[]>(() => aisVessels.value.map(vessel => ({
  id: vessel.id,
  active: vessel.id === activeVesselId.value,
  points: vessel.track
    .slice(0, Math.min(trackTimeIndex.value + 1, vessel.track.length))
    .map(point => ({ lat: point.lat, lng: point.lng, timestamp: point.timestamp }))
})))

const activeDomains = computed(() => domains.value.filter(domain => domain.status === 'active').length)
const maxTrackIndex = computed(() => Math.max(0, Math.max(...aisVessels.value.map(vessel => vessel.track.length - 1))))
const selectedTrackTime = computed(() => aisVessels.value[0]?.track[Math.min(trackTimeIndex.value, maxTrackIndex.value)]?.time || '--:--')
const trackPointCount = computed(() => aisVessels.value.reduce((sum, vessel) => sum + vessel.track.length, 0))
const activeVessel = computed(() => {
  if (!activeSpatialKey.value.startsWith('vessel:')) return undefined
  return aisVessels.value.find(vessel => vessel.id === activeVesselId.value)
})
const relatedNews = computed(() => {
  const active = activeSpatialKey.value
  const key = active.replace(/^news:/, '').replace(/^domain:/, '')
  if (active.startsWith('news:')) {
    return news.value.filter(item => item.location === key).slice(0, 12)
  }
  if (active.startsWith('vessel:')) {
    return news.value.filter(item => ['tokyo', 'shenzhen', 'singapore'].includes(item.location || '')).slice(0, 12)
  }
  if (active.startsWith('event:')) {
    const event = intelligenceEvents.value.find(item => item.id === active.slice(6))
    if (!event) return news.value.slice(0, 8)
    const topic = domains.value.find(item => item.id === event.topicId)
    if (topic) return news.value.filter(item => topic.relatedLocations.includes(item.location || '')).slice(0, 12)
    return news.value.slice(0, 8)
  }
  const domain = domains.value.find(item => item.id === key)
  if (!domain) return news.value.slice(0, 8)
  return news.value.filter(item => domain.relatedLocations.includes(item.location || '')).slice(0, 12)
})

const activeSummary = computed(() => {
  const item = spatialItems.value.find(row => row.key === activeSpatialKey.value)
  if (!item) return '选择地球点位或专题卡片查看关联新闻'
  return `${item.name}：${item.locationLabel}`
})

function statusLabel(status: DomainStatus) {
  const labels: Record<DomainStatus, string> = {
    active: '采集中',
    planning: '规划中',
    paused: '暂停'
  }
  return labels[status]
}

function statusType(status: DomainStatus) {
  if (status === 'active') return 'success'
  if (status === 'planning') return 'warning'
  return 'info'
}

function spatialTypeLabel(type: SpatialType) {
  if (type === 'domain') return '长期情报'
  if (type === 'event') return '情报事件'
  if (type === 'vessel') return 'AIS 舰艇'
  return '新闻热点'
}

function spatialTypeTag(type: SpatialType) {
  if (type === 'domain') return 'warning'
  if (type === 'event') return 'danger'
  if (type === 'vessel') return 'success'
  return 'primary'
}

function eventSeverityLabel(severity: IntelligenceEvent['severity']) {
  return {
    info: '信息',
    low: '低',
    medium: '中',
    high: '高',
    critical: '紧急'
  }[severity]
}

function eventSeverityType(severity: IntelligenceEvent['severity']) {
  if (severity === 'critical' || severity === 'high') return 'danger'
  if (severity === 'medium') return 'warning'
  if (severity === 'low') return 'success'
  return 'info'
}

function eventStatusLabel(status: IntelligenceEvent['status']) {
  return {
    open: '待处置',
    monitoring: '监视中',
    resolved: '已解决'
  }[status]
}

function eventStatusType(status: IntelligenceEvent['status']) {
  if (status === 'open') return 'danger'
  if (status === 'monitoring') return 'warning'
  return 'success'
}

function vesselStatusLabel(status: VesselStatus) {
  const labels: Record<VesselStatus, string> = {
    underway: '航行中',
    loitering: '盘旋/巡弋',
    silent: '静默/停留',
    unknown: '未知状态'
  }
  return labels[status]
}

function vesselStatusType(status: VesselStatus) {
  if (status === 'underway') return 'success'
  if (status === 'loitering') return 'warning'
  return 'info'
}

function currentVesselPoint(vessel: AisVessel) {
  if (!vessel.track.length) return undefined
  const index = Math.min(trackTimeIndex.value, vessel.track.length - 1)
  return vessel.track[index]
}

function vesselCoordinate(vessel: AisVessel) {
  const point = currentVesselPoint(vessel)
  if (!point) return '--'
  return `${point.lat.toFixed(2)}, ${point.lng.toFixed(2)}`
}

function locationName(locationKey?: string) {
  if (!locationKey) return '未知位置'
  const location = newsLocations.value[locationKey]
  return location ? location.name : locationKey
}

function formatDate(value?: string) {
  if (!value) return '未知时间'
  return value.replace('T', ' ').slice(0, 16)
}

function normalizeVesselStatus(status?: string): VesselStatus {
  if (status === 'underway' || status === 'loitering' || status === 'silent') return status
  return 'unknown'
}

function formatTrackTime(point: ApiAisTrackPoint) {
  const value = point.timestamp || point.time || ''
  if (!value) return '--:--'
  const match = value.match(/T(\d{2}:\d{2})/)
  return match ? match[1] : value.slice(0, 5)
}

function normalizeAisVessel(vessel: ApiAisVessel): AisVessel {
  const track = (vessel.track || []).map(point => ({
    timestamp: point.timestamp,
    time: formatTrackTime(point),
    lat: Number(point.lat),
    lng: Number(point.lng),
    speed: Number(point.speed || 0),
    course: Number(point.course || 0)
  }))
  if (!track.length && vessel.latest) {
    track.push({
      timestamp: vessel.latest.timestamp,
      time: formatTrackTime(vessel.latest),
      lat: Number(vessel.latest.lat),
      lng: Number(vessel.latest.lng),
      speed: Number(vessel.latest.speed || 0),
      course: Number(vessel.latest.course || 0)
    })
  }
  return {
    id: vessel.id,
    name: vessel.name,
    mmsi: vessel.mmsi,
    type: vessel.type || '未知类型',
    area: vessel.area || '未知海域',
    status: normalizeVesselStatus(vessel.status),
    track
  }
}

async function loadAisVessels() {
  try {
    const data = await getAisVessels(true, 200)
    aisVessels.value = (data.vessels || []).map(normalizeAisVessel).filter(vessel => vessel.track.length)
    const maxIndex = maxTrackIndex.value
    trackTimeIndex.value = maxIndex
    if (!aisVessels.value.some(vessel => vessel.id === activeVesselId.value) && aisVessels.value[0]) {
      activeVesselId.value = aisVessels.value[0].id
    }
  } catch (error) {
    console.error(error)
    ElMessage.warning('AIS 情报数据加载失败')
  }
}

async function submitAisImport() {
  const content = aisImportContent.value.trim()
  if (!content) {
    ElMessage.warning('请粘贴 AIS 数据')
    return
  }
  aisImporting.value = true
  try {
    const result = await importAisPayload(content, aisImportFormat.value, aisImportSource.value || 'manual-import')
    aisImportResult.value = result
    await loadAisVessels()
    ElMessage.success(`AIS 导入完成：写入 ${result.inserted} 条，跳过 ${result.skipped} 条`)
  } catch (error) {
    console.error(error)
  } finally {
    aisImporting.value = false
  }
}

async function loadAisSources() {
  try {
    const data = await getAisSources()
    aisSources.value = data.sources || []
  } catch (error) {
    console.error(error)
  }
}

function openSourceDialog(source?: AisSource) {
  sourceForm.value = source
    ? { ...source }
    : {
      name: '',
      url: '',
      format: 'csv',
      poll_interval_seconds: 3600,
      enabled: true
    }
  sourceHeadersText.value = JSON.stringify(source?.headers || {}, null, 2)
  sourceDialogOpen.value = true
}

async function saveSource() {
  if (!sourceForm.value.name || !sourceForm.value.url) {
    ElMessage.warning('请填写数据源名称和 URL')
    return
  }
  sourceSaving.value = true
  try {
    const headers = sourceHeadersText.value.trim() ? JSON.parse(sourceHeadersText.value) : {}
    await saveAisSource({
      ...sourceForm.value,
      headers
    })
    await loadAisSources()
    sourceDialogOpen.value = false
    ElMessage.success('AIS 数据源已保存')
  } catch (error) {
    console.error(error)
    if (error instanceof SyntaxError) ElMessage.error('请求头 JSON 格式错误')
  } finally {
    sourceSaving.value = false
  }
}

async function syncSource(source: AisSource) {
  try {
    const result = await syncAisSource(source.id)
    await Promise.all([loadAisSources(), loadAisVessels()])
    ElMessage.success(`同步完成：写入 ${result.inserted} 条，跳过 ${result.skipped} 条`)
  } catch (error) {
    console.error(error)
    await loadAisSources()
  }
}

async function removeSource(source: AisSource) {
  try {
    await deleteAisSource(source.id)
    await loadAisSources()
    ElMessage.success('AIS 数据源已删除')
  } catch (error) {
    console.error(error)
  }
}

async function loadSpatialNews() {
  try {
    const [newsData, locationsData] = await Promise.all([
      getNews(120),
      getNewsLocations(),
      getLocationNews()
    ])
    news.value = newsData.news || []
    newsLocations.value = locationsData.locations || {}
  } catch (error) {
    console.error(error)
    ElMessage.warning('新闻空间数据加载失败，情报地球仅显示专题点位')
  }
}

async function loadTopics() {
  try {
    const data = await getIntelligenceTopics()
    domains.value = data.topics || []
    if (!domains.value.some(topic => `domain:${topic.id}` === activeSpatialKey.value) && domains.value[0]) {
      activeDomainId.value = domains.value[0].id
      activeSpatialKey.value = `domain:${domains.value[0].id}`
    }
  } catch (error) {
    console.error(error)
    ElMessage.warning('专题情报加载失败')
  }
}

async function loadEvents() {
  try {
    const data = await getIntelligenceEvents({ limit: 200 })
    intelligenceEvents.value = data.events || []
  } catch (error) {
    console.error(error)
    ElMessage.warning('空间情报事件加载失败')
  }
}

function localDateTimeValue(value = new Date()) {
  const offset = value.getTimezoneOffset() * 60_000
  return new Date(value.getTime() - offset).toISOString().slice(0, 16)
}

function openEventDialog(event?: IntelligenceEvent) {
  const active = spatialItems.value.find(item => item.key === activeSpatialKey.value)
  eventForm.value = event
    ? { ...event, occurredAt: event.occurredAt.slice(0, 16) }
    : {
      title: '',
      summary: '',
      category: 'observation',
      severity: 'medium',
      status: 'open',
      source: '人工研判',
      occurredAt: localDateTimeValue(),
      lat: active?.lat ?? 0,
      lng: active?.lng ?? 0,
      locationName: active?.locationLabel || '',
      confidence: 0.5,
      topicId: active?.type === 'domain' ? active.id : undefined,
      vesselId: active?.type === 'vessel' ? active.id : undefined,
      assigneeAgentId: 'perceptor'
    }
  eventDialogOpen.value = true
}

async function submitEvent() {
  if (!eventForm.value.title?.trim() || !eventForm.value.locationName?.trim()) {
    ElMessage.warning('请填写事件标题和位置名称')
    return
  }
  eventSaving.value = true
  try {
    const result = await saveIntelligenceEvent(eventForm.value)
    await loadEvents()
    eventDialogOpen.value = false
    focusEvent(result.event)
    ElMessage.success('情报事件已保存并更新到地球')
  } catch (error) {
    console.error(error)
  } finally {
    eventSaving.value = false
  }
}

async function resolveEvent(event: IntelligenceEvent) {
  try {
    await updateIntelligenceEventStatus(event.id, 'resolved')
    await loadEvents()
    ElMessage.success('事件已标记为解决')
  } catch (error) {
    console.error(error)
  }
}

async function removeEvent() {
  if (!eventForm.value.id) return
  try {
    await ElMessageBox.confirm('删除后事件及其地球点位将同时移除。', '删除情报事件', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    })
    await deleteIntelligenceEvent(eventForm.value.id)
    eventDialogOpen.value = false
    await loadEvents()
    ElMessage.success('情报事件已删除')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') console.error(error)
  }
}

function splitTopicValues(value: string) {
  return value.split(/[,，\n]/).map(item => item.trim()).filter(Boolean)
}

function openTopicDialog(topic?: IntelligenceDomain) {
  topicForm.value = topic
    ? { ...topic }
    : {
      name: '',
      icon: '📍',
      description: '',
      status: 'planning',
      records: '0',
      recordValue: 0,
      updatedAt: '尚未更新',
      goal: '',
      lat: 0,
      lng: 0,
      locationName: ''
    }
  topicSourcesText.value = topic?.sources.join('，') || ''
  topicRelatedLocationsText.value = topic?.relatedLocations.join('，') || ''
  topicDialogOpen.value = true
}

async function submitTopic() {
  if (!topicForm.value.name?.trim() || !topicForm.value.locationName?.trim()) {
    ElMessage.warning('请填写专题名称和位置名称')
    return
  }
  topicSaving.value = true
  try {
    const result = await saveIntelligenceTopic({
      ...topicForm.value,
      sources: splitTopicValues(topicSourcesText.value),
      relatedLocations: splitTopicValues(topicRelatedLocationsText.value)
    })
    await loadTopics()
    topicDialogOpen.value = false
    focusDomain(result.topic)
    ElMessage.success('情报专题已保存并更新到地球')
  } catch (error) {
    console.error(error)
  } finally {
    topicSaving.value = false
  }
}

async function removeTopic() {
  const topicId = topicForm.value.id
  if (!topicId) return
  try {
    await ElMessageBox.confirm('删除后该专题点位将从地球和专题库中移除。', '删除情报专题', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    })
    await deleteIntelligenceTopic(topicId)
    topicDialogOpen.value = false
    await loadTopics()
    ElMessage.success('情报专题已删除')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') console.error(error)
  }
}

function focusSpatialItem(item: SpatialItem) {
  activeSpatialKey.value = item.key
  activeDomainId.value = item.type === 'domain' ? item.id : ''
  activeVesselId.value = item.type === 'vessel' ? item.id : activeVesselId.value
  globeRef.value?.focus(item)
}

function focusDomain(domain: IntelligenceDomain) {
  focusSpatialItem({
    key: `domain:${domain.id}`,
    type: 'domain',
    id: domain.id,
    name: domain.name,
    lat: domain.lat,
    lng: domain.lng,
    locationLabel: domain.locationName,
    countLabel: domain.records
  })
}

function focusNews(item: NewsItem) {
  if (!item.location || !newsLocations.value[item.location]) return
  const loc = newsLocations.value[item.location]
  focusSpatialItem({
    key: `news:${item.location}`,
    type: 'news',
    id: item.location,
    name: loc.name,
    lat: loc.lat,
    lng: loc.lng,
    locationLabel: `${loc.country || '未知区域'} · 新闻热点`,
    countLabel: `${news.value.filter(row => row.location === item.location).length} 条`
  })
}

function focusVessel(vessel: AisVessel) {
  const point = currentVesselPoint(vessel) || vessel.track[vessel.track.length - 1]
  focusSpatialItem({
    key: `vessel:${vessel.id}`,
    type: 'vessel',
    id: vessel.id,
    name: vessel.name,
    lat: point.lat,
    lng: point.lng,
    locationLabel: `${vessel.area} · ${point.speed} kn / ${point.course}°`,
    countLabel: `${vessel.track.length} 点`
  })
}

function focusEvent(event: IntelligenceEvent) {
  focusSpatialItem({
    key: `event:${event.id}`,
    type: 'event',
    id: event.id,
    name: event.title,
    lat: event.lat,
    lng: event.lng,
    locationLabel: `${event.locationName} · ${eventSeverityLabel(event.severity)}`,
    countLabel: eventStatusLabel(event.status)
  })
}

onMounted(async () => {
  await Promise.all([loadTopics(), loadEvents(), loadSpatialNews(), loadAisVessels(), loadAisSources()])
})
</script>

<style scoped>
.intelligence-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  color: var(--text-primary);
}

.page-head,
.metric-card,
.section-panel,
.domain-card,
.vessel-card,
.pipeline-card,
.linked-panel,
.linked-card,
.news-card,
.event-card {
  background: var(--card-bg);
  border: 1px solid var(--line-color);
  border-radius: 8px;
}

.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px;
}

.page-head h1,
.section-head h2,
.domain-card h3,
.pipeline-card h3,
.news-card h3 {
  margin: 0;
  letter-spacing: 0;
}

.page-head h1 {
  font-size: 22px;
}

.page-head p,
.section-head p,
.title-wrap p,
.analysis-block p,
.pipeline-card p,
.metric-card small,
.domain-meta span,
.linked-card span,
.news-card p,
.news-line,
.news-foot {
  color: var(--text-secondary);
}

.page-head p,
.section-head p {
  margin: 6px 0 0;
  font-size: 13px;
}

.search-input {
  width: 320px;
}

.topic-tabs {
  padding: 0 16px;
  background: var(--card-bg);
  border: 1px solid var(--line-color);
  border-radius: 8px;
}

.topic-tabs :deep(.el-tabs__header) {
  margin: 0;
}

.topic-tabs :deep(.el-tabs__content) {
  display: none;
}

.space-grid {
  display: grid;
  grid-template-columns: minmax(420px, 1.5fr) minmax(280px, 0.8fr);
  gap: 12px;
}

.linked-panel,
.section-panel {
  padding: 16px;
}

.section-head,
.card-top,
.news-line,
.news-foot {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.section-head {
  align-items: flex-start;
  margin-bottom: 14px;
}

.section-head h2 {
  font-size: 16px;
}

.domain-actions,
.card-status-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-head.compact {
  margin-bottom: 10px;
}

.linked-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 438px;
  overflow: auto;
}

.linked-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px;
  cursor: pointer;
  background: var(--card-bg-soft);
}

.linked-card.active,
.domain-card.active {
  border-color: var(--view-color-strong-border);
  background: var(--view-color-panel);
}

.linked-card strong,
.linked-card span {
  display: block;
}

.linked-card span {
  margin-top: 4px;
  font-size: 12px;
}

.vessel-detail {
  margin-top: 12px;
  padding: 12px;
  background: rgba(57, 217, 138, 0.055);
  border: 1px solid rgba(57, 217, 138, 0.22);
  border-radius: 8px;
}

.detail-title,
.vessel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.detail-grid {
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr);
  gap: 8px 10px;
  margin-top: 12px;
  font-size: 12px;
}

.detail-grid span,
.vessel-head span {
  color: var(--text-secondary);
}

.detail-grid strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}

.metric-grid,
.pipeline-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}

.metric-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px;
}

.metric-card span {
  color: var(--text-secondary);
  font-size: 13px;
}

.metric-card strong {
  font-size: 24px;
  line-height: 1.1;
}

.alert-metric strong {
  color: #f85149;
}

.event-actions,
.event-card-actions,
.event-title-line,
.event-footer,
.event-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.event-actions {
  flex-wrap: wrap;
  justify-content: flex-end;
}

.event-actions :deep(.el-select) {
  width: 124px;
}

.event-timeline {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-left: 20px;
}

.event-timeline::before {
  position: absolute;
  top: 9px;
  bottom: 9px;
  left: 6px;
  width: 1px;
  background: var(--line-color);
  content: '';
}

.event-card {
  position: relative;
  display: flex;
  gap: 12px;
  padding: 13px 14px;
  background: var(--card-bg-soft);
  cursor: pointer;
}

.event-card.active {
  border-color: var(--view-color-strong-border);
  background: var(--view-color-panel);
}

.event-marker {
  position: absolute;
  top: 20px;
  left: -19px;
  width: 10px;
  height: 10px;
  border: 2px solid var(--card-bg);
  border-radius: 50%;
  background: #8b949e;
}

.severity-critical .event-marker,
.severity-high .event-marker { background: #f85149; }
.severity-medium .event-marker { background: #d29922; }
.severity-low .event-marker { background: #3fb950; }

.event-body {
  min-width: 0;
  width: 100%;
}

.event-title-line,
.event-footer {
  justify-content: space-between;
}

.event-title-line > div {
  display: flex;
  align-items: center;
  gap: 8px;
}

.event-title-line span,
.event-meta,
.event-footer {
  color: var(--text-secondary);
  font-size: 12px;
}

.event-card h3 {
  margin: 9px 0 0;
  font-size: 15px;
  letter-spacing: 0;
}

.event-card p {
  margin: 6px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.55;
}

.event-meta {
  flex-wrap: wrap;
  margin-top: 10px;
}

.event-meta span:not(:last-child)::after {
  margin-left: 8px;
  color: var(--line-color);
  content: '·';
}

.event-footer {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--line-color);
}

.event-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.event-form-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.event-form-row.three,
.event-form-row.location {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.domain-grid,
.news-grid,
.vessel-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}

.domain-card,
.vessel-card,
.news-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  background: var(--card-bg-soft);
  cursor: pointer;
}

.vessel-card.active {
  border-color: rgba(124, 231, 255, 0.58);
  background: rgba(124, 231, 255, 0.055);
}

.vessel-head h3 {
  margin: 0 0 5px;
  font-size: 15px;
}

.ais-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 10px;
}

.time-control {
  display: grid;
  grid-template-columns: 54px minmax(160px, 240px);
  align-items: center;
  gap: 10px;
  color: var(--text-secondary);
  font-size: 12px;
}

.import-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.import-row {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr);
  gap: 10px;
}

.import-result {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  padding: 10px;
  color: var(--text-secondary);
  background: var(--card-bg-soft);
  border: 1px solid var(--line-color);
  border-radius: 7px;
  font-size: 12px;
}

.source-panel {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--line-color);
}

.source-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.source-head h3 {
  margin: 0 0 5px;
  font-size: 15px;
}

.source-head span,
.source-card span,
.source-state span {
  color: var(--text-secondary);
  font-size: 12px;
}

.source-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 10px;
}

.source-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  background: var(--card-bg-soft);
  border: 1px solid var(--line-color);
  border-radius: 8px;
}

.source-card strong,
.source-card span {
  display: block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-state {
  display: flex;
  align-items: center;
  gap: 8px;
}

.source-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
}

.source-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.source-form-row {
  display: grid;
  grid-template-columns: 160px minmax(0, 1fr);
  gap: 10px;
}

.topic-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.topic-form-title {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr) 140px;
  gap: 10px;
}

.topic-form-location {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 160px 160px;
  gap: 10px;
}

.topic-form-records {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 160px minmax(0, 1fr);
  gap: 10px;
}

.title-wrap {
  display: flex;
  align-items: flex-start;
  min-width: 0;
  gap: 10px;
}

.title-wrap h3,
.news-card h3 {
  font-size: 15px;
}

.title-wrap p {
  margin: 5px 0 0;
  font-size: 12px;
  line-height: 1.5;
}

.icon-tile {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  background: rgba(var(--view-rgb), 0.14);
  border-radius: 7px;
}

.domain-meta {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 8px 10px;
  padding-top: 10px;
  border-top: 1px solid var(--line-color);
  font-size: 12px;
}

.domain-meta strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.analysis-block {
  margin-top: auto;
  padding: 10px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.045);
  border-radius: 7px;
}

.analysis-block span {
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 600;
}

.analysis-block p,
.pipeline-card p,
.news-card p {
  margin: 6px 0 0;
  font-size: 13px;
  line-height: 1.6;
}

.news-line,
.news-foot {
  align-items: center;
  font-size: 12px;
}

.news-card h3 {
  line-height: 1.45;
}

.news-card p {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.pipeline-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.pipeline-card {
  padding: 14px;
  background: var(--card-bg-soft);
}

.step-index {
  display: inline-block;
  margin-bottom: 12px;
  color: rgb(var(--view-rgb));
  font-size: 12px;
  font-weight: 700;
}

:deep(.el-input__wrapper) {
  border-radius: 6px;
}

@media (max-width: 1180px) {
  .space-grid,
  .metric-grid,
  .pipeline-grid {
    grid-template-columns: 1fr;
  }

  .linked-list {
    max-height: 260px;
  }
}

@media (max-width: 820px) {
  .page-head {
    align-items: stretch;
    flex-direction: column;
  }

  .search-input {
    width: 100%;
  }

  .metric-grid {
    grid-template-columns: 1fr;
  }

  .domain-grid,
  .news-grid,
  .vessel-grid {
    grid-template-columns: 1fr;
  }

  .time-control {
    width: 100%;
    grid-template-columns: 48px minmax(0, 1fr);
  }

  .ais-actions {
    width: 100%;
    justify-content: flex-start;
  }

  .import-row {
    grid-template-columns: 1fr;
  }

  .source-head,
  .source-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .source-grid,
  .source-form-row,
  .topic-form-title,
  .topic-form-location,
  .topic-form-records,
  .event-form-row,
  .event-form-row.three,
  .event-form-row.location {
    grid-template-columns: 1fr;
  }

  .event-actions {
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
