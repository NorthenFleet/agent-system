<template>
  <section v-loading="loading">
    <el-row :gutter="16">
      <el-col :xs="24" :lg="14">
        <el-card shadow="never">
          <template #header><b>财务权限与数据导入</b></template>
          <el-form label-width="90px">
            <el-form-item label="用户 ID"><el-input-number v-model="roleForm.user_id" :min="1" /></el-form-item>
            <el-form-item label="财务角色"><el-select v-model="roleForm.role"><el-option v-for="role in roles" :key="role" :label="role" :value="role" /></el-select></el-form-item>
            <el-form-item label="项目范围"><el-select v-model="roleForm.project_id" clearable><el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" /></el-select></el-form-item>
            <el-form-item><el-button type="primary" @click="grant">授权</el-button></el-form-item>
          </el-form>
          <el-divider />
          <p class="hint">个人模式已关闭审批工作流。报销提交后直接进入待付款，预算保存即生效。</p>
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="10">
        <el-card shadow="never"><template #header><b>历史数据迁移</b></template><p class="hint">导入是显式后台任务；GET 请求不会扫描 Obsidian 或写入数据库。</p><el-button @click="importLegacy(true)">迁移预检</el-button><el-button type="warning" @click="importLegacy(false)">执行 SQLite 导入</el-button></el-card>
      </el-col>
    </el-row>
  </section>
</template>
<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { financeApi, type FinanceProject } from '@/api/finance'
const loading = ref(false), projects = ref<FinanceProject[]>([])
const roles = ['finance_admin','project_manager','applicant','cashier','auditor']
const roleForm = reactive({ user_id: 1, role: 'applicant', project_id: '' })
async function load() { loading.value = true; try { projects.value = await financeApi.projects() } finally { loading.value = false } }
async function grant() { await financeApi.grantRole({ ...roleForm, project_id: roleForm.project_id || null }); ElMessage.success('财务角色已授权') }
async function importLegacy(dry_run: boolean) { if (!dry_run) await ElMessageBox.confirm('将从只读历史 SQLite 导入到当前权威库，确认继续？','执行迁移',{type:'warning'}); const result = await financeApi.createImport({source_type:'legacy_sqlite',dry_run}); ElMessage.success(dry_run ? `预检完成：${JSON.stringify(result.result_payload || {})}` : '迁移任务已完成') }
onMounted(load)
</script>
<style scoped>.hint{color:var(--el-text-color-secondary);line-height:1.6}.el-divider{margin:8px 0 16px}</style>
