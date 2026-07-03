import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import HeartbeatIndicator from '@/components/common/HeartbeatIndicator.vue'

describe('HeartbeatIndicator 组件测试', () => {
  it('✅ 在线状态显示', () => {
    const wrapper = mount(HeartbeatIndicator, {
      global: { plugins: [ElementPlus] },
      props: {
        status: 'online',
        lastHeartbeat: Date.now()
      }
    })

    expect(wrapper.find('.heartbeat--online').exists()).toBe(true)
  })

  it('✅ 离线状态显示', () => {
    const wrapper = mount(HeartbeatIndicator, {
      global: { plugins: [ElementPlus] },
      props: {
        status: 'offline',
        lastHeartbeat: Date.now() - 300000
      }
    })

    expect(wrapper.find('.heartbeat--offline').exists()).toBe(true)
  })

  it('✅ 心跳时间格式化', () => {
    const wrapper = mount(HeartbeatIndicator, {
      global: { plugins: [ElementPlus] },
      props: {
        status: 'online',
        lastHeartbeat: Date.now() - 60000
      }
    })

    expect(wrapper.text()).toContain('1分钟')
  })

  it('✅ 心跳动画', () => {
    const wrapper = mount(HeartbeatIndicator, {
      global: { plugins: [ElementPlus] },
      props: {
        status: 'online',
        lastHeartbeat: Date.now()
      }
    })

    expect(wrapper.find('.heartbeat-pulse').exists()).toBe(true)
  })
})