import { defineComponent, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ResumeEditor from './ResumeEditor.vue'
import { emptyResume } from '../lib/forms'

function editor() {
  const profile = ref(emptyResume())
  profile.value.contact.name = 'Sample Applicant'
  profile.value.experience = [
    { company: 'First Co', title: 'Engineer', location: '', start_date: '', end_date: '', bullets: ['First\ncontinued', 'Second'] },
    { company: 'Other Co', title: 'Earlier Role', location: '', start_date: '', end_date: '', bullets: ['Other job'] },
  ]
  const host = mount(defineComponent({
    components: { ResumeEditor },
    setup: () => ({ profile }),
    template: '<ResumeEditor v-model="profile" />',
  }))
  return { host, profile }
}

describe('shared base and tailored editor', () => {
  it('edits, moves, adds and removes independent work points without touching another job', async () => {
    const { host, profile } = editor()
    const first = host.find('[data-section=experience] .entry')
    expect(first.find('[data-move=up]').attributes('disabled')).toBeDefined()
    expect(first.findAll('[data-move=down]')[1]!.attributes('disabled')).toBeDefined()
    await first.findAll('.work-bullet-entry textarea')[0]!.setValue('Edited\nsame entry')
    await first.find('[data-move=down]').trigger('click')
    expect(profile.value.experience[0]!.bullets).toEqual(['Second', 'Edited\nsame entry'])
    await first.find('.work-bullets .section-heading button').trigger('click')
    await first.findAll('.work-bullet-entry textarea')[2]!.setValue('Added point')
    await first.findAll('button[aria-label^="删除工作要点"]')[0]!.trigger('click')
    expect(profile.value.experience[0]!.bullets).toEqual(['Edited\nsame entry', 'Added point'])
    expect(profile.value.experience[1]!.bullets).toEqual(['Other job'])
    host.unmount()
  })
  it('revalidates textarea values when a point moves to a reused DOM row', async () => {
    const { host } = editor()
    const first = host.find('[data-section=experience] .entry')
    await first.findAll('textarea')[1]!.setValue('   ')
    await first.findAll('[data-move=up]')[1]!.trigger('click')
    await nextTick()
    const fields = first.findAll('textarea')
    expect((fields[0]!.element as HTMLTextAreaElement).validationMessage).not.toBe('')
    expect((fields[1]!.element as HTMLTextAreaElement).validationMessage).toBe('')
    host.unmount()
  })
  it('preserves the existing fifty-point limit and re-enables add after delete', async () => {
    const { host, profile } = editor()
    profile.value.experience[0]!.bullets = Array.from({ length: 50 }, (_, index) => `Point ${index}`)
    await nextTick()
    const first = host.find('[data-section=experience] .entry')
    expect(first.find('.work-bullets .section-heading button').attributes('disabled')).toBeDefined()
    await first.find('button[aria-label^="删除工作要点"]').trigger('click')
    expect(profile.value.experience[0]!.bullets).toHaveLength(49)
    expect(first.find('.work-bullets .section-heading button').attributes('disabled')).toBeUndefined()
    host.unmount()
  })
})
