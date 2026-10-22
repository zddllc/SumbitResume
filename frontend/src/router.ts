import { createRouter, createWebHistory } from 'vue-router'
import { auth, ensureSession } from './lib/auth'
import LoginPage from './views/LoginPage.vue'
import JobsPage from './views/JobsPage.vue'
import ProfilePage from './views/ProfilePage.vue'
import PersonalPage from './views/PersonalPage.vue'
import SettingsPage from './views/SettingsPage.vue'
import CredentialsPage from './views/CredentialsPage.vue'

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', redirect: '/jobs' },
    { path: '/login', component: LoginPage },
    { path: '/jobs', component: JobsPage },
    { path: '/profile', component: ProfilePage },
    { path: '/personal', component: PersonalPage },
    { path: '/settings', component: SettingsPage },
    { path: '/credentials', component: CredentialsPage },
    { path: '/:pathMatch(.*)*', redirect: '/jobs' },
  ],
})
router.beforeEach(async to => {
  await ensureSession()
  if (!auth.user && to.path !== '/login') return '/login'
  if (auth.user && to.path === '/login') return '/jobs'
})
