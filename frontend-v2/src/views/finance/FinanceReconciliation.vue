<template>
  <section v-loading="loading" class="reconciliation-page">
    <el-alert
      title="智能体和规则仅生成匹配建议"
      description="银行流水、付款单、金额和收款方必须由出纳或财务管理员人工核对后确认；系统不会自动把建议写成最终对账结果。"
      type="info"
      show-icon
      :closable="false"
    />
    <div class="toolbar">
      <el-upload :show-file-list="false" :auto-upload="false" accept=".csv,.xlsx" :on-change="change"><el-button type="primary">导入银行流水</el-button></el-upload>
      <el-button :disabled="!selected.length" type="success" @click="openConfirm">核对所选匹配</el-button>
      <el-button @click="load">刷新</el-button>
    </div>
    <el-card shadow="never">
      <el-table :data="records" @selection-change="selectionChanged">
        <el-table-column type="selection" width="50" :selectable="selectable" />
        <el-table-column label="银行交易" min-width="210">
          <template #default="{ row }"><b>{{ row.bank_transaction?.transaction_ref || row.bank_transaction_id }}</b><small>{{ row.bank_transaction?.transaction_date }} · {{ row.bank_transaction?.counterparty || '未知对手方' }}</small></template>
        </el-table-column>
        <el-table-column label="付款记录" min-width="210">
          <template #default="{ row }"><b>{{ row.payment?.payment_no || row.payment_id }}</b><small>{{ row.payment?.payee_name || '-' }} · {{ row.payment?.payee_account_masked || '-' }}</small></template>
        </el-table-column>
        <el-table-column label="匹配金额" width="140"><template #default="{ row }">{{ formatMoney(row.matched_amount) }}</template></el-table-column>
        <el-table-column label="置信度" width="150"><template #default="{ row }"><el-progress :percentage="Math.round(Number(row.confidence) * 100)" /></template></el-table-column>
        <el-table-column label="状态" width="120"><template #default="{ row }"><el-tag :type="row.status === 'confirmed' ? 'success' : 'warning'">{{ row.status === 'confirmed' ? '已确认' : '建议' }}</el-tag></template></el-table-column>
        <el-table-column prop="confirmation_note" label="人工核对说明" min-width="180" />
      </el-table>
    </el-card>

    <el-dialog v-model="confirmDialog" title="人工确认对账匹配" width="580px">
      <div class="selection-summary"><strong>{{ selected.length }}</strong><span>条建议</span><strong>{{ formatMoney(selectedTotal) }}</strong><span>匹配金额</span></div>
      <el-form label-position="top">
        <el-form-item label="核对说明"><el-input v-model="confirmationNote" type="textarea" :rows="3" placeholder="例如：已逐项核对交易日期、金额、收款方和银行流水号" /></el-form-item>
        <el-checkbox v-model="humanConfirmed">我已人工核对所选银行流水与付款记录</el-checkbox>
      </el-form>
      <template #footer><el-button @click="confirmDialog = false">取消</el-button><el-button type="success" :disabled="!canConfirm" @click="confirm">确认对账</el-button></template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, type UploadFile } from 'element-plus'
import { financeApi, formatMoney, type ReconciliationMatch } from '@/api/finance'

const loading = ref(false)
const records = ref<ReconciliationMatch[]>([])
const selected = ref<ReconciliationMatch[]>([])
const confirmDialog = ref(false)
const humanConfirmed = ref(false)
const confirmationNote = ref('')
const selectedTotal = computed(() => selected.value.reduce((sum, item) => sum + Number(item.matched_amount), 0))
const canConfirm = computed(() => humanConfirmed.value && confirmationNote.value.trim().length >= 2)

function selectionChanged(rows: ReconciliationMatch[]) { selected.value = rows }
function selectable(row: ReconciliationMatch) { return row.status === 'suggested' }

async function load() {
  loading.value = true
  try { records.value = await financeApi.reconciliations() } finally { loading.value = false }
}

async function change(file: UploadFile) {
  if (!file.raw) return
  await financeApi.importStatement(file.raw)
  ElMessage.success('银行流水已脱敏导入，并生成待人工核对的匹配建议')
  await load()
}

function openConfirm() {
  confirmationNote.value = ''
  humanConfirmed.value = false
  confirmDialog.value = true
}

async function confirm() {
  if (!canConfirm.value) return
  await financeApi.confirmReconciliations(selected.value.map(item => item.id), confirmationNote.value.trim())
  confirmDialog.value = false
  ElMessage.success('对账匹配已人工确认')
  selected.value = []
  await load()
}

onMounted(load)
</script>

<style scoped>
.reconciliation-page { display: grid; gap: 16px; }
.toolbar { display: flex; flex-wrap: wrap; gap: 10px; }
.el-table small { display: block; margin-top: 5px; color: var(--el-text-color-secondary); }
.selection-summary { display: grid; grid-template-columns: auto 1fr auto 1fr; gap: 8px; align-items: baseline; margin-bottom: 18px; padding: 14px; border: 1px solid var(--el-border-color); border-radius: 6px; background: var(--el-fill-color-lighter); }
.selection-summary strong { color: var(--el-color-primary); font-size: 22px; }
.selection-summary span { color: var(--el-text-color-secondary); }
</style>
