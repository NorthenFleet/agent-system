<template>
  <div class="finance-workspace">
    <header class="finance-head">
      <div>
        <h2>财务中心</h2>
        <p>项目经费、预算、报销、票据、付款与对账的统一工作台。</p>
      </div>
      <el-tag type="success" effect="dark">生产财务域</el-tag>
    </header>

    <el-card class="finance-nav" shadow="never">
      <el-menu :default-active="section" mode="horizontal" @select="navigate">
        <el-menu-item v-for="item in sections" :key="item.key" :index="item.key">{{ item.label }}</el-menu-item>
      </el-menu>
    </el-card>

    <component :is="activeComponent" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import FinanceBudget from './finance/FinanceBudget.vue'
import FinanceInvoices from './finance/FinanceInvoices.vue'
import FinanceOverview from './finance/FinanceOverview.vue'
import FinancePayments from './finance/FinancePayments.vue'
import FinanceReconciliation from './finance/FinanceReconciliation.vue'
import FinanceReimbursements from './finance/FinanceReimbursements.vue'
import FinanceReports from './finance/FinanceReports.vue'
import FinanceSettings from './finance/FinanceSettings.vue'

const route = useRoute()
const router = useRouter()
const sections = [
  { key: 'overview', label: '财务总览', component: FinanceOverview },
  { key: 'budget', label: '经费与预算', component: FinanceBudget },
  { key: 'reimbursements', label: '报销申请', component: FinanceReimbursements },
  { key: 'invoices', label: '发票中心', component: FinanceInvoices },
  { key: 'payments', label: '付款管理', component: FinancePayments },
  { key: 'reconciliation', label: '银行对账', component: FinanceReconciliation },
  { key: 'reports', label: '报表与审计', component: FinanceReports },
  { key: 'settings', label: '财务配置', component: FinanceSettings },
]
const section = computed(() => String(route.params.section || 'overview'))
const activeComponent = computed(() => sections.find(item => item.key === section.value)?.component || FinanceOverview)
function navigate(value: string) { router.push(`/finance/${value}`) }
</script>

<style scoped>
.finance-workspace { display: flex; flex-direction: column; gap: 16px; }
.finance-head { display: flex; align-items: center; justify-content: space-between; }
.finance-head h2 { margin: 0 0 6px; color: var(--el-text-color-primary); }
.finance-head p { margin: 0; color: var(--el-text-color-secondary); }
.finance-nav :deep(.el-card__body) { padding: 0 12px; }
.finance-nav :deep(.el-menu--horizontal) { border-bottom: 0; overflow-x: auto; }
</style>
