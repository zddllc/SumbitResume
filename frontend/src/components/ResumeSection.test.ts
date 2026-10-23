import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ResumeSection from './ResumeSection.vue'

describe('resume section folding', () => {
  it('starts closed, shows the entry count and toggles through its native summary', async () => {
    const wrapper = mount(ResumeSection, { props: { title: '论文', count: 12 }, slots: { default: '<input value="Saved content">' } })
    expect((wrapper.element as HTMLDetailsElement).open).toBe(false)
    expect(wrapper.get('summary').text()).toContain('12 项')
    await wrapper.get('summary').trigger('click')
    expect((wrapper.element as HTMLDetailsElement).open).toBe(true)
    const input = wrapper.get('input').element
    await wrapper.get('input').setValue('Edited content')
    await wrapper.get('summary').trigger('click')
    expect((wrapper.element as HTMLDetailsElement).open).toBe(false)
    await wrapper.get('summary').trigger('click')
    expect(wrapper.get('input').element).toBe(input)
    expect((input as HTMLInputElement).value).toBe('Edited content')
    wrapper.unmount()
  })

  it('keeps the chosen folded state while counts update and respects initially open sections', async () => {
    const wrapper = mount(ResumeSection, { props: { title: '工作经历', count: 2, initiallyOpen: true } })
    await wrapper.get('summary').trigger('click')
    expect((wrapper.element as HTMLDetailsElement).open).toBe(false)
    await wrapper.setProps({ count: 3 })
    expect((wrapper.element as HTMLDetailsElement).open).toBe(false)
    expect(wrapper.get('summary').text()).toContain('3 项')
    wrapper.unmount()
  })

  it('reveals invalid collapsed controls before the browser reports validation', () => {
    const wrapper = mount(ResumeSection, { props: { title: '内容', count: 1 }, slots: { default: '<input required>' } })
    expect((wrapper.element as HTMLDetailsElement).open).toBe(false)
    expect((wrapper.get('input').element as HTMLInputElement).checkValidity()).toBe(false)
    expect((wrapper.element as HTMLDetailsElement).open).toBe(true)
    wrapper.unmount()
  })
})
