import { createApp, h, ref } from 'vue'
import './style.css'
import App from './App.vue'
import { router } from './router'
import { onUnauthorized } from './lib/api'
import { expireSession } from './lib/auth'
import { errorText } from './lib/forms'

const failure = ref('')
router.onError(error => { failure.value = errorText(error); console.error(error) })
onUnauthorized(() => { expireSession(); void router.replace('/login') })
const app = createApp({
  setup() {
    return () => failure.value
      ? h('main', { class: 'auth-page' }, [
        h('section', { class: 'auth-card' }, [
          h('h1', '连接工作台失败'),
          h('p', { class: 'notice error', role: 'alert' }, failure.value),
          h('button', { onClick: () => window.location.reload() }, '重新加载'),
        ]),
      ])
      : h(App)
  },
})
app.config.errorHandler = error => { failure.value = errorText(error); console.error(error) }
app.use(router).mount('#app')
