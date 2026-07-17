import { createApp } from 'vue'
import { createPinia } from 'pinia'
import {
  ElAlert,
  ElAvatar,
  ElButton,
  ElCard,
  ElCheckbox,
  ElCol,
  ElCollapseTransition,
  ElConfigProvider,
  ElDatePicker,
  ElDescriptions,
  ElDescriptionsItem,
  ElDialog,
  ElDivider,
  ElDrawer,
  ElDropdown,
  ElDropdownItem,
  ElDropdownMenu,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElIcon,
  ElInput,
  ElLink,
  ElLoading,
  ElMenu,
  ElMenuItem,
  ElOption,
  ElPagination,
  ElPopconfirm,
  ElProgress,
  ElRow,
  ElSegmented,
  ElSelect,
  ElSkeleton,
  ElStep,
  ElSteps,
  ElSwitch,
  ElTabPane,
  ElTable,
  ElTableColumn,
  ElTabs,
  ElTag,
  ElTimeline,
  ElTimelineItem,
  ElTooltip
} from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router/index.ts'
import './styles/main.css'

const app = createApp(App)

app.use(createPinia())
app.use(router)

const elementComponents = [
  ElAlert,
  ElAvatar,
  ElButton,
  ElCard,
  ElCheckbox,
  ElCol,
  ElCollapseTransition,
  ElConfigProvider,
  ElDatePicker,
  ElDescriptions,
  ElDescriptionsItem,
  ElDialog,
  ElDivider,
  ElDrawer,
  ElDropdown,
  ElDropdownItem,
  ElDropdownMenu,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElIcon,
  ElInput,
  ElLink,
  ElLoading,
  ElMenu,
  ElMenuItem,
  ElOption,
  ElPagination,
  ElPopconfirm,
  ElProgress,
  ElRow,
  ElSegmented,
  ElSelect,
  ElSkeleton,
  ElStep,
  ElSteps,
  ElSwitch,
  ElTabPane,
  ElTable,
  ElTableColumn,
  ElTabs,
  ElTag,
  ElTimeline,
  ElTimelineItem,
  ElTooltip
]

for (const component of elementComponents) {
  app.use(component)
}

app.mount('#app')

// PWA: 注册 Service Worker
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(err => {
      console.log('[SW] Service Worker 注册失败:', err)
    })
  })
}
