// Vue 应用入口
import { createApp } from 'vue';
import { initialState, statusMap, teamMap } from './data.js';

console.log('[App] 开始初始化 Vue 应用...');

createApp({
  data() {
    return initialState;
  },
  methods: {
    selectAgent(agent) {
      this.selectedAgent = agent;
      console.log('[App] 选择智能体:', agent.name);
    },
    getStatusText(status) {
      return statusMap[status]?.text || status;
    },
    getStatusType(status) {
      return statusMap[status]?.type || 'info';
    },
    getTeamName(team) {
      return teamMap[team] || team;
    }
  },
  async mounted() {
    console.log('[App] ===== Vue 应用已挂载 =====');
    this.loading = true;
    try {
      const res = await fetch('/api/agents');
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      this.agents = data.agents || [];
      console.log('[App] ✅ 加载成功:', this.agents.length, '个智能体');
      if (this.agents.length > 0) {
        this.selectedAgent = this.agents[0];
        console.log('[App] 默认选择:', this.selectedAgent.name);
      }
    } catch (e) {
      console.error('[App] ❌ 加载失败:', e);
      this.error = e.message;
    } finally {
      this.loading = false;
    }
  }
}).mount('#app');

console.log('[App] ✅ Vue 脚本已加载');
