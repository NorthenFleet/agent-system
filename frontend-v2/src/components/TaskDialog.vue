<template>
  <el-dialog
    v-model="visible"
    :title="isEdit ? '编辑任务' : '创建任务'"
    width="560px"
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
            <el-select v-model="form.assignee" placeholder="选择负责人" clearable style="width: 100%">
              <el-option label="🟦 李奥纳多" value="leonardo" />
              <el-option label="🟥 拉斐尔" value="raphael" />
              <el-option label="🟪 多纳泰罗" value="donatello" />
              <el-option label="🟧 米开朗基罗" value="michelangelo" />
              <el-option label="🔧 千斤顶" value="wheeljack" />
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
    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" :loading="loading" @click="handleSubmit">
        {{ isEdit ? '保存' : '创建' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance } from 'element-plus'
import type { Task, TaskCreate, TaskUpdate } from '@/stores/tasks'
import { useTasksStore } from '@/stores/tasks'

const props = defineProps<{
  modelValue: boolean
  task?: Task | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const tasksStore = useTasksStore()
const formRef = ref<FormInstance>()
const loading = ref(false)

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
</script>
