<template>
  <section class="page" data-module="pumpstation-detail">
    <header class="page-head">
      <div>
        <h2>泵站详情</h2>
        <p class="page-desc">进入详情时始终从服务端读取最新状态，动作按既定顺序办理，重复或越序操作会被服务端拦下。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" type="button" to="/pumpstation">返回列表</RouterLink>
      </div>
    </header>

    <div v-if="notFound" class="empty-state">该泵站不存在或已归档，可返回列表重新选择。</div>

    <template v-else-if="entry">
      <div class="stat-row">
        <article class="stat-card">
          <span class="stat-label">泵站编号</span>
          <strong class="stat-value">{{ entry['泵站编号'] }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">当前状态</span>
          <strong class="stat-value">{{ entry.status }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">下一个可办动作</span>
          <strong class="stat-value">{{ entry.next_action ?? '已办结，无待办动作' }}</strong>
        </article>
      </div>

      <table class="data-table">
        <thead>
          <tr><th>字段</th><th>内容</th></tr>
        </thead>
        <tbody>
          <tr v-for="column in columns" :key="column">
            <td>{{ column }}</td>
            <td>{{ entry[column] ?? '—' }}</td>
          </tr>
        </tbody>
      </table>

      <div class="page-actions" style="margin: 16px 0;">
        <button
          v-for="action in actions"
          :key="action"
          class="btn"
          :class="{ primary: action === entry.next_action }"
          type="button"
          :disabled="busyAction !== null || action !== entry.next_action"
          :title="action !== entry.next_action ? unavailableHint(action) : ''"
          @click="runAction(action)"
        >
          {{ busyAction === action ? `正在${action}…` : action }}
        </button>
      </div>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>

      <h3 style="margin: 20px 0 8px;">办理历史</h3>
      <table class="data-table">
        <thead>
          <tr><th>时间</th><th>动作</th><th>变更前</th><th>变更后</th><th>备注</th></tr>
        </thead>
        <tbody>
          <tr v-for="(item, index) in entry.history" :key="index">
            <td>{{ item.time }}</td>
            <td>{{ item.action }}</td>
            <td>{{ item.from ?? '—' }}</td>
            <td>{{ item.to ?? '—' }}</td>
            <td>{{ item.remark ?? '—' }}</td>
          </tr>
          <tr v-if="!entry.history.length">
            <td colspan="5" class="empty-state">暂无办理记录</td>
          </tr>
        </tbody>
      </table>
    </template>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { request } from '@/api/client'

type HistoryItem = {
  time: string
  action: string
  from: string | null
  to: string | null
  remark: string | null
}
type Entry = {
  id: number
  status: string
  next_action: string | null
  history: HistoryItem[]
  [field: string]: string | number | null | HistoryItem[]
}

const ENDPOINT = '/api/pumpstation'
const columns = ["泵站编号", "泵站名称", "服务区域", "装机台数", "设计流量", "上次检修日", "值守方式", "泵站状态"]
const actions = ["办理接管", "标记减量", "安排检修"]

const route = useRoute()
const entry = ref<Entry | null>(null)
const notFound = ref(false)
const errorMessage = ref('')
const busyAction = ref<string | null>(null)

function unavailableHint(action: string): string {
  if (!entry.value) return ''
  const status = String(entry.value.status)
  const statuses = ["待接管", "运行正常", "减量运行", "停运检修"]
  if (status === statuses[statuses.length - 1]) {
    return `泵站已办结（${status}），不能再办理任何动作`
  }
  return entry.value.next_action
    ? `动作越序或已办理：请先「${entry.value.next_action}」`
    : ''
}

async function runAction(action: string) {
  if (!entry.value || busyAction.value !== null) return
  errorMessage.value = ''
  busyAction.value = action
  try {
    const response = await request(`${ENDPOINT}/${entry.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    if (!response.ok) {
      throw new Error('泵站设施动作未生效，请稍后重试')
    }
    const result = await response.json()
    // HTTP 成功但业务规则拦下（重复/越序）时，服务端给出可读原因
    if (!result.ok) {
      errorMessage.value = result.message ?? '该动作当前不可办理'
      return
    }
    // 动作落库后重新拉取详情，保证与列表、概览同一口径
    await loadEntry()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '泵站设施操作失败'
  } finally {
    busyAction.value = null
  }
}

async function loadEntry() {
  const id = Number(route.params.id)
  const response = await request(`${ENDPOINT}/${id}`)
  if (response.status === 404) {
    notFound.value = true
    return
  }
  if (!response.ok) {
    throw new Error('泵站详情读取失败')
  }
  entry.value = await response.json()
}

onMounted(async () => {
  try {
    await loadEntry()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '泵站详情读取失败'
  }
})
</script>

<style scoped>
.btn:disabled {
  color: var(--muted);
  cursor: not-allowed;
}
</style>
