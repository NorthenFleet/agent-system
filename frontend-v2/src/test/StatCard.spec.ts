import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import StatCard from '@/components/common/StatCard.vue'

describe('StatCard 组件测试', () => {
  it('✅ 基本渲染', () => {
    const wrapper = mount(StatCard, {
      global: { plugins: [ElementPlus] },
      props: {
        title: '测试指标',
        value: 1234,
        icon: '📊',
        color: '#409eff'
      }
    })

    expect(wrapper.text()).toContain('测试指标')
    expect(wrapper.text()).toContain('1234')
    expect(wrapper.text()).toContain('📊')
  })

  it('✅ 渲染配置颜色', () => {
    const wrapper = mount(StatCard, {
      global: { plugins: [ElementPlus] },
      props: {
        title: '告警数',
        value: 5,
        icon: '⚠️',
        color: '#f56c6c'
      }
    })

    expect((wrapper.find('.stat-icon').element as HTMLElement).style.background).toBe(
      'rgba(245, 108, 108, 0.082)'
    )
  })

  it('✅ 数值为 0 时仍正确显示', () => {
    const wrapper = mount(StatCard, {
      global: { plugins: [ElementPlus] },
      props: {
        title: '离线数',
        value: 0,
        icon: '○',
        color: '#909399'
      }
    })

    expect(wrapper.find('.stat-value').text()).toBe('0')
  })

  it('✅ 统计卡保持标准结构', () => {
    const wrapper = mount(StatCard, {
      global: { plugins: [ElementPlus] },
      props: {
        title: '任务完成',
        value: 80,
        icon: '✅',
        color: '#67c23a'
      }
    })

    expect(wrapper.find('.stat-content').exists()).toBe(true)
    expect(wrapper.find('.stat-info').exists()).toBe(true)
  })
})
