import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(
  resolve(process.cwd(), 'src/views/WritingWorkspace.vue'),
  'utf8'
)

describe('WritingWorkspace unified navigation', () => {
  it('uses one collaboration workbench instead of three competing edit pages', () => {
    const classIndex = source.indexOf('class="workspace-navigation-tabs"')
    const tabsStart = source.lastIndexOf('<el-tabs', classIndex)
    const tabsEnd = source.indexOf('</el-tabs>', classIndex)
    const navigation = source.slice(tabsStart, tabsEnd)
    const labels = [...navigation.matchAll(/<el-tab-pane label="([^"]+)"/g)]
      .map(match => match[1])

    expect(classIndex).toBeGreaterThan(-1)
    expect(labels).toEqual([
      '研究总览',
      '协同工作台',
      '概念与论证',
      '研究迭代',
      '参考文献',
      '排版与交付'
    ])
    expect(source).not.toContain('class="content-studio-tabs"')
    expect(source).not.toContain('class="workspace-tabs"')
    expect(navigation).not.toContain('文档撰写')
    expect(navigation).not.toContain('PPT 制作')
    expect(navigation).not.toContain('联动工作台')
    expect(source).toContain('@tab-change="handleUnifiedNavigationChange"')
  })

  it('prioritizes a presentation selected from the document library over the saved pane layout', () => {
    expect(source).toContain(':key="`${selectedProjectId}-${linkedPresentationDocumentId}`"')
    expect(source).toContain('workbenchInitialPresetOverride.value = true')
    expect(source).toContain('linkedPresentationDocumentId.value = nextDocument.id')
  })
})
