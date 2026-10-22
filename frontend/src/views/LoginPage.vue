<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { auth, signIn } from '../lib/auth'
import { useAction } from '../lib/forms'
import NoticeBanner from '../components/NoticeBanner.vue'

const router = useRouter()
const email = ref(''), password = ref(''), name = ref('')
const { busy, message, run } = useAction()
async function submit() {
  await run(async () => {
    await signIn(email.value, password.value, auth.setup_required ? name.value : undefined)
    password.value = ''
    await router.replace('/jobs')
  })
}
</script>
<template>
  <main class="auth-page"><section class="auth-card">
    <span class="eyebrow">RESUME STUDIO</span>
    <h1>{{ auth.setup_required ? '建立你的工作台' : '欢迎回来' }}</h1>
    <p class="muted">{{ auth.setup_required ? '创建本机唯一账号，之后关闭注册。' : '登录后管理简历、职位和求职资料。' }}</p>
    <NoticeBanner :message="message" />
    <form class="stack" @submit.prevent="submit">
      <label v-if="auth.setup_required">显示名称<input v-model="name" required maxlength="100" autocomplete="name"></label>
      <label>邮箱<input v-model="email" type="email" required maxlength="254" autocomplete="username"></label>
      <label>密码<input v-model="password" type="password" required :minlength="auth.setup_required ? 8 : 1" maxlength="1024" :autocomplete="auth.setup_required ? 'new-password' : 'current-password'"></label>
      <p v-if="auth.setup_required" class="hint">至少 8 个字符。应用账号与 LinkedIn 账号无关。</p>
      <button type="submit" :disabled="busy">{{ busy ? '请稍候…' : auth.setup_required ? '创建并进入' : '登录工作台' }}</button>
    </form>
    <p class="footnote">单用户 · 会话 Cookie + CSRF 校验</p>
  </section></main>
</template>
