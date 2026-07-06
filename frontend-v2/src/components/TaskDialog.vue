<template>
  <el-dialog
    v-model="visible"
    :title="isEdit ? '编辑任务' : '创建任务'"
    width="600px"
    class="task-dialog"
    @close="handleClose"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="80px"
      label-position="right"
    >
      <el-form-item label="标题" prop="title">
        <el-input v-model="form.title" placeholder="请输入任务标题" />
      </el-form-item>
      <el-form-item label="描述">
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="3"
          placeholder="任务描述（可选）"
        />
      </el-form-item>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="类型">
            <el-select v-model="form.type" placeholder="选择类型" style="width: 100%">
              <el-option label="全栈" value="fullstack" />
              <el-option label="后端" value="backend" />
              <el-option label="前端" value="frontend" />
              <el-option label="测试" value="testing" />
              <el-option label="其他" value="general" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="优先级">
            <el-select v-model="form.priority" placeholder="选择优先级" style="width: 100%">
              <el-option label="低" value="low" />
              <el-option label="中" value="medium" />
              <el-option label="高" value="high" />
              <el-option label="紧急" value="critical" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="状态">
            <el-select v-model="form.status" placeholder="选择状态" style="width: 100%">
              <el-option label="待处理" value="pending" />
              <el-option label="已分配" value="assigned" />
              <el-option label="进行中" value="in_progress" />
              <el-option label="审查中" value="review" />
              <el-option label="测试中" value="testing" />
              <el-option label="已完成" value="done" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="负责人">
            <el-select
              v-model="form.assignee"
              placeholder="选择负责人"
              clearable
              style="width: 100%"
              @visible-change="onAssigneeDropdownVisible"
            >
              <el-option-group
                v-for="group in assigneeGroups"
                :key="group.label"
                :label="group.label"
              >
                <el-option
                  v-for="opt in group.options"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                >
                  <span class="assignee-option">
                    <span v-if="opt.isRecommended" class="assignee-star">★</span>
                    <span>{{ opt.label }}</span>
                    <span v-if="opt.score != null" class="assignee-score">{{ Math.round(opt.score * 100) }}%</span>
                  </span>
                </el-option>
              </el-option-group>
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="开始日期">
            <el-date-picker
              v-model="form.start_date"
              type="date"
              placeholder="选择日期"
              style="width: 100%"
              value-format="YYYY-MM-DD"
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="截止日期">
            <el-date-picker
              v-model="form.due_date"
              type="date"
              placeholder="选择日期"
              style="width: 100%"
              value-format="YYYY-MM-DD"
            />
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>

    <!-- 智能推荐区域 -->
    <TaskRecommendation
      v-if="!isEdit"
      ref="recommendRef"
      :task-type="form.type"
      :priority="form.priority"
      :tags="[]"
      @select="onRecommendSelect"
    />

    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" :loading="loading" @click="handleSubmit">
        {{ isEdit ? '保存' : '创建' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance } from 'element-plus'
import type { Task, TaskCreate, TaskUpdate } from '@/stores/tasks'
import { useTasksStore } from '@/stores/tasks'
import TaskRecommendation from './task/TaskRecommendation.vue'
import { recommendAgent, type RecommendAgent } from '@/api/recommendation'

const props = defineProps<{
  modelValue: boolean
  task?: Task | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const tasksStore = useTasksStore()
const formRef = ref<FormInstance>()
const recommendRef = ref<InstanceType<typeof TaskRecommendation>>()
void recommendRef
const loading = ref(false)
const recommendAgents = ref<RecommendAgent[]>([])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v)
})

const isEdit = computed(() => !!props.task)

const form = reactive({
  title: '',
  description: '',
  type: 'general',
  status: 'pending',
  priority: 'medium',
  assignee: '',
  start_date: '',
  due_date: ''
})

const rules = {
  title: [{ required: true, message: '请输入任务标题', trigger: 'blur' }]
}

watch(() => props.task, (task) => {
  if (task) {
    form.title = task.title
    form.description = task.description || ''
    form.type = task.type
    form.status = task.status
    form.priority = task.priority
    form.assignee = task.assignee || ''
    form.start_date = task.start_date ? task.start_date.split('T')[0] : ''
    form.due_date = task.due_date ? task.due_date.split('T')[0] : ''
  } else {
    resetForm()
  }
}, { immediate: true })

// ===== 负责人选项（含推荐） =====
interface AssigneeOption {
  value: string
  label: string
  score?: number
  isRecommended: boolean
}

const baseAgents: Array<{ value: string; label: string }> = [
  { value: 'leonardo', label: '🟦 李奥纳多' },
  { value: 'raphael', label: '🟥 拉斐尔' },
  { value: 'donatello', label: '🟪 多纳泰罗' },
  { value: 'michelangelo', label: '🟧 米开朗基罗' },
  { value: 'wheeljack', label: '🔧 千斤顶' }
]

const assigneeGroups = computed<
  Array<{ label: string; options: AssigneeOption[] }>
>(() => {
  const recMap = new Map<string, number>()
  recommendAgents.value.forEach(a => recMap.set(a.agent_id, a.score))

  const recommended: AssigneeOption[] = []
  const others: AssigneeOption[] = []

  for (const base of baseAgents) {
    const score = recMap.get(base.value)
    if (score != null) {
      recommended.push({
        value: base.value,
        label: base.label,
        score,
        isRecommended: true
      })
    } else {
      others.push({
        value: base.value,
        label: base.label,
        isRecommended: false
      })
    }
  }

  recommended.sort((a, b) => (b.score ?? 0) - (a.score ?? 0))

  const groups: Array<{ label: string; options: AssigneeOption[] }> = []
  if (recommended.length) {
    groups.push({ label: '⭐ 推荐', options: recommended })
  }
  if (others.length) {
    groups.push({ label: '全部', options: others })
  }
  return groups
})

function onRecommendSelect(agentId: string) {
  form.assignee = agentId
  ElMessage.success(`已选择推荐 Agent: ${agentId}`)
}

async function onAssigneeDropdownVisible(visible: boolean) {
  if (!visible || isEdit.value) return
  if (recommendAgents.value.length > 0) return
  try {
    const res = await recommendAgent({
      task_type: form.type,
      priority: form.priority,
      tags: []
    })
    recommendAgents.value = res.agents || []
  } catch {
    // 静默失败
  }
}

function resetForm() {
  form.title = ''
  form.description = ''
  form.type = 'general'
  form.status = 'pending'
  form.priority = 'medium'
  form.assignee = ''
  form.start_date = ''
  form.due_date = ''
}

function handleClose() {
  visible.value = false
  formRef.value?.resetFields()
  resetForm()
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    if (isEdit.value && props.task) {
      const updateData: TaskUpdate = {
        title: form.title,
        description: form.description,
        type: form.type,
        status: form.status,
        priority: form.priority,
        assignee: form.assignee || undefined,
        start_date: form.start_date || undefined,
        due_date: form.due_date || undefined
      }
      await tasksStore.updateTaskAction(props.task.task_id, updateData)
      ElMessage.success('任务已更新')
    } else {
      const createData: TaskCreate = {
        title: form.title,
        description: form.description,
        type: form.type,
        priority: form.priority,
        assignee: form.assignee || undefined,
        start_date: form.start_date || undefined,
        due_date: form.due_date || undefined
      }
      await tasksStore.createTaskAction(createData)
      ElMessage.success('任务已创建')
    }
    handleClose()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  if (!isEdit.value) {
    recommendAgents.value = []
  }
})
</script>

<style scoped>
.assignee-option {
  display: flex;
  align-items: center;
  gap: 6px;
}

.assignee-star {
  color: #eab308;
  font-size: 14px;
  filter: drop-shadow(0 1px 2px rgba(234, 179, 8, 0.4));
}

.assignee-score {
  margin-left: auto;
  font-size: 11px;
  color: #909399;
  font-weight: 600;
}
</style>
