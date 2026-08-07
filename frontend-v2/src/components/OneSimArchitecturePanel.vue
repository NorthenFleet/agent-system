<template>
  <section class="architecture-workbench">
    <header class="architecture-head">
      <div>
        <span class="eyebrow">ONE-SIM ARCHITECTURE</span>
        <h3>系统逻辑与代码组织</h3>
        <p>以事实所有权和运行闭环为主干，代码依赖图用于下钻验证。</p>
      </div>
      <div class="head-actions">
        <el-tooltip content="重新载入代码探索图">
          <el-button :icon="Refresh" circle aria-label="重新载入代码探索图" @click="graphKey += 1" />
        </el-tooltip>
        <el-tooltip content="在新窗口打开代码探索图">
          <el-button :icon="FullScreen" circle aria-label="在新窗口打开代码探索图" @click="openGraph" />
        </el-tooltip>
      </div>
    </header>

    <nav class="view-switch" aria-label="架构视图">
      <button
        v-for="item in views"
        :key="item.id"
        type="button"
        :class="{ active: activeView === item.id }"
        @click="activeView = item.id"
      >
        <component :is="item.icon" />
        <span>{{ item.label }}</span>
      </button>
    </nav>

    <div v-if="activeView !== 'explorer'" class="architecture-layout">
      <main class="architecture-canvas">
        <template v-if="activeView === 'logical'">
          <div class="canvas-title">
            <div><strong>四平面逻辑架构</strong><small>由上到下：目标编排、决策、执行、数据与契约</small></div>
            <el-tag type="success" effect="plain">目标架构</el-tag>
          </div>
          <div class="plane-stack">
            <section v-for="plane in logicalPlanes" :key="plane.id" :class="['plane', `plane-${plane.id}`]">
              <div class="plane-label">
                <span>{{ plane.kicker }}</span>
                <strong>{{ plane.title }}</strong>
                <small>{{ plane.truth }}</small>
              </div>
              <div class="plane-nodes">
                <button
                  v-for="node in plane.nodes"
                  :key="node.id"
                  type="button"
                  :class="['architecture-node', { selected: selectedNode.id === node.id }]"
                  @click="selectNode(node)"
                >
                  <component :is="node.icon" />
                  <span><strong>{{ node.title }}</strong><small>{{ node.subtitle }}</small></span>
                  <i :class="['health-dot', node.health || 'stable']" />
                </button>
              </div>
            </section>
            <div class="flow-label flow-goal">Goal / Job / Event</div>
            <div class="flow-label flow-command">Plan / Command</div>
            <div class="flow-label flow-feedback">Observation / Result</div>
          </div>
          <div class="ownership-legend">
            <span><i class="legend-company" />公司编排</span>
            <span><i class="legend-decision" />决策平面</span>
            <span><i class="legend-runtime" />执行平面</span>
            <span><i class="legend-data" />数据与契约</span>
            <span class="rule">跨边界只通过版本化 API、Job、Event 与 Schema</span>
          </div>
        </template>

        <template v-else-if="activeView === 'modules'">
          <div class="canvas-title">
            <div><strong>模块组织架构</strong><small>从仓库目录映射到职责、接口与验证入口</small></div>
            <el-tag effect="plain">7 个主域</el-tag>
          </div>
          <div class="module-root">
            <div class="root-node"><FolderOpened /><span><strong>One-Sim</strong><small>智能公司生产与仿真底座</small></span></div>
            <div class="module-grid">
              <button
                v-for="module in modules"
                :key="module.id"
                type="button"
                :class="['module-card', `tone-${module.tone}`, { selected: selectedNode.id === module.id }]"
                @click="selectNode(module)"
              >
                <div class="module-title"><component :is="module.icon" /><strong>{{ module.title }}</strong></div>
                <code>{{ module.path }}</code>
                <p>{{ module.subtitle }}</p>
                <div class="module-children"><span v-for="child in module.children" :key="child">{{ child }}</span></div>
              </button>
            </div>
          </div>
        </template>

        <template v-else>
          <div class="canvas-title">
            <div><strong>公司到仿真的完整运行链路</strong><small>每一步都标出输入、输出和事实所有者</small></div>
            <el-tag type="warning" effect="plain">验收闭环</el-tag>
          </div>
          <ol class="runtime-flow">
            <li v-for="(step, index) in runtimeSteps" :key="step.id">
              <button
                type="button"
                :class="['runtime-step', `tone-${step.tone}`, { selected: selectedNode.id === step.id }]"
                @click="selectNode(step)"
              >
                <span class="step-index">{{ String(index + 1).padStart(2, '0') }}</span>
                <component :is="step.icon" />
                <span class="step-copy"><strong>{{ step.title }}</strong><small>{{ step.subtitle }}</small></span>
                <el-tag size="small" effect="plain">{{ step.owner }}</el-tag>
              </button>
              <div v-if="index < runtimeSteps.length - 1" class="step-connector"><ArrowDown /></div>
            </li>
          </ol>
        </template>
      </main>

      <aside class="node-inspector">
        <div class="inspector-heading">
          <span>节点详情</span>
          <el-tag size="small" :type="ownerTagType(selectedNode.tone)">{{ selectedNode.owner }}</el-tag>
        </div>
        <div class="inspector-title"><component :is="selectedNode.icon" /><div><strong>{{ selectedNode.title }}</strong><small>{{ selectedNode.subtitle }}</small></div></div>
        <section><span>核心职责</span><p>{{ selectedNode.responsibility }}</p></section>
        <section><span>事实所有权</span><p>{{ selectedNode.truth }}</p></section>
        <section v-if="selectedNode.path"><span>代码入口</span><code>{{ selectedNode.path }}</code></section>
        <section><span>输入</span><div class="tag-list"><el-tag v-for="item in selectedNode.inputs" :key="item" size="small" effect="plain">{{ item }}</el-tag></div></section>
        <section><span>输出</span><div class="tag-list"><el-tag v-for="item in selectedNode.outputs" :key="item" size="small" effect="plain">{{ item }}</el-tag></div></section>
        <section v-if="selectedNode.contracts?.length"><span>关键契约</span><ul><li v-for="item in selectedNode.contracts" :key="item"><code>{{ item }}</code></li></ul></section>
      </aside>
    </div>

    <section v-else class="explorer-view">
      <div class="explorer-notice">
        <div><Search /><span><strong>代码探索视图</strong><small>12,741 个细粒度节点用于搜索、调用关系验证和局部下钻，不代表系统逻辑架构。</small></span></div>
        <div class="explorer-metrics"><span>806 社区</span><span>1,211 主干关系</span><span>ca9cba45</span></div>
      </div>
      <iframe :key="graphKey" src="/assets/graphs/one-sim-architecture.html" title="One-Sim 代码探索图" sandbox="allow-scripts" />
    </section>
  </section>
</template>

<script setup lang="ts">
import { markRaw, ref, type Component } from 'vue'
import {
  Aim, ArrowDown, Box, Connection, Cpu, DataAnalysis, Files, FolderOpened,
  FullScreen, Grid, Monitor, Operation, Refresh, Search, Share, Tickets
} from '@element-plus/icons-vue'

type Tone = 'company' | 'decision' | 'runtime' | 'data' | 'interface'
type NodeInfo = {
  id: string
  title: string
  subtitle: string
  owner: string
  tone: Tone
  icon: Component
  responsibility: string
  truth: string
  path?: string
  inputs: string[]
  outputs: string[]
  contracts?: string[]
  health?: 'stable' | 'active' | 'warning'
  children?: string[]
}

const icon = (value: Component) => markRaw(value)
const node = (value: NodeInfo) => value
const activeView = ref('logical')
const graphKey = ref(0)
const views = [
  { id: 'logical', label: '逻辑架构', icon: icon(Grid) },
  { id: 'modules', label: '模块组织', icon: icon(FolderOpened) },
  { id: 'runtime', label: '运行链路', icon: icon(Operation) },
  { id: 'explorer', label: '代码探索', icon: icon(Search) }
]

const openClaw = node({ id: 'openclaw', title: 'OpenClaw 智能公司', subtitle: '目标、角色、项目与验收', owner: 'OpenClaw', tone: 'company', icon: icon(Share), responsibility: '把真实项目目标拆成可追踪的 Job，组织智能体协作，并对 One-Sim 产物进行验收或发起重规划。', truth: '公司目标、项目关系、人员/智能体组织与验收状态。', path: '192.168.31.41:3021', inputs: ['用户目标', '约束', '验收标准'], outputs: ['Goal / Job', '审批', '重规划请求'], contracts: ['job_id', 'goal/job/event API'], health: 'active' })
const integration = node({ id: 'integration', title: '集成边界', subtitle: '版本化 API / Job / Event', owner: '共享接口', tone: 'interface', icon: icon(Connection), responsibility: '隔离公司编排与产品内部运行时，提供幂等、可审计、可演进的系统接缝。', truth: '只拥有传输状态与关联标识，不拥有领域运行状态。', path: 'integration/ + data_lake/structure/', inputs: ['Goal', 'Job', 'Event'], outputs: ['标准请求', 'Artifact / Result'], contracts: ['goal/job', 'observation/event', 'artifact/result'], health: 'stable' })
const planning = node({ id: 'planning', title: 'AI Planning', subtitle: '规划、分解、分配、重规划', owner: 'ai-planning', tone: 'decision', icon: icon(Aim), responsibility: '把公司意图和可见态势转成版本化计划、战斗任务与标准指令。', truth: '计划、任务分解、分配、策略决策及其解释。', path: 'ai-planning/ai_planning/planning/', inputs: ['Mission', 'Observation', '约束'], outputs: ['Plan', 'CombatTask', 'CommandSet'], contracts: ['mission_plan.yaml', 'combat_task.yaml', 'task_command_mapping.yaml'], health: 'active' })
const agents = node({ id: 'agents', title: 'Agent Runtime', subtitle: '决策、训练、策略运行', owner: 'ai-planning', tone: 'decision', icon: icon(Cpu), responsibility: '消费按 side 裁剪的观察，运行策略并输出标准 command 与 decision trace。', truth: '策略内部状态、训练 episode 和决策轨迹。', path: 'ai-planning/ai_planning/agents/', inputs: ['AgentObservation', 'Policy'], outputs: ['Commands', 'DecisionTrace'], contracts: ['agent_observation_contract.yaml', 'agent_runtime_contract.yaml'], health: 'stable' })
const api5130 = node({ id: 'api5130', title: 'Planning API', subtitle: '5130 规划管理与态势会话', owner: 'ai-planning', tone: 'decision', icon: icon(Monitor), responsibility: '承载规划会话、训练入口、任务与 command-set 输出，是决策平面的外部服务入口。', truth: '会话级规划状态；不持有 wargame 全局权威态。', path: 'ai-planning/ai_planning/runner/', inputs: ['Job', 'Scenario', 'Observation'], outputs: ['PlanVersion', 'CommandSet'], contracts: ['planning situation API', 'action_commands.yaml'], health: 'active' })
const engine = node({ id: 'engine', title: 'Wargame Engine', subtitle: 'ECS、命令执行与裁决', owner: 'wargame', tone: 'runtime', icon: icon(Box), responsibility: '加载想定和规则，推进唯一权威世界态，执行命令并生成事件、观察与回放。', truth: '全局世界态、实体状态、回合/时间、执行进度和裁决结果。', path: 'envs/wargame/src/engine/', inputs: ['CommandIntent', 'Scenario', 'Rules'], outputs: ['GameState', 'Event', 'Replay'], contracts: ['command_intent.json', 'event_schema.yaml'], health: 'active' })
const observation = node({ id: 'observation', title: 'Observation Gateway', subtitle: '按 side 裁剪可见态势', owner: 'wargame', tone: 'runtime', icon: icon(DataAnalysis), responsibility: '从全量世界态派生权限安全的观察，防止智能体读取隐藏单位或完整 game_state。', truth: '观察是投影，源事实仍属于 Wargame Engine。', path: 'envs/wargame/src/engine/observation/', inputs: ['GameState', 'Side', 'Visibility'], outputs: ['PlayerObservation', 'AgentObservation'], contracts: ['player_observation.yaml', 'agent_observation_contract.yaml'], health: 'stable' })
const ui = node({ id: 'ui', title: '仿真与管理界面', subtitle: '5120 手工推演 / 5100 管理', owner: 'wargame UI', tone: 'runtime', icon: icon(Monitor), responsibility: '显示运行时只读投影、提交标准命令并管理想定规则数据，不成为权威状态源。', truth: '仅拥有界面交互状态。', path: 'envs/wargame/frontend/ + web-admin/', inputs: ['UI Projection', 'Catalog'], outputs: ['CommandIntent', '管理请求'], contracts: ['frontend_world_state.yaml'], health: 'stable' })
const lake = node({ id: 'lake', title: 'Data Lake', subtitle: '契约、想定、单位、规则与资产', owner: 'data_lake', tone: 'data', icon: icon(Files), responsibility: '保存跨模块共享语义和可审计领域事实，向规划与仿真提供统一发现入口。', truth: 'Schema、想定、单位定义、规则数据和静态资产；不执行实时计算。', path: 'data_lake/', inputs: ['版本化数据', '规则配置', 'Schema'], outputs: ['Validated Bundle', 'Contract Registry'], contracts: ['schema_manifest.yaml', 'rule_manifest.yaml', 'coordinate_schema.yaml'], health: 'stable' })

const logicalPlanes = [
  { id: 'company', kicker: 'COMPANY PLANE', title: '公司编排平面', truth: '谁提出目标、组织资源并验收', nodes: [openClaw, integration] },
  { id: 'decision', kicker: 'DECISION PLANE', title: '决策平面', truth: '谁拥有计划与决策', nodes: [api5130, planning, agents] },
  { id: 'runtime', kicker: 'EXECUTION PLANE', title: '权威执行平面', truth: '谁推进世界态并裁决', nodes: [engine, observation, ui] },
  { id: 'data', kicker: 'DATA & CONTRACT PLANE', title: '数据与契约平面', truth: '谁定义跨模块共享语义', nodes: [lake] }
]

const modules: NodeInfo[] = [
  { ...planning, id: 'module-planning', title: 'AI Planning', subtitle: '任务规划、Agent、训练与服务入口', path: 'ai-planning/', children: ['planning', 'agents', 'training', 'runner'] },
  { ...engine, id: 'module-wargame', title: 'Wargame', subtitle: '唯一权威仿真运行时与服务', path: 'envs/wargame/', children: ['src/engine', 'services', 'frontend', 'tests'] },
  { ...lake, id: 'module-lake', title: 'Data Lake', subtitle: '共享契约和领域事实源', path: 'data_lake/', children: ['structure', 'scenarios', 'units', 'rules/v4'] },
  { ...integration, id: 'module-integration', title: 'Integration', subtitle: 'OpenClaw 与 One-Sim 的稳定接缝', path: 'integration/', children: ['jobs', 'events', 'artifacts', 'adapters'] },
  { ...ui, id: 'module-frontends', title: 'Frontends', subtitle: '规划、仿真和管理投影', path: '*/frontend/ + runner/static/', children: ['5130', '5120', '5100', 'projections'] },
  { id: 'module-tests', title: 'Verification', subtitle: '契约、冒烟与跨进程闭环', owner: 'tests', tone: 'interface', icon: icon(Tickets), responsibility: '验证跨模块契约和 observation 到 command 再到 ECS 的真实闭环。', truth: '测试结果与兼容性证据。', path: 'envs/wargame/tests/ + ai-planning/tests/', inputs: ['Schema', 'Runtime'], outputs: ['Contract Result', 'E2E Evidence'], contracts: ['smoke', 'contract', 'process-e2e'], children: ['unit', 'contract', 'process-e2e', 'baseline'] },
  { id: 'module-tools', title: 'Tools & Dev Loop', subtitle: '开发地图、验证脚本与自动化', owner: 'tooling', tone: 'interface', icon: icon(Operation), responsibility: '为开发者和 Codex 提供一致的入口、验证命令和架构导航。', truth: '开发辅助状态，不拥有业务事实。', path: 'scripts/ + tools/ + dev-loop/', inputs: ['Source', 'Manifest'], outputs: ['Validation', 'Report'], contracts: ['CODEX_DEVELOPMENT_MAP.md'], children: ['scripts', 'tools', 'dev-loop', 'docs'] }
]

const runtimeSteps: NodeInfo[] = [
  { ...openClaw, id: 'run-goal', title: '创建公司 Job', subtitle: '目标、约束、场景和验收标准', outputs: ['job_id', 'GoalSpec'] },
  { ...integration, id: 'run-contract', title: '校验集成契约', subtitle: '幂等键、版本、权限与关联标识', inputs: ['GoalSpec'], outputs: ['Accepted Job'] },
  { ...api5130, id: 'run-session', title: '建立规划态势会话', subtitle: '绑定想定、观察和引擎 backend', inputs: ['Accepted Job', 'Scenario'], outputs: ['PlanningSession'] },
  { ...planning, id: 'run-plan', title: '分解、分配与形成计划', subtitle: 'Mission → Plan → CombatTask → CommandSet', inputs: ['Mission', 'Observation'], outputs: ['PlanVersion', 'CommandSet'] },
  { ...engine, id: 'run-execute', title: '执行标准命令', subtitle: 'CommandGateway → ECS → RuleRuntime', inputs: ['CommandSet', 'Rules'], outputs: ['GameState', 'Events'] },
  { ...observation, id: 'run-observe', title: '生成安全观察', subtitle: '按 side 和可见性裁剪全局状态', inputs: ['GameState'], outputs: ['AgentObservation'] },
  { ...agents, id: 'run-replan', title: '评估与重规划', subtitle: '事件、奖励和新观察驱动下一轮决策', inputs: ['Observation', 'Events', 'Reward'], outputs: ['DecisionTrace', 'Replan'] },
  { ...openClaw, id: 'run-accept', title: '回传产物并验收', subtitle: '回放、指标、报告和可追溯引用', inputs: ['Artifact', 'Result'], outputs: ['Accept', 'Revise', 'New Job'] }
]

const selectedNode = ref<NodeInfo>(openClaw)
function selectNode(value: NodeInfo) { selectedNode.value = value }
function openGraph() { window.open('/assets/graphs/one-sim-architecture.html', '_blank', 'noopener,noreferrer') }
function ownerTagType(tone: Tone) { return tone === 'runtime' ? 'warning' : tone === 'data' ? 'success' : tone === 'decision' ? 'primary' : 'info' }
</script>

<style scoped>
.architecture-workbench { display: grid; gap: 12px; color: var(--text); }
.architecture-head, .canvas-title, .inspector-heading, .inspector-title, .explorer-notice, .explorer-notice > div { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.architecture-head h3, .architecture-head p { margin: 3px 0 0; }
.architecture-head p { color: var(--text-secondary); font-size: 12px; }
.eyebrow { color: #62a8ff; font-size: 10px; font-weight: 700; }
.head-actions { display: flex; gap: 8px; }
.view-switch { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border: 1px solid var(--view-color-border); background: var(--view-color-faint); }
.view-switch button { display: flex; align-items: center; justify-content: center; gap: 7px; min-height: 38px; border: 0; border-right: 1px solid var(--view-color-border); color: var(--text-secondary); background: transparent; cursor: pointer; }
.view-switch button:last-child { border-right: 0; }
.view-switch button.active { color: #fff; background: #286db4; }
.view-switch svg { width: 15px; }
.architecture-layout { display: grid; grid-template-columns: minmax(0, 1fr) 270px; min-height: 590px; border: 1px solid var(--view-color-border); background: #111923; }
.architecture-canvas { min-width: 0; padding: 14px; border-right: 1px solid var(--view-color-border); }
.canvas-title { margin-bottom: 12px; }
.canvas-title > div { display: grid; gap: 2px; }
.canvas-title small { color: #8291a6; }
.plane-stack { position: relative; display: grid; gap: 11px; padding-right: 112px; }
.plane { display: grid; grid-template-columns: 160px minmax(0, 1fr); min-height: 104px; border: 1px solid #2c3c50; background: #172230; }
.plane-label { display: flex; flex-direction: column; justify-content: center; gap: 4px; padding: 12px; border-right: 1px solid #2c3c50; }
.plane-label span { font-size: 9px; font-weight: 700; color: #8496aa; }
.plane-label small { color: #8496aa; line-height: 1.45; }
.plane-nodes { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); align-items: center; gap: 8px; padding: 10px; }
.plane-company { border-left: 3px solid #5c8cff; }
.plane-decision { border-left: 3px solid #21b8d4; }
.plane-runtime { border-left: 3px solid #ff9b54; }
.plane-data { border-left: 3px solid #54c77a; }
.architecture-node { position: relative; display: flex; align-items: center; gap: 9px; min-width: 0; min-height: 64px; padding: 9px; border: 1px solid #34475e; border-radius: 4px; color: #dbe6f3; text-align: left; background: #1c2a39; cursor: pointer; }
.architecture-node:hover, .architecture-node.selected, .module-card:hover, .module-card.selected, .runtime-step:hover, .runtime-step.selected { border-color: #62a8ff; background: #203a55; }
.architecture-node > svg { flex: 0 0 auto; width: 19px; color: #7db9ff; }
.architecture-node > span, .inspector-title > div { display: grid; gap: 4px; min-width: 0; }
.architecture-node small { overflow: hidden; color: #8999ac; text-overflow: ellipsis; white-space: nowrap; }
.health-dot { position: absolute; top: 7px; right: 7px; width: 6px; height: 6px; border-radius: 50%; background: #7f8a98; }
.health-dot.active { background: #4cd47c; box-shadow: 0 0 0 3px rgb(76 212 124 / 12%); }
.health-dot.warning { background: #f7b955; }
.flow-label { position: absolute; right: 0; width: 96px; padding: 6px; border: 1px solid #38516b; color: #9bb6d2; font-size: 9px; text-align: center; background: #14202d; }
.flow-label::before { position: absolute; right: 100%; top: 50%; width: 17px; border-top: 1px dashed #4e6f91; content: ''; }
.flow-goal { top: 79px; }
.flow-command { top: 201px; }
.flow-feedback { top: 323px; }
.ownership-legend { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 12px; color: #8c9bae; font-size: 10px; }
.ownership-legend span { display: flex; align-items: center; gap: 5px; }
.ownership-legend i { width: 8px; height: 8px; }
.legend-company { background: #5c8cff; } .legend-decision { background: #21b8d4; } .legend-runtime { background: #ff9b54; } .legend-data { background: #54c77a; }
.ownership-legend .rule { margin-left: auto; color: #b7c8da; }
.node-inspector { display: flex; flex-direction: column; gap: 14px; min-width: 0; padding: 14px; background: #151f2b; }
.inspector-heading { padding-bottom: 10px; border-bottom: 1px solid #2b3b4d; font-weight: 700; }
.inspector-title { justify-content: flex-start; }
.inspector-title > svg { width: 28px; color: #72b2ff; }
.inspector-title small { color: #8191a5; }
.node-inspector section { display: grid; gap: 6px; }
.node-inspector section > span { color: #8292a6; font-size: 10px; font-weight: 700; }
.node-inspector p { margin: 0; color: #c3cedb; font-size: 11px; line-height: 1.55; }
.node-inspector code { overflow-wrap: anywhere; color: #8bc4ff; font-size: 10px; }
.node-inspector ul { display: grid; gap: 5px; margin: 0; padding-left: 16px; }
.tag-list { display: flex; flex-wrap: wrap; gap: 5px; }
.module-root { display: grid; gap: 14px; }
.root-node { display: flex; align-items: center; gap: 10px; width: fit-content; padding: 10px 16px; border: 1px solid #4a78a8; background: #1b3045; }
.root-node svg { width: 24px; color: #70b4ff; }
.root-node span { display: grid; gap: 2px; }
.root-node small { color: #8699ae; }
.module-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; padding-left: 26px; border-left: 1px solid #35506d; }
.module-card { display: grid; gap: 7px; min-width: 0; padding: 12px; border: 1px solid #30435a; border-radius: 4px; color: #dce7f2; text-align: left; background: #182432; cursor: pointer; }
.module-title { display: flex; align-items: center; gap: 8px; }
.module-title svg { width: 18px; color: #77b8ff; }
.module-card code { color: #74aade; font-size: 10px; }
.module-card p { margin: 0; color: #92a2b5; font-size: 11px; }
.module-children { display: flex; flex-wrap: wrap; gap: 5px; }
.module-children span { padding: 3px 6px; border: 1px solid #344a62; color: #aab8c8; font-size: 9px; background: #111b26; }
.runtime-flow { display: grid; gap: 0; max-width: 760px; margin: 0 auto; padding: 0; list-style: none; }
.runtime-step { display: grid; grid-template-columns: 34px 24px minmax(0, 1fr) auto; align-items: center; gap: 10px; width: 100%; min-height: 62px; padding: 9px 12px; border: 1px solid #33475d; border-radius: 4px; color: #dbe6f2; text-align: left; background: #192634; cursor: pointer; }
.runtime-step > svg { width: 19px; color: #73b8ff; }
.step-index { color: #68829d; font: 700 11px monospace; }
.step-copy { display: grid; gap: 3px; }
.step-copy small { color: #8c9db0; }
.step-connector { display: flex; justify-content: center; height: 22px; color: #527ba4; }
.step-connector svg { width: 14px; }
.explorer-view { display: grid; gap: 10px; }
.explorer-notice { padding: 10px 12px; border: 1px solid #31455c; background: #162331; }
.explorer-notice > div:first-child { justify-content: flex-start; }
.explorer-notice svg { width: 20px; color: #69adf7; }
.explorer-notice span { display: grid; gap: 2px; }
.explorer-notice small { color: #8e9eb0; }
.explorer-metrics { display: flex !important; gap: 6px !important; }
.explorer-metrics span { display: block; padding: 4px 7px; border: 1px solid #36506b; color: #a8bad0; font-size: 9px; }
.explorer-view iframe { display: block; width: 100%; height: min(680px, 68vh); min-height: 520px; border: 1px solid var(--view-color-border); background: #0f0f1a; }
@media (max-width: 1100px) { .architecture-layout { grid-template-columns: 1fr; } .architecture-canvas { border-right: 0; border-bottom: 1px solid var(--view-color-border); } .node-inspector { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); } .inspector-heading, .inspector-title { grid-column: 1 / -1; } }
@media (max-width: 760px) { .architecture-head { align-items: flex-start; } .view-switch { grid-template-columns: repeat(2, minmax(0, 1fr)); } .view-switch button:nth-child(2) { border-right: 0; } .plane-stack { padding-right: 0; } .plane { grid-template-columns: 1fr; } .plane-label { border-right: 0; border-bottom: 1px solid #2c3c50; } .plane-nodes, .module-grid { grid-template-columns: 1fr; } .flow-label { display: none; } .node-inspector { grid-template-columns: 1fr; } .runtime-step { grid-template-columns: 30px 22px minmax(0, 1fr); } .runtime-step .el-tag { grid-column: 3; width: fit-content; } .explorer-notice { align-items: flex-start; flex-direction: column; } .explorer-metrics { flex-wrap: wrap; } }
</style>
