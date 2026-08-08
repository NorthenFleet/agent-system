<template>
  <section v-loading="loading" class="settings-page">
    <el-alert
      v-if="users.length < 2"
      title="正式审批需要至少两名启用用户"
      description="当前只有一个用户，无法同时满足申请与审批职责分离。请先在用户管理中创建审批用户，再授予审核角色。"
      type="warning"
      show-icon
      :closable="false"
    />

    <div class="settings-grid">
      <el-card shadow="never">
        <template #header>
          <div class="card-heading"><div><b>财务角色</b><small>授权决定可见项目和可执行动作</small></div><el-tag>{{ assignments.length }} 项</el-tag></div>
        </template>
        <el-form label-position="top" class="role-form">
          <el-form-item label="用户">
            <el-select v-model="roleForm.user_id" filterable>
              <el-option v-for="user in users" :key="user.id" :label="`${user.display_name} · ${user.username}`" :value="user.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="财务角色">
            <el-select v-model="roleForm.role"><el-option v-for="role in roleOptions" :key="role.value" :label="role.label" :value="role.value" /></el-select>
          </el-form-item>
          <el-form-item label="项目范围">
            <el-select v-model="roleForm.project_id" clearable placeholder="全局角色">
              <el-option v-for="project in projects" :key="project.id" :label="project.name" :value="project.id" />
            </el-select>
          </el-form-item>
          <el-button type="primary" @click="grant">授予角色</el-button>
        </el-form>
        <el-table :data="assignments" class="assignment-table" empty-text="尚未配置财务角色">
          <el-table-column label="用户" min-width="130"><template #default="{ row }"><b>{{ row.display_name }}</b><small>{{ row.username }}</small></template></el-table-column>
          <el-table-column label="角色" min-width="120"><template #default="{ row }">{{ roleLabel(row.role) }}</template></el-table-column>
          <el-table-column label="范围" min-width="150"><template #default="{ row }">{{ assignmentScope(row) }}</template></el-table-column>
        </el-table>
      </el-card>

      <el-card shadow="never">
        <template #header>
          <div class="card-heading"><div><b>审批工作流</b><small>提交时固化流程快照，后续修改不影响在途单据</small></div><el-button type="primary" @click="workflowDialog = true">新建流程</el-button></div>
        </template>
        <div class="workflow-list">
          <article v-for="workflow in workflows" :key="workflow.id">
            <div class="workflow-title">
              <div><b>{{ workflow.name }}</b><small>{{ workflowProject(workflow.project_id) }} · {{ amountRange(workflow.min_amount, workflow.max_amount) }}</small></div>
              <el-tag :type="workflow.is_active ? 'success' : 'info'">{{ workflow.is_active ? '已启用' : '已停用' }}</el-tag>
            </div>
            <div class="workflow-steps">
              <span v-for="(step, index) in workflow.steps" :key="step.id || index">
                <i>{{ index + 1 }}</i>{{ step.name }} · {{ step.assignee_role ? roleLabel(step.assignee_role) : userLabel(step.assignee_user_id) }}
              </span>
            </div>
          </article>
          <el-empty v-if="!workflows.length" description="尚未配置审批工作流，正式报销不能提交" />
        </div>
      </el-card>
    </div>

    <el-card shadow="never">
      <template #header><div class="card-heading"><div><b>历史数据迁移</b><small>导入是显式后台任务，日常查询不会扫描旧数据源</small></div></div></template>
      <div class="migration-actions"><el-button @click="importLegacy(true)">迁移预检</el-button><el-button type="warning" @click="importLegacy(false)">执行 SQLite 导入</el-button></div>
    </el-card>

    <el-dialog v-model="workflowDialog" title="新建审批工作流" width="720px">
      <el-form label-position="top">
        <div class="workflow-form-grid">
          <el-form-item label="流程名称"><el-input v-model="workflowForm.name" /></el-form-item>
          <el-form-item label="项目范围"><el-select v-model="workflowForm.project_id" clearable placeholder="全部项目"><el-option v-for="project in projects" :key="project.id" :label="project.name" :value="project.id" /></el-select></el-form-item>
          <el-form-item label="最低金额"><el-input-number v-model="workflowForm.min_amount" :min="0" :precision="2" /></el-form-item>
          <el-form-item label="最高金额"><el-input-number v-model="workflowForm.max_amount" :min="0.01" :precision="2" placeholder="不设上限" /></el-form-item>
          <el-form-item label="优先级"><el-input-number v-model="workflowForm.priority" :min="1" :max="10000" /></el-form-item>
        </div>
        <div class="step-heading"><b>审批步骤</b><el-button @click="addStep">添加步骤</el-button></div>
        <div v-for="(step, index) in workflowSteps" :key="index" class="step-row">
          <span class="step-index">{{ index + 1 }}</span>
          <el-input v-model="step.name" placeholder="步骤名称" />
          <el-segmented v-model="step.assignee_mode" :options="assigneeModes" />
          <el-select v-if="step.assignee_mode === 'role'" v-model="step.assignee_role">
            <el-option v-for="role in approvalRoleOptions" :key="role.value" :label="role.label" :value="role.value" />
          </el-select>
          <el-select v-else v-model="step.assignee_user_id" filterable placeholder="选择审批人">
            <el-option v-for="user in users" :key="user.id" :label="`${user.display_name} · ${user.username}`" :value="user.id" />
          </el-select>
          <el-button circle :disabled="workflowSteps.length === 1" title="删除步骤" @click="removeStep(index)">×</el-button>
        </div>
      </el-form>
      <template #footer><el-button @click="workflowDialog = false">取消</el-button><el-button type="primary" @click="createWorkflow">创建并启用</el-button></template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { financeApi, formatMoney, type ApprovalWorkflow, type FinanceProject, type FinanceRoleAssignment } from '@/api/finance'
import { listUsers } from '@/api/userAdmin'
import type { User } from '@/api/auth'

type WorkflowDraftStep = {
  name: string
  assignee_mode: 'role' | 'user'
  assignee_role: string
  assignee_user_id?: number
}

const loading = ref(false)
const projects = ref<FinanceProject[]>([])
const users = ref<User[]>([])
const assignments = ref<FinanceRoleAssignment[]>([])
const workflows = ref<ApprovalWorkflow[]>([])
const workflowDialog = ref(false)
const roleForm = reactive({ user_id: 1, role: 'applicant', project_id: '' })
const workflowForm = reactive<{ name: string; project_id: string; min_amount: number; max_amount?: number; priority: number }>({
  name: '', project_id: '', min_amount: 0, max_amount: undefined, priority: 100,
})
const workflowSteps = ref<WorkflowDraftStep[]>([
  { name: '财务复核', assignee_mode: 'role', assignee_role: 'reviewer' },
])
const assigneeModes = [{ label: '按角色', value: 'role' }, { label: '指定用户', value: 'user' }]
const roleOptions = [
  { value: 'finance_admin', label: '财务管理员' },
  { value: 'project_manager', label: '项目经理' },
  { value: 'applicant', label: '申请人' },
  { value: 'reviewer', label: '审核人' },
  { value: 'cashier', label: '出纳' },
  { value: 'auditor', label: '审计员' },
]
const approvalRoleOptions = roleOptions.filter(role => ['finance_admin', 'project_manager', 'reviewer'].includes(role.value))

function roleLabel(value?: string | null) { return roleOptions.find(role => role.value === value)?.label || value || '-' }
function userLabel(userId?: number | null) { const user = users.value.find(item => item.id === userId); return user ? user.display_name : `用户 ${userId || '-'}` }
function assignmentScope(assignment: FinanceRoleAssignment) { return assignment.projects.length ? assignment.projects.map(item => item.project_name).join('、') : '全局' }
function workflowProject(projectId?: string | null) { return projectId ? projects.value.find(project => project.id === projectId)?.name || '指定项目' : '全部项目' }
function amountRange(min: number, max?: number | null) { return max ? `${formatMoney(min)} - ${formatMoney(max)}` : `${formatMoney(min)} 起` }

async function load() {
  loading.value = true
  try {
    const [projectRows, userResult, roleRows, workflowRows] = await Promise.all([
      financeApi.projects(), listUsers(), financeApi.roles(), financeApi.workflows(),
    ])
    projects.value = projectRows
    users.value = userResult.users.filter(user => user.is_active)
    assignments.value = roleRows
    workflows.value = workflowRows
    if (!users.value.find(user => user.id === roleForm.user_id)) roleForm.user_id = users.value[0]?.id || 1
  } finally {
    loading.value = false
  }
}

async function grant() {
  await financeApi.grantRole({ ...roleForm, project_id: roleForm.project_id || null })
  ElMessage.success('财务角色已授权')
  await load()
}

function addStep() { workflowSteps.value.push({ name: '', assignee_mode: 'role', assignee_role: 'reviewer' }) }
function removeStep(index: number) { if (workflowSteps.value.length > 1) workflowSteps.value.splice(index, 1) }

async function createWorkflow() {
  if (!workflowForm.name.trim() || workflowSteps.value.some(step => !step.name.trim())) {
    ElMessage.warning('请填写流程名称和全部步骤名称')
    return
  }
  const steps = workflowSteps.value.map(step => ({
    name: step.name.trim(),
    assignee_role: step.assignee_mode === 'role' ? step.assignee_role : null,
    assignee_user_id: step.assignee_mode === 'user' ? step.assignee_user_id : null,
  }))
  if (steps.some(step => !step.assignee_role && !step.assignee_user_id)) {
    ElMessage.warning('每个审批步骤必须指定角色或用户')
    return
  }
  await financeApi.createWorkflow({
    name: workflowForm.name.trim(),
    project_id: workflowForm.project_id || null,
    min_amount: workflowForm.min_amount,
    max_amount: workflowForm.max_amount || null,
    priority: workflowForm.priority,
    steps,
  })
  workflowDialog.value = false
  workflowForm.name = ''
  workflowSteps.value = [{ name: '财务复核', assignee_mode: 'role', assignee_role: 'reviewer' }]
  ElMessage.success('审批工作流已创建')
  await load()
}

async function importLegacy(dry_run: boolean) {
  if (!dry_run) await ElMessageBox.confirm('将从只读历史 SQLite 导入到当前权威库，确认继续？', '执行迁移', { type: 'warning' })
  const result = await financeApi.createImport({ source_type: 'legacy_sqlite', dry_run })
  ElMessage.success(dry_run ? `预检完成：${JSON.stringify(result.result_payload || {})}` : '迁移任务已完成')
}

onMounted(load)
</script>

<style scoped>
.settings-page { display: grid; gap: 16px; }
.settings-grid { display: grid; grid-template-columns: minmax(420px, .9fr) minmax(520px, 1.1fr); gap: 16px; align-items: start; }
.card-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.card-heading small { display: block; margin-top: 5px; color: var(--el-text-color-secondary); font-weight: 400; }
.role-form { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)) auto; gap: 10px; align-items: end; }
.role-form .el-form-item { margin-bottom: 0; }
.role-form > .el-button { margin-bottom: 1px; }
.assignment-table { margin-top: 18px; }
.assignment-table small { display: block; margin-top: 3px; color: var(--el-text-color-secondary); }
.workflow-list { display: grid; gap: 10px; }
.workflow-list article { padding: 14px; border: 1px solid var(--el-border-color); border-radius: 6px; background: var(--el-fill-color-lighter); }
.workflow-title { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.workflow-title small { display: block; margin-top: 5px; color: var(--el-text-color-secondary); }
.workflow-steps { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.workflow-steps span { display: inline-flex; align-items: center; gap: 6px; padding: 6px 9px; border: 1px solid var(--el-border-color); border-radius: 4px; background: var(--el-bg-color); font-size: 12px; }
.workflow-steps i, .step-index { display: grid; place-items: center; width: 20px; height: 20px; border-radius: 50%; background: var(--el-color-primary-light-8); color: var(--el-color-primary); font-style: normal; font-weight: 700; }
.migration-actions { display: flex; gap: 10px; }
.workflow-form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 14px; }
.step-heading { display: flex; align-items: center; justify-content: space-between; margin: 8px 0 12px; }
.step-row { display: grid; grid-template-columns: 28px minmax(120px, 1fr) 190px minmax(160px, 1fr) 32px; gap: 8px; align-items: center; margin-bottom: 8px; }
@media (max-width: 1280px) {
  .settings-grid { grid-template-columns: 1fr; }
}
@media (max-width: 860px) {
  .role-form, .workflow-form-grid { grid-template-columns: 1fr; }
  .step-row { grid-template-columns: 28px 1fr; }
  .step-row > :not(.step-index) { grid-column: 2; width: 100%; }
}
</style>
