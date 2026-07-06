<template>
  <div class="user-admin-page">
    <el-row :gutter="16">
      <el-col :span="10">
        <el-card class="panel" shadow="hover">
          <template #header>
            <div class="panel-header">
              <div>
                <h2>用户管理</h2>
                <p class="muted">用户账号、角色和启用状态</p>
              </div>
              <el-button type="primary" size="small" @click="openCreateDialog">新建用户</el-button>
            </div>
          </template>

          <el-table
            v-loading="loading"
            :data="users"
            row-key="id"
            highlight-current-row
            @current-change="selectUser"
          >
            <el-table-column prop="display_name" label="用户" min-width="130">
              <template #default="{ row }">
                <div class="user-cell">
                  <strong>{{ row.display_name }}</strong>
                  <span>{{ row.username }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="role" label="角色" width="88">
              <template #default="{ row }">
                <el-tag size="small" :type="row.role === 'admin' ? 'danger' : row.role === 'agent' ? 'warning' : 'info'">
                  {{ roleLabel(row.role) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="is_active" label="状态" width="78">
              <template #default="{ row }">
                <el-tag size="small" :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="14">
        <el-card class="panel" shadow="hover">
          <template #header>
            <div class="panel-header">
              <div>
                <h2>模块权限</h2>
                <p class="muted">{{ selectedUser ? `${selectedUser.display_name} 登录后可见的功能模块` : '请选择用户' }}</p>
              </div>
              <div class="panel-actions">
                <el-button size="small" :disabled="!selectedUser" @click="selectAllModules">全选</el-button>
                <el-button size="small" :disabled="!selectedUser || selectedUser.role === 'admin'" @click="clearModules">清空</el-button>
                <el-button size="small" type="primary" :loading="savingModules" :disabled="!selectedUser" @click="saveModules">
                  保存权限
                </el-button>
              </div>
            </div>
          </template>

          <el-empty v-if="!selectedUser" description="请选择左侧用户" />
          <template v-else>
            <div class="profile-editor">
              <el-input v-model="editForm.display_name" placeholder="显示名称" />
              <el-select v-model="editForm.role" :disabled="selectedUser.role === 'admin'" placeholder="角色">
                <el-option label="管理员" value="admin" />
                <el-option label="智能体成员" value="agent" />
                <el-option label="观察者" value="viewer" />
              </el-select>
              <el-select v-model="editForm.is_active" placeholder="状态">
                <el-option label="启用" :value="true" />
                <el-option label="停用" :value="false" />
              </el-select>
              <el-button :loading="savingUser" @click="saveUser">保存用户</el-button>
            </div>

            <div class="module-grid">
              <label
                v-for="module in modules"
                :key="module.module_key"
                class="module-card"
                :class="{ checked: selectedModuleKeys.includes(module.module_key), disabled: selectedUser.role === 'admin' }"
              >
                <el-checkbox
                  :model-value="selectedModuleKeys.includes(module.module_key)"
                  :disabled="selectedUser.role === 'admin'"
                  @change="toggleModule(module.module_key, Boolean($event))"
                />
                <div>
                  <strong>{{ module.name }}</strong>
                  <span>{{ module.route_path }}</span>
                  <p>{{ module.description || '暂无说明' }}</p>
                </div>
              </label>
            </div>
          </template>
        </el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="createDialogVisible" title="新建用户" width="520px">
      <div class="create-form">
        <el-input v-model="createForm.username" placeholder="用户名" />
        <el-input v-model="createForm.display_name" placeholder="显示名称" />
        <el-input v-model="createForm.password" placeholder="初始密码" show-password />
        <el-select v-model="createForm.role" placeholder="角色">
          <el-option label="管理员" value="admin" />
          <el-option label="智能体成员" value="agent" />
          <el-option label="观察者" value="viewer" />
        </el-select>
      </div>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="submitCreateUser">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FeatureModule, User, UserRole } from '@/api/auth'
import {
  createUser,
  getUserModules,
  listModules,
  listUsers,
  updateUser,
  updateUserModules
} from '@/api/userAdmin'

const loading = ref(false)
const users = ref<User[]>([])
const modules = ref<FeatureModule[]>([])
const selectedUser = ref<User | null>(null)
const selectedModuleKeys = ref<string[]>([])
const savingModules = ref(false)
const savingUser = ref(false)
const creating = ref(false)
const createDialogVisible = ref(false)

const editForm = reactive({
  display_name: '',
  role: 'viewer' as UserRole,
  is_active: true
})

const createForm = reactive({
  username: '',
  display_name: '',
  password: '',
  role: 'viewer' as UserRole
})

function roleLabel(role: string) {
  return { admin: '管理员', agent: '成员', viewer: '观察者' }[role] || role
}

async function loadAll() {
  loading.value = true
  try {
    const [userRes, moduleRes] = await Promise.all([listUsers(), listModules()])
    users.value = userRes.users
    modules.value = moduleRes.modules.filter(item => item.is_enabled !== false)
    if (!selectedUser.value && users.value.length) {
      await selectUser(users.value[0])
    }
  } finally {
    loading.value = false
  }
}

async function selectUser(user: User | null) {
  if (!user) return
  selectedUser.value = user
  editForm.display_name = user.display_name
  editForm.role = user.role
  editForm.is_active = user.is_active
  const data = await getUserModules(user.id)
  selectedModuleKeys.value = data.module_keys
}

function toggleModule(moduleKey: string, checked: boolean) {
  if (!selectedUser.value || selectedUser.value.role === 'admin') return
  const next = new Set(selectedModuleKeys.value)
  if (checked) next.add(moduleKey)
  else next.delete(moduleKey)
  selectedModuleKeys.value = Array.from(next)
}

function selectAllModules() {
  selectedModuleKeys.value = modules.value.map(item => item.module_key)
}

function clearModules() {
  selectedModuleKeys.value = []
}

async function saveModules() {
  if (!selectedUser.value) return
  savingModules.value = true
  try {
    const data = await updateUserModules(selectedUser.value.id, selectedModuleKeys.value)
    selectedModuleKeys.value = data.module_keys
    ElMessage.success('模块权限已保存')
  } finally {
    savingModules.value = false
  }
}

async function saveUser() {
  if (!selectedUser.value) return
  savingUser.value = true
  try {
    const data = await updateUser(selectedUser.value.id, {
      display_name: editForm.display_name,
      role: editForm.role,
      is_active: editForm.is_active
    })
    const index = users.value.findIndex(item => item.id === data.user.id)
    if (index >= 0) users.value[index] = data.user
    selectedUser.value = data.user
    ElMessage.success('用户信息已保存')
    await selectUser(data.user)
  } finally {
    savingUser.value = false
  }
}

function openCreateDialog() {
  createForm.username = ''
  createForm.display_name = ''
  createForm.password = ''
  createForm.role = 'viewer'
  createDialogVisible.value = true
}

async function submitCreateUser() {
  if (!createForm.username || !createForm.password || !createForm.display_name) {
    ElMessage.warning('请填写用户名、显示名称和密码')
    return
  }
  creating.value = true
  try {
    const data = await createUser({ ...createForm })
    users.value.unshift(data.user)
    createDialogVisible.value = false
    ElMessage.success('用户已创建')
    await selectUser(data.user)
  } finally {
    creating.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.user-admin-page {
  min-height: 100%;
}

.panel {
  border-radius: 8px;
}

.panel-header,
.panel-actions,
.profile-editor {
  display: flex;
  align-items: center;
  gap: 10px;
}

.panel-header {
  justify-content: space-between;
}

.panel-header h2 {
  margin: 0 0 4px;
  color: var(--text-primary);
  font-size: 18px;
}

.muted {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
}

.user-cell {
  display: grid;
  gap: 2px;
}

.user-cell strong {
  color: var(--text-primary);
}

.user-cell span {
  color: var(--text-secondary);
  font-size: 12px;
}

.profile-editor {
  margin-bottom: 14px;
}

.module-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.module-card {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 8px;
  padding: 12px;
  border: 1px solid var(--line-color);
  border-radius: 8px;
  background: var(--card-bg-soft);
}

.module-card.checked {
  border-color: var(--view-color);
  background: var(--view-color-soft);
}

.module-card.disabled {
  opacity: 0.85;
}

.module-card strong,
.module-card span,
.module-card p {
  display: block;
}

.module-card strong {
  color: var(--text-primary);
  font-size: 14px;
}

.module-card span,
.module-card p {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.module-card p {
  margin: 4px 0 0;
}

.create-form {
  display: grid;
  gap: 12px;
}
</style>
