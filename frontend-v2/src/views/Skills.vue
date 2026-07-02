<template>
  <div class="skills-page">
    <el-card class="panel" shadow="hover">
      <template #header>
        <div class="panel-header">
          <span>技能管理</span>
          <el-input v-model="keyword" size="small" placeholder="搜索技能" clearable style="width: 260px" />
        </div>
      </template>
      <el-table :data="filteredSkills" size="small" height="640">
        <el-table-column prop="name" label="技能" min-width="220" show-overflow-tooltip />
        <el-table-column prop="category" label="分类" width="120" />
        <el-table-column prop="source" label="来源" width="160" />
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" size="small">{{ statusLabel(row.status || (row.enabled ? 'enabled' : 'disabled')) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="触发词" min-width="220">
          <template #default="{ row }">
            <el-tag v-for="trigger in row.triggers?.slice(0, 4) || []" :key="trigger" size="small" class="tag-gap">{{ trigger }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="说明" min-width="320" show-overflow-tooltip />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getSkills, type SkillItem } from '@/api/openclaw'

const skills = ref<SkillItem[]>([])
const keyword = ref('')

const filteredSkills = computed(() => {
  const key = keyword.value.trim().toLowerCase()
  if (!key) return skills.value
  return skills.value.filter(skill => `${skill.name} ${skill.category} ${skill.description}`.toLowerCase().includes(key))
})

async function loadSkills() {
  try {
    const data = await getSkills()
    skills.value = data.skills
  } catch {
    ElMessage.error('技能数据加载失败')
  }
}

onMounted(loadSkills)

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    enabled: '已启用',
    disabled: '已停用',
    active: '启用',
    inactive: '停用',
    ready: '就绪',
    draft: '草稿'
  }
  return map[status] || status
}
</script>

<style scoped>
.panel {
  border-radius: 8px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.tag-gap {
  margin-right: 4px;
  margin-bottom: 4px;
}
</style>
