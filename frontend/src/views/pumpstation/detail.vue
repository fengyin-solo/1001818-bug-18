<template>
  <section class="page" data-module="pumpstation-detail">
    <header class="page-head">
      <div>
        <h2>泵站设施详情</h2>
        <p class="page-desc">泵站编号 {{ entry?.['泵站编号'] ?? entryId }}：动作按既定顺序生效，历史记录只追加不覆盖。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/pumpstation">返回列表</RouterLink>
      </div>
    </header>

    <div v-if="notFound" class="data-table empty-state" style="padding: 24px;">
      {{ errorMessage || '泵站不存在或已归档' }}
    </div>

    <template v-else-if="entry">
      <div class="stat-row">
        <article class="stat-card">
          <span class="stat-label">当前状态</span>
          <strong class="stat-value">{{ entry.status }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">是否待办</span>
          <strong class="stat-value">{{ entry.pending ? '待处理' : '已处理' }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">工况</span>
          <strong class="stat-value">{{ entry.abnormal ? '异常工况' : '正常' }}</strong>
        </article>
      </div>

      <table class="data-table">
        <tbody>
          <tr v-for="column in columns" :key="column">
            <th style="width: 160px;">{{ column }}</th>
            <td>{{ entry[column] ?? '—' }}</td>
          </tr>
        </tbody>
      </table>

      <div class="page-head">
        <h3 style="font-size: 15px;">办理动作</h3>
      </div>
      <div class="row-actions" style="margin-bottom: 12px;">
        <template v-if="nextAction">
          <button
            class="btn primary"
            type="button"
            :disabled="submitting"
            @click="runAction(nextAction)"
          >
            {{ submitting ? '提交中…' : nextAction }}
          </button>
          <span class="muted-text">当前为「{{ entry.status }}」，仅可执行下一步动作，重复或越序提交会被服务端拦下。</span>
        </template>
        <span v-else class="muted-text">该泵站已到「{{ entry.status }}」终态，全部流程办结，无可用动作。</span>
      </div>
      <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
      <p v-if="successMessage" class="success-text">{{ successMessage }}</p>

      <div class="page-head">
        <h3 style="font-size: 15px;">历史记录</h3>
      </div>
      <table class="data-table">
        <thead>
          <tr><th>时间</th><th>动作</th><th>变更前</th><th>变更后</th></tr>
        </thead>
        <tbody>
          <tr v-for="(record, index) in history" :key="`${record.time}-${index}`">
            <td>{{ record.time }}</td>
            <td>{{ record.action }}</td>
            <td>{{ record.from || '—' }}</td>
            <td>{{ record.to }}</td>
          </tr>
          <tr v-if="!history.length">
            <td colspan="4" class="empty-state">暂无历史记录</td>
          </tr>
        </tbody>
      </table>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>
type HistoryRecord = { action: string; from: string; to: string; time: string }
type Entry = Row & { status?: string; pending?: boolean; abnormal?: boolean; history?: HistoryRecord[] }

const ENDPOINT = '/api/pumpstation'
const columns = ["泵站编号", "泵站名称", "服务区域", "装机台数", "设计流量", "上次检修日", "值守方式", "泵站状态"]
const nextActionByStatus: Record<string, string> = {
  '待接管': '办理接管',
  '运行正常': '标记减量',
  '减量运行': '安排检修',
}

const route = useRoute()
const entryId = String(route.params.id)
const entry = ref<Entry | null>(null)
const notFound = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const submitting = ref(false)

const history = computed<HistoryRecord[]>(() => entry.value?.history ?? [])
const nextAction = computed(() => nextActionByStatus[String(entry.value?.status ?? '')] ?? '')

async function loadDetail() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${entryId}`)
    if (response.status === 404) {
      notFound.value = true
      return
    }
    if (!response.ok) {
      throw new Error('泵站详情读取失败')
    }
    entry.value = await response.json()
    notFound.value = false
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '泵站详情读取失败'
  }
}

async function runAction(action: string) {
  if (submitting.value || !entry.value) {
    return
  }
  errorMessage.value = ''
  successMessage.value = ''
  submitting.value = true
  try {
    const response = await request(`${ENDPOINT}/${entry.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload || payload.ok === false) {
      throw new Error(payload?.message ?? '泵站设施动作未生效，请稍后重试')
    }
    // 动作落库后以服务端返回为准重拉详情，列表、概览共用同一份数据口径。
    await loadDetail()
    successMessage.value = payload.message ?? '动作已生效'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '泵站设施操作失败'
  } finally {
    submitting.value = false
  }
}

onMounted(loadDetail)
</script>
