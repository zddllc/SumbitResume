<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { api } from '../lib/api'
import { lines, useAction, useUnsavedGuard } from '../lib/forms'
import type { AppState, PersonalInfo } from '../types'
import NoticeBanner from '../components/NoticeBanner.vue'
const form = reactive<PersonalInfo>({ work_authorization: '', needs_sponsorship: 'unspecified', willing_to_relocate: 'unspecified', preferred_locations: [], notice_period: '', salary_expectation: '', veteran_status: 'unspecified', disability_status: 'unspecified' })
const locations = ref('')
const dirty = ref(false)
useUnsavedGuard(dirty)
const { busy, message, run } = useAction()
const answers = [{ value: 'unspecified', label: '未填写' }, { value: 'yes', label: '是' }, { value: 'no', label: '否' }, { value: 'decline', label: '不愿披露' }]
onMounted(() => run(async () => { Object.assign(form, (await api<AppState>('state')).personal); locations.value = form.preferred_locations.join('\n') }))
async function save() { await run(async () => { await api('personal', 'POST', { ...form, preferred_locations: lines(locations.value) }); dirty.value = false }, '申请信息已加密保存，不会发送给模型。') }
</script>
<template>
  <header class="page-heading"><div><span class="eyebrow">APPLICATION FACTS</span><h1>申请信息</h1><p class="muted">自愿填写，可不披露。后端加密保存，不发送模型、不自动推断。</p></div></header>
  <NoticeBanner :message="message" />
  <form class="card stack" @input="dirty = true" @change="dirty = true" @submit.prevent="save"><fieldset :disabled="busy" class="stack">
    <div class="form-grid">
      <label>工作许可 / 可工作国家<input v-model="form.work_authorization" maxlength="500"></label>
      <label>是否需要雇主签证支持<select v-model="form.needs_sponsorship"><option v-for="answer in answers" :key="answer.value" :value="answer.value">{{ answer.label }}</option></select></label>
      <label>是否愿意搬迁<select v-model="form.willing_to_relocate"><option v-for="answer in answers" :key="answer.value" :value="answer.value">{{ answer.label }}</option></select></label>
      <label>偏好工作地区（每行一项）<textarea v-model="locations" rows="3" /></label>
      <label>到岗 / 离职通知期<input v-model="form.notice_period" maxlength="500"></label>
      <label>薪资期望（注明币种与周期）<input v-model="form.salary_expectation" maxlength="500"></label>
      <label>退役军人身份<select v-model="form.veteran_status"><option value="unspecified">未填写</option><option value="not_veteran">非退役军人</option><option value="veteran">退役军人</option><option value="decline">不愿披露</option></select></label>
      <label>是否有残障（自愿披露）<select v-model="form.disability_status"><option v-for="answer in answers" :key="answer.value" :value="answer.value">{{ answer.label }}</option></select></label>
    </div>
    <p class="hint">这些是个人事实，不等于某个雇主问卷的法律分类；未来投递时仍需确认具体问题。</p>
    <button type="submit">加密保存申请信息</button>
  </fieldset></form>
</template>
