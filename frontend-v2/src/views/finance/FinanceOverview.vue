<template>
  <section v-loading="loading">
    <el-alert v-if="error" :title="error" type="error" show-icon class="block" />
    <el-row :gutter="16" class="block">
      <el-col v-for="metric in metrics" :key="metric.label" :xs="12" :sm="8" :lg="6">
        <el-card class="metric" shadow="hover"><span>{{ metric.label }}</span><strong>{{ metric.value }}</strong></el-card>
      </el-col>
    </el-row>
    <el-card shadow="never">
      <template #header><div class="header"><b>近期报销</b><el-button @click="load">刷新</el-button></div></template>
      <el-table :data="dashboard?.recent_reimbursements || []" empty-text="暂无报销记录">
        <el-table-column prop="reimbursement_no" label="单号" min-width="190" />
        <el-table-column prop="title" label="标题" min-width="200" />
        <el-table-column prop="total_amount" label="金额" width="140"><template #default="{ row }">{{ formatMoney(row.total_amount) }}</template></el-table-column>
        <el-table-column prop="status" label="状态" width="130"><template #default="{ row }"><el-tag>{{ statusLabel(row.status) }}</el-tag></template></el-table-column>
        <el-table-column prop="created_at" label="创建时间" min-width="190" />
      </el-table>
    </el-card>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { financeApi, formatMoney, type Dashboard } from '@/api/finance'
const dashboard = ref<Dashboard | null>(null); const loading = ref(false); const error = ref('')
const metrics = computed(() => {
  const s = dashboard.value?.summary
  return [
    { label: '项目总预算', value: formatMoney(s?.budget_amount) },
    { label: '预算占用', value: formatMoney(s?.reserved_amount) },
    { label: '已支出', value: formatMoney(s?.spent_amount) },
    { label: '可用预算', value: formatMoney(s?.available_amount) },
    { label: '待付款', value: String(s?.pending_payments || 0) },
    { label: '待对账流水', value: String(s?.unmatched_transactions || 0) },
    { label: '发票', value: String(s?.invoices || 0) },
  ]
})
const labels: Record<string, string> = { draft: '草稿', submitted: '已提交', in_review: '审批中', returned: '已退回', approved: '已通过', payment_pending: '待付款', paid: '已付款', archived: '已归档', rejected: '已驳回', cancelled: '已取消' }
const statusLabel = (value: string) => labels[value] || value
async function load() { loading.value = true; error.value = ''; try { dashboard.value = await financeApi.dashboard() } catch (e: any) { error.value = e?.response?.data?.detail?.message || '财务总览加载失败' } finally { loading.value = false } }
onMounted(load)
</script>
<style scoped>
.block { margin-bottom: 16px; }.metric { margin-bottom: 16px; }.metric span { display:block;color:var(--el-text-color-secondary);font-size:13px}.metric strong{display:block;margin-top:10px;font-size:24px}.header{display:flex;justify-content:space-between;align-items:center}
</style>
