import { effectScope, reactive, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { emptyMissionDraft, useMissionDraft } from '@/composables/useMissionDraft'
function setup(id = 'authenticated:1') {
  const scope = effectScope(), form = reactive(emptyMissionDraft()), owner = ref(id)
  const draft = scope.run(() => useMissionDraft(form, owner))!
  return { form, owner, draft, stop: () => scope.stop() }
}
describe('mission draft lifecycle', () => {
  it('requires explicit restore after remount and retains project and evidence references', () => {
    const a = setup(); Object.assign(a.form, { title: '重新交付', project_id: 'p', mission_type: 'document', objective: 'old-task old-artifact sha256' }); a.stop()
    const b = setup(); expect(b.draft.pending.value).toBe(true); expect(b.form.objective).toBe('')
    b.draft.restore(); expect(b.form).toEqual({ title: '重新交付', project_id: 'p', mission_type: 'document', objective: 'old-task old-artifact sha256' }); b.stop()
  })
  it('isolates accounts and does not erase another account on a late success', () => {
    const a = setup(); a.form.objective = 'A'; const old = { ...a.form }; a.owner.value = 'authenticated:2'
    expect(a.form.objective).toBe(''); expect(a.draft.pending.value).toBe(false); a.form.objective = 'B'
    a.draft.submitted(old, 'authenticated:1'); expect(a.form.objective).toBe('B')
    a.owner.value = 'authenticated:1'; a.draft.restore(); expect(a.form.objective).toBe('A'); a.stop()
  })
  it('keeps edits until acknowledged success, and clears only the submitted version', () => {
    const a = setup(); a.form.objective = 'original'; const old = { ...a.form }; a.form.objective = 'edited'
    a.draft.submitted(old, a.owner.value); expect(a.form.objective).toBe('edited')
    a.draft.submitted({ ...a.form }, a.owner.value); a.stop(); const b = setup(); expect(b.draft.pending.value).toBe(false); b.stop()
  })
  it('keeps unreadable drafts pending and supports explicit discard', () => {
    localStorage.setItem('command-center:draft:v1:authenticated%3A1', '{bad')
    const a = setup(); expect(a.draft.pending.value).toBe(true); expect(a.draft.canRestore()).toBe(false); a.draft.discard(); expect(a.draft.pending.value).toBe(false); a.stop()
  })
  it('reports storage failure without claiming the draft was saved', () => {
    const a = setup(); const spy = vi.spyOn(localStorage, 'setItem').mockImplementation(() => { throw new Error('quota') })
    a.form.objective = 'retain me'; expect(a.form.objective).toBe('retain me'); expect(a.draft.notice.value).toContain('保存失败'); spy.mockRestore(); a.stop()
  })
})

it('persists submission identity through response loss and refresh, changes it for changed content', () => {
  const a = setup(); a.form.objective = 'retry me'
  const payload = { objective: 'retry me' }; const first = a.draft.submissionKey(payload); a.stop()
  const b = setup(); b.draft.restore(); expect(b.draft.submissionKey(payload)).toBe(first)
  b.form.objective = 'new intent'; expect(b.draft.submissionKey({ objective: 'new intent' })).not.toBe(first); b.stop()
})


it('blocks sending when the submission identity cannot be persisted', () => {
  const a = setup(); a.form.objective = 'retain me'
  const spy = vi.spyOn(localStorage, 'setItem').mockImplementation(() => { throw new Error('quota') })
  expect(() => a.draft.submissionKey({ objective: 'retain me' })).toThrow('Cannot persist')
  expect(a.draft.notice.value).toContain('尚未发送请求')
  spy.mockRestore(); a.stop()
})

it('does not restore a draft with a corrupt submission identity as a new request', () => {
  localStorage.setItem('command-center:draft:v1:authenticated%3A1', JSON.stringify({ version: 1, draft: { ...emptyMissionDraft(), objective: 'already sent' }, submission: { signature: '{}', key: '?' } }))
  const a = setup(); expect(a.draft.pending.value).toBe(true); expect(a.draft.canRestore()).toBe(false)
  a.draft.restore(); expect(a.form.objective).toBe(''); expect(() => a.draft.submissionKey({})).toThrow()
  a.stop()
})
