<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { api } from '../lib/api'
import { useAction, useUnsavedGuard } from '../lib/forms'
import type { AppState, Provider } from '../types'
import NoticeBanner from '../components/NoticeBanner.vue'
const form = reactive({ provider: 'deepseek' as Provider, model: 'deepseek-flash', base_url: '', api_version: '2024-12-01-preview', api_key: '' })
const keySaved = ref(false)
const dirty = ref(false)
useUnsavedGuard(dirty)
const { busy, message, run } = useAction()
const defaults: Record<Provider, string> = { deepseek: 'deepseek-flash', azure_openai: 'gpt-6.1-sol', azure_deepseek: 'DeepSeek-V4-Flash', openai: '' }
function changeProvider() { form.model = defaults[form.provider]; form.base_url = ''; form.api_key = '' }
async function load() {
  const state = await api<AppState>('state')
  for (const key of ['provider', 'model', 'base_url', 'api_version'] as const) {
    const value = state.llm[key]
    if (value !== undefined) Object.assign(form, { [key]: value })
  }
  keySaved.value = state.llm.key_saved
}
onMounted(() => run(load))
async function save() { await run(async () => { await api('llm', 'POST', form); form.api_key = ''; keySaved.value = true; dirty.value = false }, '模型配置已加密保存；实际调用时验证服务可用性。') }
async function remove() {
  if (!window.confirm('删除已保存的模型 key？后续需要重新配置。')) return
  await run(async () => { await api('llm', 'DELETE'); form.api_key = ''; keySaved.value = false }, 'API key 已删除。')
}
</script>
<template>
  <header class="page-heading"><div><span class="eyebrow">MODEL CONNECTION</span><h1>模型设置</h1><p class="muted">API key 由后端加密保存，不回显、不放入前端构建产物。</p></div></header>
  <NoticeBanner :message="message" />
  <form class="card stack" @input="dirty = true" @change="dirty = true" @submit.prevent="save">
    <fieldset :disabled="busy" class="stack">
      <div class="form-grid">
        <label>供应商<select v-model="form.provider" @change="changeProvider"><option value="deepseek">DeepSeek</option><option value="azure_openai">Azure OpenAI</option><option value="azure_deepseek">Azure DeepSeek</option><option value="openai">OpenAI / 兼容接口</option></select></label>
        <label>模型 / Azure deployment<input v-model="form.model" required maxlength="500"></label>
        <label>API 地址<input v-model="form.base_url" type="url" maxlength="500" placeholder="默认供应商地址；Azure 必填"></label>
        <label>Azure OpenAI API version<input v-model="form.api_version" maxlength="500"></label>
      </div>
      <label>API key<input v-model="form.api_key" type="password" autocomplete="off" maxlength="4096" :placeholder="keySaved ? '已保存，留空保留原 key' : '首次配置必填'"></label>
      <p class="hint">切换供应商或 API 地址时需重新填写 key。保存设置不产生模型费用。</p>
      <div class="button-row"><button type="submit">加密保存设置</button><button type="button" class="secondary danger" @click="remove">删除已存 key</button></div>
    </fieldset>
  </form>
</template>
