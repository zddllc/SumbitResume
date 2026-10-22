<script setup lang="ts">
import { RouterLink, RouterView, useRouter } from 'vue-router'
import { auth, signOut } from './lib/auth'
import { useAction } from './lib/forms'
import NoticeBanner from './components/NoticeBanner.vue'
const router = useRouter()
const { busy, message, run } = useAction()
const routes = [
  { path: '/jobs', label: '职位与任务' }, { path: '/profile', label: '简历底板' },
  { path: '/personal', label: '申请信息' }, { path: '/settings', label: '模型设置' },
  { path: '/credentials', label: '外站账号' },
]
async function logout() {
  if (!window.confirm('确定退出？尚未保存的修改会丢失，后台任务不会因此自动取消。')) return
  await run(async () => { await signOut(); await router.replace('/login') })
}
</script>

<template>
  <div v-if="auth.user" class="shell">
    <aside class="sidebar">
      <RouterLink class="brand" to="/jobs">Resume<span>Studio.</span></RouterLink>
      <span class="eyebrow">你的求职工作台</span>
      <nav aria-label="工作区"><RouterLink v-for="route in routes" :key="route.path" :to="route.path" class="nav-button" active-class="active">{{ route.label }}</RouterLink></nav>
      <div class="sidebar-bottom"><strong>{{ auth.user.name }}</strong><small>{{ auth.user.email }}</small><button class="secondary small" :disabled="busy" @click="logout">退出登录</button><p class="hint">API · 后端图形界面 Chrome</p></div>
    </aside>
    <main class="content"><NoticeBanner :message="message" /><RouterView /></main>
  </div>
  <RouterView v-else />
</template>
