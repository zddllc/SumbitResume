<script setup lang="ts">
import type { Message } from '../types'
defineProps<{ message: Message | null }>()
</script>
<template>
  <p v-if="message" class="notice" :class="{ error: message.kind === 'error' }" :role="message.kind === 'error' ? 'alert' : 'status'">{{ message.text }}</p>
</template>
