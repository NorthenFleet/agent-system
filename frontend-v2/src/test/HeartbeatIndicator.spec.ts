import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import HeartbeatIndicator from '@/components/common/HeartbeatIndicator.vue'
import type { Agent } from '@/stores/agents'

function agent(overrides: Partial<Agent> = {}): Agent {
  return {
    agent_id: 'optimus',
    agent_name: '擎天柱',
    status: 'online',
    current_task: null,
    last_heartbeat: '2026-09-17T00:00:00Z',
    heartbeat_age_seconds: 0,
    health: 'healthy',
    cpu_usage: null,
    memory_usage: null,
    ...overrides
  }
}

describe('HeartbeatIndicator 组件测试', () => {
  it('✅ 在线状态显示', () => {
    const wrapper = mount(HeartbeatIndicator, { props: { agent: agent() } })

    expect(wrapper.find('.status-healthy').exists()).toBe(true)
  })

  it('✅ 离线状态显示', () => {
    const wrapper = mount(HeartbeatIndicator, {
      props: { agent: agent({ status: 'offline', health: 'offline', heartbeat_age_seconds: 300 }) }
    })

    expect(wrapper.find('.status-offline').exists()).toBe(true)
  })

  it('✅ 心跳时间格式化', () => {
    const wrapper = mount(HeartbeatIndicator, {
      props: { agent: agent({ heartbeat_age_seconds: 60 }) }
    })

    expect(wrapper.attributes('title')).toContain('1分钟前')
  })

  it('✅ 心跳动画', () => {
    const wrapper = mount(HeartbeatIndicator, {
      props: { agent: agent({ health: 'critical' }) }
    })

    expect(wrapper.find('.status-critical').exists()).toBe(true)
  })
})
