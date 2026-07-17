<template>
  <section class="world-cup-topic">
    <header class="topic-head">
      <div>
        <span class="eyebrow">2026 FIFA WORLD CUP</span>
        <h2>美加墨世界杯赛果与进球时间</h2>
        <p>逐场比分、进球事件和时间分布，数据已保存至情报数据库。</p>
      </div>
      <el-button :loading="syncing" type="primary" @click="syncData">
        <el-icon><Refresh /></el-icon>
        同步最新赛果
      </el-button>
    </header>

    <div class="summary-strip">
      <div><span>已完赛</span><strong>{{ summary.completed }}</strong><small>/ {{ summary.matches }} 场</small></div>
      <div><span>总进球</span><strong>{{ summary.goals }}</strong><small>不含点球大战</small></div>
      <div><span>场均进球</span><strong>{{ summary.average_goals }}</strong><small>球 / 场</small></div>
      <div><span>待赛</span><strong>{{ summary.scheduled }}</strong><small>场</small></div>
      <div><span>数据更新</span><strong class="updated">{{ formatUpdated(summary.updated_at) }}</strong><small>ESPN 比赛事件</small></div>
    </div>

    <div class="analysis-grid">
      <article class="analysis-panel">
        <div class="panel-title"><h3>射手榜</h3><span>前 12 名</span></div>
        <div class="scorer-list">
          <div v-for="(item, index) in summary.top_scorers" :key="`${item.name}-${item.team}`" class="scorer-row">
            <span class="rank">{{ index + 1 }}</span>
            <div><strong>{{ item.name }}</strong><small>{{ teamName(item.team) }}</small></div>
            <b>{{ item.goals }}</b>
          </div>
        </div>
      </article>
      <article class="analysis-panel">
        <div class="panel-title"><h3>进球时间分布</h3><span>{{ summary.goals }} 球</span></div>
        <div class="period-list">
          <div v-for="item in summary.goal_periods" :key="item.period" class="period-row">
            <span>{{ item.period }}'</span>
            <div><i :style="{ width: periodWidth(item.goals) }"></i></div>
            <strong>{{ item.goals }}</strong>
          </div>
        </div>
      </article>
    </div>

    <article class="matches-panel">
      <div class="table-toolbar">
        <div>
          <h3>比赛统计表</h3>
          <span>当前 {{ filteredMatches.length }} 场，进球分钟保留伤停补时标记</span>
        </div>
        <div class="filters">
          <el-select v-model="stageFilter" clearable placeholder="全部阶段" aria-label="赛事阶段">
            <el-option v-for="item in stages" :key="item" :label="stageName(item)" :value="item" />
          </el-select>
          <el-input v-model="teamFilter" clearable placeholder="搜索球队" aria-label="搜索球队">
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <el-segmented v-model="statusFilter" :options="statusOptions" />
        </div>
      </div>

      <el-table :data="filteredMatches" :empty-text="loading ? '正在加载...' : '暂无数据'" row-key="id" stripe>
        <el-table-column label="开球时间" width="148">
          <template #default="{ row }"><span class="date-cell">{{ formatKickoff(row.kickoff_at) }}</span></template>
        </el-table-column>
        <el-table-column label="阶段" width="126">
          <template #default="{ row }"><el-tag size="small" effect="plain">{{ stageName(row.stage) }}</el-tag></template>
        </el-table-column>
        <el-table-column label="主队" min-width="138" align="right">
          <template #default="{ row }"><span class="team-cell home">{{ teamName(row.home_team) }}<img :src="row.home_logo" alt="" /></span></template>
        </el-table-column>
        <el-table-column label="比分" width="94" align="center">
          <template #default="{ row }">
            <strong v-if="row.completed" class="score">{{ row.home_score }} : {{ row.away_score }}</strong>
            <span v-else class="scheduled">待赛</span>
            <small v-if="row.status_label === 'AET'" class="score-note">加时</small>
          </template>
        </el-table-column>
        <el-table-column label="客队" min-width="138">
          <template #default="{ row }"><span class="team-cell"><img :src="row.away_logo" alt="" />{{ teamName(row.away_team) }}</span></template>
        </el-table-column>
        <el-table-column label="进球时间" min-width="330">
          <template #default="{ row }">
            <div v-if="row.goals.length" class="goal-list">
              <span v-for="goal in row.goals" :key="goal.id" class="goal-chip">
                <b>{{ goal.minute_label }}</b>
                {{ goal.scorer_name }}
                <em v-if="goal.penalty">点球</em><em v-if="goal.own_goal">乌龙</em>
              </span>
            </div>
            <span v-else class="muted">{{ row.completed ? '无进球' : '尚未开赛' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="场地" min-width="180">
          <template #default="{ row }"><span class="venue">{{ row.venue || row.location || '--' }}</span></template>
        </el-table-column>
      </el-table>
    </article>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Search } from '@element-plus/icons-vue'
import {
  getWorldCup2026Matches,
  getWorldCup2026Summary,
  syncWorldCup2026,
  type WorldCupMatch,
  type WorldCupSummary
} from '@/api/openclaw'

const loading = ref(false)
const syncing = ref(false)
const matches = ref<WorldCupMatch[]>([])
const stageFilter = ref('')
const teamFilter = ref('')
const statusFilter = ref<'all' | 'completed' | 'scheduled'>('all')
const statusOptions = [
  { label: '全部', value: 'all' },
  { label: '已完赛', value: 'completed' },
  { label: '待赛', value: 'scheduled' }
]
const summary = ref<WorldCupSummary>({
  matches: 0, completed: 0, scheduled: 0, goals: 0, average_goals: 0,
  updated_at: null, top_scorers: [], goal_periods: []
})

const stages = computed(() => [...new Set(matches.value.map(item => item.stage).filter(Boolean))])
const filteredMatches = computed(() => {
  const keyword = teamFilter.value.trim().toLowerCase()
  return matches.value.filter(item => {
    if (stageFilter.value && item.stage !== stageFilter.value) return false
    if (statusFilter.value === 'completed' && !item.completed) return false
    if (statusFilter.value === 'scheduled' && item.completed) return false
    if (!keyword) return true
    return [item.home_team, item.away_team, item.home_code, item.away_code]
      .some(value => value.toLowerCase().includes(keyword) || teamName(value).includes(teamFilter.value.trim()))
  })
})

const stageLabels: Record<string, string> = {
  'group-stage': '小组赛', 'round-of-32': '32 强', 'round-of-16': '16 强',
  'quarterfinals': '四分之一决赛', 'semifinals': '半决赛',
  '3rd-place-match': '季军赛', 'final': '决赛'
}
const teamLabels: Record<string, string> = {
  Argentina: '阿根廷', Australia: '澳大利亚', Austria: '奥地利', Belgium: '比利时', Brazil: '巴西',
  Cameroon: '喀麦隆', Canada: '加拿大', Colombia: '哥伦比亚', Croatia: '克罗地亚', Curaçao: '库拉索',
  Denmark: '丹麦', Ecuador: '厄瓜多尔', Egypt: '埃及', England: '英格兰', France: '法国', Germany: '德国',
  Ghana: '加纳', Haiti: '海地', Iran: '伊朗', Iraq: '伊拉克', Italy: '意大利', 'Ivory Coast': '科特迪瓦',
  Japan: '日本', Jordan: '约旦', 'South Korea': '韩国', Mexico: '墨西哥', Morocco: '摩洛哥', Netherlands: '荷兰',
  'New Zealand': '新西兰', Nigeria: '尼日利亚', Norway: '挪威', Panama: '巴拿马', Paraguay: '巴拉圭',
  Portugal: '葡萄牙', Qatar: '卡塔尔', 'Saudi Arabia': '沙特阿拉伯', Scotland: '苏格兰', Senegal: '塞内加尔',
  Serbia: '塞尔维亚', 'South Africa': '南非', Spain: '西班牙', Sweden: '瑞典', Switzerland: '瑞士',
  Tunisia: '突尼斯', Turkey: '土耳其', Ukraine: '乌克兰', Uruguay: '乌拉圭', USA: '美国', Uzbekistan: '乌兹别克斯坦'
}

function stageName(stage: string) { return stageLabels[stage] || stage || '未分类' }
function teamName(team: string) { return teamLabels[team] || team }
function formatKickoff(value: string) {
  if (!value) return '--'
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value))
}
function formatUpdated(value: string | null) {
  if (!value) return '尚未同步'
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(`${value.replace(' ', 'T')}Z`))
}
function periodWidth(value: number) {
  const max = Math.max(...summary.value.goal_periods.map(item => item.goals), 1)
  return `${Math.max(5, Math.round(value / max * 100))}%`
}
async function loadData() {
  loading.value = true
  try {
    const [summaryData, matchesData] = await Promise.all([getWorldCup2026Summary(), getWorldCup2026Matches()])
    summary.value = summaryData
    matches.value = matchesData.matches || []
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '世界杯专题数据加载失败')
  } finally {
    loading.value = false
  }
}
async function syncData() {
  syncing.value = true
  try {
    const result = await syncWorldCup2026()
    ElMessage.success(`已同步 ${result.completed} 场赛果、${result.goals} 个进球`)
    await loadData()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '世界杯数据同步失败')
  } finally {
    syncing.value = false
  }
}
onMounted(loadData)
</script>

<style scoped>
.world-cup-topic { display: grid; gap: 14px; }
.topic-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; padding: 18px 20px; border: 1px solid var(--line-color); background: var(--card-bg); border-radius: 6px; }
.eyebrow { color: #55a6ff; font-size: 11px; font-weight: 700; }
.topic-head h2 { margin: 5px 0; font-size: 22px; letter-spacing: 0; }
.topic-head p, .table-toolbar span, .panel-title span { margin: 0; color: var(--text-secondary); font-size: 12px; }
.summary-strip { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); border: 1px solid var(--line-color); background: var(--card-bg); border-radius: 6px; }
.summary-strip > div { display: grid; grid-template-columns: auto 1fr; gap: 2px 8px; padding: 14px 18px; border-right: 1px solid var(--line-color); }
.summary-strip > div:last-child { border-right: 0; }
.summary-strip span { grid-column: 1 / -1; color: var(--text-secondary); font-size: 12px; }
.summary-strip strong { font-size: 25px; line-height: 1.1; }
.summary-strip strong.updated { font-size: 15px; align-self: center; }
.summary-strip small { align-self: end; color: var(--text-secondary); }
.analysis-grid { display: grid; grid-template-columns: 1.2fr .8fr; gap: 14px; }
.analysis-panel, .matches-panel { border: 1px solid var(--line-color); background: var(--card-bg); border-radius: 6px; overflow: hidden; }
.panel-title, .table-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 13px 16px; border-bottom: 1px solid var(--line-color); }
.panel-title h3, .table-toolbar h3 { margin: 0; font-size: 15px; }
.scorer-list { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); }
.scorer-row { display: grid; grid-template-columns: 22px 1fr auto; align-items: center; gap: 8px; min-width: 0; padding: 10px 12px; border-right: 1px solid var(--line-color); border-bottom: 1px solid var(--line-color); }
.scorer-row:nth-child(3n) { border-right: 0; }
.scorer-row .rank { color: var(--text-secondary); font-size: 11px; }
.scorer-row div { display: grid; min-width: 0; }
.scorer-row strong, .scorer-row small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.scorer-row small { color: var(--text-secondary); }
.scorer-row b { color: #55a6ff; font-size: 17px; }
.period-list { display: grid; gap: 10px; padding: 14px 16px; }
.period-row { display: grid; grid-template-columns: 56px 1fr 28px; align-items: center; gap: 10px; font-size: 12px; }
.period-row > div { height: 7px; overflow: hidden; background: var(--page-bg); border-radius: 2px; }
.period-row i { display: block; height: 100%; background: #55a6ff; }
.filters { display: flex; align-items: center; gap: 8px; }
.filters .el-select, .filters .el-input { width: 160px; }
.date-cell, .venue { color: var(--text-secondary); font-size: 12px; }
.team-cell { display: inline-flex; align-items: center; gap: 7px; font-weight: 600; }
.team-cell.home { justify-content: flex-end; }
.team-cell img { width: 22px; height: 22px; object-fit: contain; }
.score { font-size: 17px; }
.scheduled, .muted { color: var(--text-secondary); font-size: 12px; }
.score-note { display: block; color: #e6a23c; }
.goal-list { display: flex; flex-wrap: wrap; gap: 5px; padding: 5px 0; }
.goal-chip { display: inline-flex; align-items: center; gap: 4px; padding: 3px 6px; border: 1px solid rgba(85, 166, 255, .35); background: rgba(85, 166, 255, .08); border-radius: 4px; font-size: 11px; }
.goal-chip b { color: #55a6ff; }
.goal-chip em { color: #e6a23c; font-style: normal; }
.matches-panel :deep(.el-table) {
  --el-table-bg-color: var(--card-bg);
  --el-table-tr-bg-color: var(--card-bg);
  --el-table-header-bg-color: rgba(255, 255, 255, .025);
  --el-table-row-hover-bg-color: rgba(85, 166, 255, .08);
  --el-table-border-color: var(--line-color);
  --el-table-text-color: var(--text-primary);
  --el-table-header-text-color: var(--text-secondary);
}
.matches-panel :deep(.el-table__inner-wrapper::before) { background: var(--line-color); }
@media (max-width: 1180px) { .summary-strip { grid-template-columns: repeat(3, 1fr); } .analysis-grid { grid-template-columns: 1fr; } .scorer-list { grid-template-columns: repeat(2, 1fr); } .scorer-row:nth-child(3n) { border-right: 1px solid var(--line-color); } .scorer-row:nth-child(2n) { border-right: 0; } }
@media (max-width: 820px) { .topic-head, .table-toolbar { align-items: stretch; flex-direction: column; } .summary-strip { grid-template-columns: 1fr 1fr; } .filters { align-items: stretch; flex-direction: column; } .filters .el-select, .filters .el-input { width: 100%; } .scorer-list { grid-template-columns: 1fr; } }
</style>
