import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import DocumentEvaluationPanel from '@/components/writing/DocumentEvaluationPanel.vue'
import type {
  DocumentEvaluationProfile,
  DocumentEvaluationReport
} from '@/api/writing'

const profile: DocumentEvaluationProfile = {
  id: 'rich_text.doctoral.v1',
  system_profile_id: 'rich_text.doctoral.v1',
  name: '通用博士论文评价标准',
  version: '1.0.0',
  kind: 'rich_text',
  document_types: ['博士论文'],
  pass_threshold: 80,
  profile_sha256: 'profile-sha',
  policy_revision: 0,
  maturity_labels: ['材料汇集', '结构草稿', '正文完整', '内审合格', '送审就绪', '答辩就绪'],
  dimensions: [
    { id: 'method', name: '方法设计', weight: 50, min_score: 70, source: 'ai' },
    { id: 'evidence', name: '实验与证据', weight: 50, min_score: 70, source: 'ai' }
  ],
  gates: [
    { id: 'structure', name: '结构完整', source: 'automatic', required: true, critical: false },
    { id: 'ethics', name: '学术伦理确认', source: 'external', required: true, critical: true }
  ]
}

function report(status: DocumentEvaluationReport['status']): DocumentEvaluationReport {
  return {
    id: 'eval-1',
    project_id: 'project-1',
    document_id: 'document-1',
    document_title: '测试论文',
    document_kind: 'rich_text',
    document_type: '博士论文',
    source_sha256: 'source-sha',
    profile_id: profile.id,
    profile_name: profile.name,
    profile_version: profile.version,
    profile_sha256: profile.profile_sha256,
    model: status === 'pending' ? '' : 'gpt-oss:20b',
    status,
    decision: status === 'confirmed' ? 'qualified' : 'pending',
    maturity_level: status === 'confirmed' ? 'L4' : 'L2',
    maturity_label: status === 'confirmed' ? '送审就绪' : '正文完整',
    technical_score: 100,
    provisional_score: status === 'pending' ? null : 82,
    confirmed_score: status === 'confirmed' ? 85 : null,
    coverage: status === 'pending' ? 0 : 100,
    dimensions: profile.dimensions.map(row => ({
      ...row,
      status: status === 'pending' ? 'pending' : 'pass',
      score: status === 'pending' ? null : 82,
      confirmed_score: status === 'confirmed' ? 85 : null,
      summary: status === 'pending' ? '尚未执行学术深度评价' : '证据已覆盖',
      evidence: [],
      recommendations: []
    })),
    gates: profile.gates.map(row => ({
      ...row,
      status: row.id === 'structure' ? 'pass' : status === 'confirmed' ? 'pass' : 'pending',
      reason: '',
      evidence: []
    })),
    priority_actions: status === 'pending' ? [] : ['补充多随机种子实验'],
    linked_documents: [],
    audit: [],
    created_at: '2026-07-30T00:00:00Z',
    updated_at: '2026-07-30T00:00:00Z',
    evaluated_at: ''
  }
}

function mountPanel(status: DocumentEvaluationReport['status']) {
  return mount(DocumentEvaluationPanel, {
    props: {
      profile,
      report: report(status),
      profiles: [profile]
    },
    global: { plugins: [ElementPlus] }
  })
}

describe('DocumentEvaluationPanel', () => {
  it('shows pending items without converting them to zero', () => {
    const wrapper = mountPanel('pending')
    expect(wrapper.text()).toContain('AI建议分')
    expect(wrapper.text()).toContain('待评价')
    expect(wrapper.text()).not.toContain('AI建议分0')
    expect(wrapper.text()).toContain('未评价项目不记0分')
  })

  it.each([
    ['evaluating', '评价中'],
    ['provisional', 'AI建议'],
    ['confirmed', '专家已确认'],
    ['stale', '需复评'],
    ['failed', '评价失败']
  ] as const)('renders %s state as %s', (status, label) => {
    const wrapper = mountPanel(status)
    expect(wrapper.text()).toContain(label)
  })

  it('renders backend-provided dimensions and hard gates dynamically', () => {
    const wrapper = mountPanel('provisional')
    expect(wrapper.text()).toContain('方法设计')
    expect(wrapper.text()).toContain('实验与证据')
    expect(wrapper.text()).toContain('结构完整')
    expect(wrapper.text()).toContain('学术伦理确认')
    expect(wrapper.text()).toContain('高总分不能抵消硬门槛失败')
  })

  it('clearly separates AI advice from expert-confirmed score', () => {
    const wrapper = mountPanel('confirmed')
    expect(wrapper.text()).toContain('AI建议分')
    expect(wrapper.text()).toContain('专家确认分')
    expect(wrapper.text()).toContain('已形成审计记录')
    expect(wrapper.text()).toContain('85')
  })
})
