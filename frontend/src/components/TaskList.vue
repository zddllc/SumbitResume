<script setup lang="ts">
import type { Task } from '../types'
import { activeTask, dateText } from '../lib/forms'
defineProps<{ tasks: Task[]; disabled?: boolean }>()
defineEmits<{ cancel: [id: string] }>()
const kinds = { browser: '打开 Chrome', parse: '解析简历', scan: '职位遍历与定制', tailor: '定制已保存职位' }
const statuses = { queued: '等待中', running: '执行中', cancelling: '取消中', succeeded: '已完成', failed: '有错误', cancelled: '已取消', interrupted: '已中断' }
</script>
<template>
  <div class="stack">
    <p v-if="!tasks.length" class="empty">暂无任务。</p>
    <article v-for="task in tasks" :key="task.id" class="task">
      <div class="section-heading"><strong>{{ kinds[task.kind] }} · {{ dateText(task.created_at) }}</strong><span class="badge" :class="task.status">{{ statuses[task.status] }}</span></div>
      <p v-if="task.kind === 'scan' || task.kind === 'tailor'" class="hint">已处理 {{ task.processed }} · 新生成 {{ task.generated }} · 复用 {{ task.cached }} · 失败 {{ task.failed }}</p>
      <p v-if="task.error">{{ task.error }}</p>
      <details v-if="task.errors.length"><summary>查看具体失败职位</summary><p v-for="(error, index) in task.errors" :key="index">{{ error.job_id }}: {{ error.message }}</p></details>
      <button v-if="activeTask(task)" class="secondary small" :disabled="disabled || task.status === 'cancelling'" @click="$emit('cancel', task.id)">取消任务</button>
    </article>
  </div>
</template>
