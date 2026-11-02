import { ref, watch, type Ref } from 'vue'

export type MissionDraft = { title: string; project_id: string; mission_type: 'software' | 'document'; objective: string }
export const emptyMissionDraft = (): MissionDraft => ({ title: '', project_id: '', mission_type: 'software', objective: '' })
export function useMissionDraft(form: MissionDraft, owner: Ref<string>) {
  const pending = ref(false)
  const notice = ref('')
  let paused = false
  let stored: MissionDraft | null = null
  let key = ''
  let submission: { signature: string; key: string } | null = null
  const persist = () => localStorage.setItem(key, JSON.stringify({ version: 1, draft: { ...form }, submission }))
  const reset = () => { paused = true; Object.assign(form, emptyMissionDraft()); paused = false }
  watch(owner, value => {
    reset(); pending.value = false; stored = null; submission = null
    key = value ? `command-center:draft:v1:${encodeURIComponent(value)}` : ''
    notice.value = key ? '草稿仅保存在当前浏览器，按账号区分。' : '当前用户身份未就绪，草稿暂不保存。'
    if (!key) return
    try {
      const raw = localStorage.getItem(key)
      if (!raw) return
      pending.value = true
      const data = JSON.parse(raw)
      if (data.version !== 1 || !data.draft || !['software', 'document'].includes(data.draft.mission_type) ||
          !['title', 'project_id', 'objective'].every(k => typeof data.draft[k] === 'string')) throw new Error('invalid draft')
      if (data.submission != null) {
        if (typeof data.submission.signature !== 'string' || typeof data.submission.key !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(data.submission.key)) throw new Error('invalid submission key')
        submission = { signature: data.submission.signature, key: data.submission.key }
      }
      stored = { title: data.draft.title, project_id: data.draft.project_id, mission_type: data.draft.mission_type, objective: data.draft.objective }
      notice.value = submission ? '发现此账号的提交草稿，结果可能尚未确认。恢复后可核对并重试。' : '发现此账号的未提交草稿，请恢复或丢弃后继续。'
    } catch { notice.value = pending.value ? '已保存草稿无法读取，可丢弃后重新填写。' : '浏览器存储不可用，草稿暂不保存。' }
  }, { immediate: true, flush: 'sync' })
  watch(form, () => {
    if (paused || pending.value || !key) return
    try {
      if (form.title || form.objective || form.project_id) {
        persist()
        notice.value = '草稿已保存到当前浏览器。'
      } else { localStorage.removeItem(key); notice.value = '当前没有已保存草稿。' }
    } catch { notice.value = '草稿保存失败，请保留当前页面并复制内容。' }
  }, { deep: true, flush: 'sync' })
  function restore() {
    if (!stored) return
    paused = true; Object.assign(form, stored); paused = false
    pending.value = false; stored = null; notice.value = '草稿已恢复，请核对项目和目标后提交。'
  }
  function discard() {
    try { if (key) localStorage.removeItem(key) }
    catch { notice.value = '草稿清理失败，内容仍保留，请稍后重试。'; return }
    pending.value = false; stored = null; submission = null; reset(); notice.value = '草稿已清理。'
  }
  function submitted(snapshot: MissionDraft, submittedOwner: string) {
    if (submittedOwner !== owner.value || JSON.stringify(snapshot) !== JSON.stringify(form)) return
    discard()
  }
  function submissionKey(payload: unknown) {
    if (!key || pending.value) throw new Error('草稿身份尚未就绪')
    const signature = JSON.stringify(payload)
    if (!submission || submission.signature !== signature) submission = { signature, key: crypto.randomUUID() }
    try { persist() } catch { notice.value = '提交标识保存失败，尚未发送请求，请保留页面后重试。'; throw new Error('Cannot persist submission key') }
    return submission.key
  }
  return { pending, notice, restore, discard, submitted, submissionKey, canRestore: () => !!stored }
}
