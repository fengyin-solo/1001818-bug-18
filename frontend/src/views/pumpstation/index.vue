<template>
  <section class="page" data-module="pumpstation">
    <header class="page-head">
      <div>
        <h2>泵站设施管理</h2>
        <p class="page-desc">维护泵站，围绕泵站编号、泵站名称、服务区域、装机台数做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记泵站</button>
        <button class="btn" type="button" @click="exportRows">导出泵站设施清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <RouterLink v-if="column === '泵站编号'" class="link" :to="`/pumpstation/${row.id}`">
              {{ row[column] ?? '—' }}
            </RouterLink>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :disabled="busyId === row.id || action !== row.next_action"
              :title="action !== row.next_action ? unavailableHint(row, action) : ''"
              @click="runAction(action, row)"
            >
              {{ busyId === row.id ? '办理中…' : action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无泵站设施数据，可先登记泵站</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条泵站设施记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { request } from '@/api/client'

type Row = {
  id: number
  status: string
  next_action: string | null
  history?: unknown[]
  [field: string]: string | number | null | unknown[] | undefined
}

const ENDPOINT = '/api/pumpstation'
const columns = ["泵站编号", "泵站名称", "服务区域", "装机台数", "设计流量", "上次检修日", "值守方式", "泵站状态"]
const actions = ["办理接管", "标记减量", "安排检修"]
const TERMINAL_STATUS = "停运检修"

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref([
  { label: "在运泵站", value: 0 },
  { label: "减量运行泵站", value: 0 },
  { label: "停运检修泵站", value: 0 },
  { label: "待接管泵站", value: 0 },
])
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
// 同一台泵站动作在途时锁定，重复点击只提交一次
const busyId = ref<number | null>(null)

function unavailableHint(row: Row, action: string): string {
  if (row.status === TERMINAL_STATUS) {
    return `泵站已办结（${row.status}），不能再办理任何动作`
  }
  if (row.next_action === null) return ''
  return action === row.next_action
    ? ''
    : `该动作已办理或越序，请先「${row.next_action}」`
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '泵站登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  if (busyId.value !== null || action !== row.next_action) return
  errorMessage.value = ''
  busyId.value = Number(row.id)
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    if (!response.ok) {
      throw new Error('泵站设施动作未生效，请稍后重试')
    }
    const result = await response.json()
    // HTTP 成功但被业务规则拦下（重复/越序/已办结）时，展示服务端说明的原因
    if (!result.ok) {
      errorMessage.value = result.message ?? '该动作当前不可办理'
      return
    }
    // 动作落到服务端后重新拉列表，状态、可办动作、统计与详情、概览保持同一口径
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '泵站设施操作失败'
  } finally {
    busyId.value = null
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    // 统计需要全量口径，与当前分页过滤条件分开取
    const [listResponse, allResponse] = await Promise.all([
      request(`${ENDPOINT}?${query}`),
      request(`${ENDPOINT}?size=200`),
    ])
    if (!listResponse.ok || !allResponse.ok) {
      throw new Error('泵站列表读取失败')
    }
    const payload = await listResponse.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length

    const all = await allResponse.json()
    const allRows: Row[] = all.items ?? []
    const countBy = (status: string) => allRows.filter((row) => row.status === status).length
    stats.value = [
      { label: "在运泵站", value: countBy('运行正常') },
      { label: "减量运行泵站", value: countBy('减量运行') },
      { label: "停运检修泵站", value: countBy('停运检修') },
      { label: "待接管泵站", value: countBy('待接管') },
    ]
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '泵站设施列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.link:disabled {
  color: var(--muted);
  cursor: not-allowed;
  text-decoration: none;
}
</style>
