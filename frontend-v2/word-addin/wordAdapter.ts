import { sha256, type CapturedParagraph } from './core'

declare const Office: any
declare const Word: any

function requireWord(): void {
  if (typeof Office === 'undefined' || typeof Word === 'undefined') {
    throw new Error('请在Microsoft Word桌面版中打开此任务窗格')
  }
}

export async function captureCurrentParagraph(): Promise<CapturedParagraph> {
  requireWord()
  return Word.run(async (context: any) => {
    const selection = context.document.getSelection()
    const paragraphs = selection.paragraphs
    paragraphs.load('items/text,items/style')
    await context.sync()
    if (paragraphs.items.length !== 1) {
      throw new Error('首期仅支持光标所在的单个普通段落')
    }
    const paragraph = paragraphs.items[0]
    const text = String(paragraph.text || '')
    if (!text.trim()) throw new Error('当前段落为空')
    const url = String(Office.context?.document?.url || '')
    if (!url) throw new Error('请先将文档另存为Word候选副本')
    return {
      text,
      sha256: await sha256(text),
      style: String(paragraph.style || ''),
      documentFingerprint: await sha256(url)
    }
  })
}

export async function replaceCurrentParagraph(
  expected: CapturedParagraph,
  replacementText: string
): Promise<{ beforeSha256: string; afterSha256: string }> {
  requireWord()
  return Word.run(async (context: any) => {
    const selection = context.document.getSelection()
    const paragraphs = selection.paragraphs
    paragraphs.load('items/text,items/style')
    await context.sync()
    if (paragraphs.items.length !== 1) throw new Error('应用前选区已跨越多个段落')
    const paragraph = paragraphs.items[0]
    const beforeText = String(paragraph.text || '')
    const beforeSha256 = await sha256(beforeText)
    if (beforeSha256 !== expected.sha256) throw new Error('当前Word段落已变化，请重新读取并生成建议')
    if (String(paragraph.style || '') !== expected.style) throw new Error('当前Word段落样式已变化，请重新读取')
    paragraph.insertText(replacementText, 'Replace')
    paragraph.load('text,style')
    await context.sync()
    const afterText = String(paragraph.text || '')
    const afterSha256 = await sha256(afterText)
    if (afterSha256 !== await sha256(replacementText)) {
      throw new Error('Word写入结果与已验证候选不一致')
    }
    if (String(paragraph.style || '') !== expected.style) {
      throw new Error('Word写入改变了段落样式，候选不得回流')
    }
    return { beforeSha256, afterSha256 }
  })
}
