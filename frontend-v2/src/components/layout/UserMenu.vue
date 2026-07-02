<template>
  <el-dropdown trigger="click" @command="handleCommand">
    <span class="user-menu">
      <el-avatar :size="30" class="user-avatar">
        {{ authStore.displayName.charAt(0) }}
      </el-avatar>
      <span class="user-name">{{ authStore.displayName }}</span>
      <el-icon class="el-icon--right"><ArrowDown /></el-icon>
    </span>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item disabled>
          <div class="user-info-dropdown">
            <div class="display-name">{{ authStore.displayName }}</div>
            <div class="username">@{{ authStore.user?.username }}</div>
          </div>
        </el-dropdown-item>
        <el-dropdown-item>
          <el-tag size="small" :type="getRoleType(authStore.user?.role)">
            {{ getRoleLabel(authStore.user?.role) }}
          </el-tag>
        </el-dropdown-item>
        <el-dropdown-item divided command="logout">
          <el-icon><SwitchButton /></el-icon>
          退出登录
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup lang="ts">
import { ArrowDown, SwitchButton } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

function getRoleType(role?: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  const map: Record<string, '' | 'success' | 'warning' | 'info' | 'danger'> = {
    admin: 'danger', agent: 'success', viewer: 'info'
  }
  return map[role || ''] || ''
}

function getRoleLabel(role?: string): string {
  const map: Record<string, string> = {
    admin: '管理员', agent: '智能体', viewer: '观察者'
  }
  return map[role || ''] || '未知'
}

function handleCommand(command: string) {
  if (command === 'logout') {
    authStore.logout()
    router.push('/login')
  }
}
</script>

<style scoped>
.user-menu {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  transition: background 0.15s;
}

.user-menu:hover {
  background: rgba(var(--view-rgb), 0.08);
}

.user-avatar {
  background: var(--view-color);
  color: #08111f;
  font-size: 14px;
}

.user-name {
  font-size: 14px;
  color: #c9d1d9;
}

.user-info-dropdown {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.display-name {
  font-weight: 600;
  font-size: 14px;
}

.username {
  font-size: 12px;
  color: #8b949e;
}
</style>
