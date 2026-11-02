<template>
  <div class="finance-reimbursements">
    <!-- 统计卡片 -->
    <el-row :gutter="16" class="stat-row">
      <el-col :span="6" v-for="stat in stats" :key="stat.label">
        <el-card shadow="hover" class="stat-card" :class="stat.type">
          <div class="stat-value">{{ stat.value }}</div>
          <div class="stat-label">{{ stat.label }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 操作栏 -->
    <el-card shadow="never" class="toolbar-card">
      <el-row :gutter="16" align="middle">
        <el-col :span="12">
          <el-button type="primary" @click="showCreateDialog = true">
            <el-icon><Plus /></el-icon>
            新建报销单
          </el-button>
          <el-button @click="refreshList">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </el-col>
        <el-col :span="12" class="filter-col">
          <el-select v-model="filterStatus" placeholder="状态筛选" clearable @change="fetchList">
            <el-option label="草稿" value="draft" />
            <el-option label="已提交" value="submitted" />
            <el-option label="审批中" value="in_review" />
            <el-option label="已通过" value="approved" />
            <el-option label="已拒绝" value="rejected" />
            <el-option label="已付款" value="paid" />
          </el-select>
          <el-select v-model="filterCategory" placeholder="类别筛选" clearable @change="fetchList">
            <el-option label="差旅" value="travel" />
            <el-option label="办公用品" value="office" />
            <el-option label="餐饮" value="meal" />
            <el-option label="交通" value="transport" />
            <el-option label="培训" value="training" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-col>
      </el-row>
    </el-card>

    <!-- 报销单列表 -->
    <el-card shadow="never">
      <el-table :data="reimbursements" v-loading="loading" stripe>
        <el-table-column prop="code" label="单号" width="160" />
        <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
        <el-table-column prop="amount" label="金额" width="120" align="right">
          <template #default="{ row }">
            <span class="amount">¥{{ row.amount.toFixed(2) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="类别" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{ categoryMap[row.category] || row.category }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">
              {{ statusMap[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="applicant_name" label="申请人" width="100" />
        <el-table-column prop="created_at" label="创建时间" width="160">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="viewDetail(row)">详情</el-button>
            <el-button link type="warning" v-if="row.status === 'draft'" @click="submitReimbursement(row)">提交</el-button>
            <el-button link type="danger" v-if="row.status === 'draft'" @click="deleteReimbursement(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        @size-change="fetchList"
        @current-change="fetchList"
        class="pagination"
      />
    </el-card>

    <!-- 创建报销单对话框 -->
    <el-dialog v-model="showCreateDialog" title="新建报销单" width="600px">
      <el-form :model="createForm" label-width="100px">
        <el-form-item label="报销标题" required>
          <el-input v-model="createForm.title" placeholder="请输入报销标题" />
        </el-form-item>
        <el-form-item label="报销金额" required>
          <el-input-number v-model="createForm.amount" :min="0" :precision="2" :step="100" />
        </el-form-item>
        <el-form-item label="报销类别" required>
          <el-select v-model="createForm.category" placeholder="请选择类别">
            <el-option label="差旅" value="travel" />
            <el-option label="办公用品" value="office" />
            <el-option label="餐饮" value="meal" />
            <el-option label="交通" value="transport" />
            <el-option label="培训" value="training" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="报销说明">
          <el-input v-model="createForm.description" type="textarea" :rows="3" placeholder="请输入报销说明" />
        </el-form-item>
        <el-form-item label="所属部门">
          <el-input v-model="createForm.department" placeholder="请输入所属部门" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="createReimbursement" :loading="creating">创建</el-button>
      </template>
    </el-dialog>

    <!-- 详情对话框 -->
    <el-dialog v-model="showDetailDialog" title="报销单详情" width="700px">
      <div v-if="currentReimbursement" class="detail-content">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="报销单号">{{ currentReimbursement.code }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusType(currentReimbursement.status)">
              {{ statusMap[currentReimbursement.status] }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="报销标题" :span="2">{{ currentReimbursement.title }}</el-descriptions-item>
          <el-descriptions-item label="报销金额">
            <span class="amount">¥{{ currentReimbursement.amount?.toFixed(2) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="报销类别">
            <el-tag size="small">{{ categoryMap[currentReimbursement.category] }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="申请人">{{ currentReimbursement.applicant_name }}</el-descriptions-item>
          <el-descriptions-item label="所属部门">{{ currentReimbursement.department }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatDate(currentReimbursement.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="提交时间">{{ formatDate(currentReimbursement.submitted_at) }}</el-descriptions-item>
          <el-descriptions-item label="报销说明" :span="2">{{ currentReimbursement.description || '-' }}</el-descriptions-item>
        </el-descriptions>

        <!-- 审批记录 -->
        <div v-if="currentReimbursement.approval_records?.length" class="approval-section">
          <h4>审批记录</h4>
          <el-timeline>
            <el-timeline-item
              v-for="(record, index) in currentReimbursement.approval_records"
              :key="index"
              :type="record.action === 'approve' ? 'success' : record.action === 'reject' ? 'danger' : 'warning'"
              :timestamp="formatDate(record.created_at)"
            >
              <div class="approval-record">
                <strong>{{ record.approver_name }}</strong>
                <el-tag size="small" :type="record.action === 'approve' ? 'success' : record.action === 'reject' ? 'danger' : 'warning'">
                  {{ actionMap[record.action] }}
                </el-tag>
                <p v-if="record.comment">{{ record.comment }}</p>
              </div>
            </el-timeline-item>
          </el-timeline>
        </div>

        <!-- 审批操作 -->
        <div v-if="currentReimbursement.status === 'submitted' || currentReimbursement.status === 'in_review'" class="approval-actions">
          <el-input v-model="approvalComment" type="textarea" :rows="2" placeholder="请输入审批意见" />
          <div class="action-buttons">
            <el-button type="success" @click="approveReimbursement('approve')" :loading="approving">通过</el-button>
            <el-button type="danger" @click="approveReimbursement('reject')" :loading="approving">拒绝</el-button>
            <el-button type="warning" @click="approveReimbursement('return')" :loading="approving">退回</el-button>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { request } from '@/utils/request'

// 状态映射
const statusMap: Record<string, string> = {
  draft: '草稿',
  submitted: '已提交',
  in_review: '审批中',
  approved: '已通过',
  rejected: '已拒绝',
  paid: '已付款',
  archived: '已归档'
}

const categoryMap: Record<string, string> = {
  travel: '差旅',
  office: '办公用品',
  meal: '餐饮',
  transport: '交通',
  training: '培训',
  other: '其他'
}

const actionMap: Record<string, string> = {
  approve: '通过',
  reject: '拒绝',
  return: '退回',
  transfer: '转交'
}

// 状态类型
const statusType = (status: string) => {
  const map: Record<string, string> = {
    draft: 'info',
    submitted: 'warning',
    in_review: 'warning',
    approved: 'success',
    rejected: 'danger',
    paid: 'success'
  }
  return map[status] || 'info'
}

// 统计数据
const stats = ref([
  { label: '报销单总数', value: 0, type: 'total' },
  { label: '待审批', value: 0, type: 'pending' },
  { label: '已通过', value: 0, type: 'approved' },
  { label: '总金额', value: '¥0', type: 'amount' }
])

// 列表数据
const reimbursements = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

// 筛选
const filterStatus = ref('')
const filterCategory = ref('')

// 创建表单
const showCreateDialog = ref(false)
const creating = ref(false)
const createForm = reactive({
  title: '',
  amount: 0,
  category: '',
  description: '',
  department: ''
})

// 详情
const showDetailDialog = ref(false)
const currentReimbursement = ref(null)
const approvalComment = ref('')
const approving = ref(false)

// 获取统计数据
const fetchStatistics = async () => {
  try {
    const res = await request.get('/finance/workflow/statistics')
    const data = res.data
    stats.value = [
      { label: '报销单总数', value: data.total_reimbursements, type: 'total' },
      { label: '待审批', value: data.pending_count, type: 'pending' },
      { label: '已通过', value: data.approved_count, type: 'approved' },
      { label: '总金额', value: `¥${data.total_amount?.toFixed(2) || '0.00'}`, type: 'amount' }
    ]
  } catch (e) {
    console.error('获取统计失败', e)
  }
}

// 获取列表
const fetchList = async () => {
  loading.value = true
  try {
    const params: any = {
      page: page.value,
      page_size: pageSize.value
    }
    if (filterStatus.value) params.status = filterStatus.value
    if (filterCategory.value) params.category = filterCategory.value

    const res = await request.get('/finance/workflow/reimbursements', { params })
    reimbursements.value = res.data.items
    total.value = res.data.total
  } catch (e) {
    ElMessage.error('获取报销单列表失败')
  } finally {
    loading.value = false
  }
}

// 刷新列表
const refreshList = () => {
  fetchList()
  fetchStatistics()
}

// 创建报销单
const createReimbursement = async () => {
  if (!createForm.title || !createForm.amount || !createForm.category) {
    ElMessage.warning('请填写必填项')
    return
  }

  creating.value = true
  try {
    await request.post('/finance/workflow/reimbursements?applicant_id=1', createForm)
    ElMessage.success('报销单创建成功')
    showCreateDialog.value = false
    Object.assign(createForm, { title: '', amount: 0, category: '', description: '', department: '' })
    refreshList()
  } catch (e) {
    ElMessage.error('创建失败')
  } finally {
    creating.value = false
  }
}

// 查看详情
const viewDetail = async (row: any) => {
  try {
    const res = await request.get(`/finance/workflow/reimbursements/${row.id}`)
    currentReimbursement.value = res.data
    showDetailDialog.value = true
  } catch (e) {
    ElMessage.error('获取详情失败')
  }
}

// 提交报销单
const submitReimbursement = async (row: any) => {
  try {
    await ElMessageBox.confirm('确认提交该报销单？提交后将启动审批流程。', '提示', {
      type: 'warning'
    })
    await request.post(`/finance/workflow/reimbursements/${row.id}/submit`)
    ElMessage.success('报销单已提交')
    refreshList()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('提交失败')
    }
  }
}

// 删除报销单
const deleteReimbursement = async (row: any) => {
  try {
    await ElMessageBox.confirm('确认删除该报销单？此操作不可恢复。', '警告', {
      type: 'warning'
    })
    await request.delete(`/finance/workflow/reimbursements/${row.id}`)
    ElMessage.success('报销单已删除')
    refreshList()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

// 审批报销单
const approveReimbursement = async (action: string) => {
  if (!currentReimbursement.value) return

  approving.value = true
  try {
    await request.post(
      `/finance/workflow/reimbursements/${currentReimbursement.value.id}/approve?approver_id=1&approver_name=审批人`,
      { action, comment: approvalComment.value }
    )
    ElMessage.success('审批完成')
    showDetailDialog.value = false
    approvalComment.value = ''
    refreshList()
  } catch (e) {
    ElMessage.error('审批失败')
  } finally {
    approving.value = false
  }
}

// 格式化日期
const formatDate = (dateStr: string) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

onMounted(() => {
  refreshList()
})
</script>

<style scoped>
.finance-reimbursements {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.stat-row {
  margin-bottom: 8px;
}

.stat-card {
  text-align: center;
  padding: 20px;
}

.stat-card.total { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }
.stat-card.pending { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: white; }
.stat-card.approved { background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); color: white; }
.stat-card.amount { background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%); color: white; }

.stat-value {
  font-size: 28px;
  font-weight: bold;
  margin-bottom: 8px;
}

.stat-label {
  font-size: 14px;
  opacity: 0.9;
}

.toolbar-card :deep(.el-card__body) {
  padding: 16px;
}

.filter-col {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.amount {
  color: #f56c6c;
  font-weight: bold;
}

.pagination {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.detail-content {
  max-height: 60vh;
  overflow-y: auto;
}

.approval-section {
  margin-top: 24px;
}

.approval-section h4 {
  margin-bottom: 16px;
  color: var(--el-text-color-primary);
}

.approval-record {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.approval-record p {
  width: 100%;
  margin: 8px 0 0;
  color: var(--el-text-color-secondary);
}

.approval-actions {
  margin-top: 24px;
  padding-top: 24px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.action-buttons {
  margin-top: 12px;
  display: flex;
  gap: 12px;
}
</style>
