<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { api } from '../lib/api'
import { useAction, useUnsavedGuard } from '../lib/forms'
import type { AppState, Credential } from '../types'
import NoticeBanner from '../components/NoticeBanner.vue'
const form = reactive({ site: '', label: '', username: '', password: '' })
const credentials = ref<Credential[]>([])
const dirty = ref(false)
useUnsavedGuard(dirty)
const { busy, message, run } = useAction()
async function load() { credentials.value = (await api<AppState>('state')).credentials }
onMounted(() => run(load))
async function save() {
  await run(async () => {
    await api('credentials', 'POST', form)
    Object.assign(form, { site: '', label: '', username: '', password: '' })
    dirty.value = false
    await load()
  }, '外站账号已加密保存。')
}
async function remove(id: string) {
  if (!window.confirm('确定删除这个外站账号？')) return
  await run(async () => { await api(`credentials/${encodeURIComponent(id)}`, 'DELETE'); await load() }, '外站账号已删除。')
}
</script>
<template>
  <header class="page-heading"><div><span class="eyebrow">ACCOUNT VAULT</span><h1>外站账号</h1><p class="muted">用户名和密码由后端加密保存，密码不回显、不发送模型。</p></div></header>
  <NoticeBanner :message="message" />
  <form class="card stack" @input="dirty = true" @change="dirty = true" @submit.prevent="save"><fieldset :disabled="busy" class="stack">
    <div class="form-grid">
      <label>网站域名<input v-model="form.site" required maxlength="500" placeholder="jobs.example.com"></label>
      <label>备注名称<input v-model="form.label" maxlength="500"></label>
      <label>用户名 / 邮箱<input v-model="form.username" required maxlength="500" autocomplete="off"></label>
      <label>密码<input v-model="form.password" type="password" required maxlength="4096" autocomplete="new-password"></label>
    </div>
    <p class="hint">目前只保存账号，不自动登录或提交。更换密码时删除旧条目后重新添加。</p>
    <button type="submit">加密保存外站账号</button>
  </fieldset></form>
  <section class="card"><h2>已保存的账号</h2><p v-if="!credentials.length" class="empty">尚未保存外站账号。</p>
    <div v-for="credential in credentials" :key="credential.id" class="credential-item">
      <div><strong>{{ credential.label || credential.site }}</strong><small>{{ credential.site }} · {{ credential.username_hint }}</small></div>
      <button class="secondary danger small" :disabled="busy" @click="remove(credential.id)">删除</button>
    </div>
  </section>
</template>
