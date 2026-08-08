<template>
  <section v-loading="loading" class="payments-page">
    <el-alert
      title="系统不直接发起银行转账"
      description="付款登记、银行实际操作和系统确认是三个独立动作。只有人工核对银行回单后，预算才会从占用转为支出。"
      type="warning"
      show-icon
      :closable="false"
    />
    <div class="toolbar"><el-button type="primary" @click="open">登记付款</el-button><el-button @click="load">刷新</el-button></div>
    <el-card shadow="never">
      <el-table :data="payments">
        <el-table-column prop="payment_no" label="付款单号" min-width="190" />
        <el-table-column prop="payee_name" label="收款方" min-width="140" />
        <el-table-column label="金额" width="140"><template #default="{ row }">{{ formatMoney(row.amount) }}</template></el-table-column>
        <el-table-column prop="payee_account_masked" label="脱敏账号" min-width="130" />
        <el-table-column label="状态" width="110"><template #default="{ row }"><el-tag :type="row.status === 'pending' ? 'warning' : 'success'">{{ statusLabel(row.status) }}</el-tag></template></el-table-column>
        <el-table-column prop="bank_reference" label="银行流水" min-width="150" />
        <el-table-column label="人工确认" min-width="170"><template #default="{ row }"><span v-if="row.confirmed_by_user_id">用户 {{ row.confirmed_by_user_id }} · {{ row.confirmation_note }}</span><span v-else class="muted">未确认</span></template></el-table-column>
        <el-table-column label="操作" width="130"><template #default="{ row }"><el-button v-if="row.status === 'pending'" size="small" type="success" @click="openConfirm(row)">核对回单</el-button></template></el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialog" title="登记待付款" width="540px">
      <el-form label-width="90px">
        <el-form-item label="报销单"><el-select v-model="form.reimbursement_id"><el-option v-for="item in approved" :key="item.id" :label="`${item.reimbursement_no} · ${formatMoney(item.total_amount)}`" :value="item.id" /></el-select></el-form-item>
        <el-form-item label="收款方"><el-input v-model="form.payee_name" /></el-form-item>
        <el-form-item label="收款账号"><el-input v-model="form.payee_account" show-password /></el-form-item>
        <el-form-item label="计划付款"><el-date-picker v-model="form.scheduled_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ssZ" /></el-form-item>
      </el-form>
      <p class="safety-note">完整账号仅用于当前登记过程，后端只保存末四位脱敏结果。</p>
      <template #footer><el-button @click="dialog = false">取消</el-button><el-button type="primary" @click="create">保存待付款</el-button></template>
    </el-dialog>

    <el-dialog v-model="confirmDialog" title="人工核对银行回单" width="560px">
      <div v-if="selectedPayment" class="confirm-summary">
        <div><span>收款方</span><b>{{ selectedPayment.payee_name }}</b></div>
        <div><span>付款金额</span><b>{{ formatMoney(selectedPayment.amount) }}</b></div>
        <div><span>脱敏账号</span><b>{{ selectedPayment.payee_account_masked || '-' }}</b></div>
      </div>
      <el-form label-position="top">
        <el-form-item label="银行流水号"><el-input v-model="confirmation.bank_reference" /></el-form-item>
        <el-form-item label="核对说明"><el-input v-model="confirmation.confirmation_note" type="textarea" :rows="3" placeholder="例如：已核对网银回单中的收款方、金额、账号末四位和付款时间" /></el-form-item>
        <el-checkbox v-model="confirmation.human_confirmed">我已人工核对银行回单，确认这笔付款真实完成</el-checkbox>
      </el-form>
      <template #footer><el-button @click="confirmDialog = false">取消</el-button><el-button type="success" :disabled="!canConfirm" @click="performConfirm">确认并计入支出</el-button></template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { financeApi, formatMoney, type Payment, type Reimbursement } from '@/api/finance'

const loading = ref(false)
const dialog = ref(false)
const confirmDialog = ref(false)
const payments = ref<Payment[]>([])
const approved = ref<Reimbursement[]>([])
const selectedPayment = ref<Payment | null>(null)
const form = reactive({ reimbursement_id: '', payee_name: '', payee_account: '', scheduled_at: '' })
const confirmation = reactive({ bank_reference: '', confirmation_note: '', human_confirmed: false })
const canConfirm = computed(() => Boolean(
  confirmation.human_confirmed
  && confirmation.bank_reference.trim()
  && confirmation.confirmation_note.trim().length >= 2,
))

function statusLabel(value: string) { return ({ pending: '待确认', paid: '已付款', reconciled: '已对账', cancelled: '已取消' } as Record<string, string>)[value] || value }

async function load() {
  loading.value = true
  try {
    [payments.value, approved.value] = await Promise.all([financeApi.payments(), financeApi.reimbursements('approved')])
  } finally {
    loading.value = false
  }
}

async function open() {
  await load()
  form.reimbursement_id = approved.value[0]?.id || ''
  form.payee_name = ''
  form.payee_account = ''
  form.scheduled_at = ''
  dialog.value = true
}

async function create() {
  await financeApi.createPayment({ ...form, scheduled_at: form.scheduled_at || null })
  form.payee_account = ''
  dialog.value = false
  ElMessage.success('待付款已登记，尚未计入支出')
  await load()
}

function openConfirm(payment: Payment) {
  selectedPayment.value = payment
  confirmation.bank_reference = ''
  confirmation.confirmation_note = ''
  confirmation.human_confirmed = false
  confirmDialog.value = true
}

async function performConfirm() {
  if (!selectedPayment.value || !canConfirm.value) return
  await financeApi.confirmPayment(selectedPayment.value.id, {
    version: selectedPayment.value.lock_version,
    bank_reference: confirmation.bank_reference.trim(),
    paid_at: new Date().toISOString(),
    human_confirmed: true,
    confirmation_note: confirmation.confirmation_note.trim(),
  })
  confirmDialog.value = false
  ElMessage.success('付款已人工确认并计入支出')
  await load()
}

onMounted(load)
</script>

<style scoped>
.payments-page { display: grid; gap: 16px; }
.toolbar { display: flex; gap: 10px; }
.muted, .safety-note { color: var(--el-text-color-secondary); }
.safety-note { margin: 0; font-size: 12px; line-height: 1.6; }
.confirm-summary { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; margin-bottom: 18px; border: 1px solid var(--el-border-color); background: var(--el-border-color); }
.confirm-summary div { display: grid; gap: 6px; padding: 12px; background: var(--el-bg-color); }
.confirm-summary span { color: var(--el-text-color-secondary); font-size: 12px; }
@media (max-width: 640px) { .confirm-summary { grid-template-columns: 1fr; } }
</style>
