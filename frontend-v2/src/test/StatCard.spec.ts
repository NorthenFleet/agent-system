import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import StatCard from '@/components/common/StatCard.vue'

vi.mock('@element-plus/icons-vue', () => ({
  TrendingUp: { name: 'TrendingUp', render: () => null },
  TrendingDown: { name: 'TrendingDown', render: () => null },
  Minus: { name: 'Minus', render: () => null }
}))

describe('StatCard 组件测试', () => {
  it('✅ 基本渲染', () => {
    const wrapper = mount(StatCard, {
      global: { plugins: [ElementPlus] },
      props: {
        title: '测试指标',
        value: 1234,
        unit: '个'
      }
    })

    expect(wrapper.text()).toContain('测试指标')
    expect(wrapper.text()).toContain('1234')
    expect(wrapper.text()).toContain('个')
  })

  it('✅ 变化趋势显示 - 上升', () => {
    const wrapper = mount(StatCard, {
      global: { plugins: [ElementPlus] },
      props: {
        title: '活跃用户',
        value: 1000,
        change: 15.5,
        unit: '人'
      }
    })

    expect(wrapper.text()).toContain('+15.5%')
  })

  it('✅ 变化趋势显示 - 下降', () => {
    const wrapper = mount(StatCard, {
      global: { plugins: [ElementPlus] },
      props: {
        title: '错误率',
        value: 2.5,
        change: -10.2,
        unit: '%'
      }
    })

    expect(wrapper.text()).toContain('-10.2%')
  })

  it('✅ 变化趋势显示 - 持平', () => {
    const wrapper = mount(StatCard, {
      global: { plugins: [ElementPlus] },
      props: {
        title: '访问量',
        value: 5000,
        change: 0,
        unit: '次'
      }
    })

    expect(wrapper.text()).toContain('0%')
  })

  it('✅ 不同颜色主题', () => {
    const wrapper = mount(StatCard, {
      global: { plugins: [ElementPlus] },
      props: {
        title: '告警数',
        value: 5,
        color: 'danger',
        unit: '条'
      }
    })

    expect(wrapper.classes()).toContain('stat-card--danger')
  })

  it('✅ 图标自定义', () => {
    const wrapper = mount(StatCard, {
      global: { plugins: [ElementPlus] },
      props: {
        title: '任务完成',
        value: 80,
        icon: 'TrendingUp',
        unit: '%'
      }
    })

    expect(wrapper.find('svg').exists()).toBe(true)
  })
})