import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'
import { auth } from '../lib/auth'
import LoginPage from './LoginPage.vue'

describe('password form', () => {
  it('uses an eight-character minimum only for initial account setup', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: LoginPage }] })
    await router.push('/')
    auth.setup_required = true
    const wrapper = mount(LoginPage, { global: { plugins: [router] } })
    expect(wrapper.find('input[type=password]').attributes('minlength')).toBe('8')
    auth.setup_required = false
    await wrapper.vm.$nextTick()
    expect(wrapper.find('input[type=password]').attributes('minlength')).toBe('1')
    wrapper.unmount()
  })
})
