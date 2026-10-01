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
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <template v-if="nextAction(row.status)">
              <button
                class="link"
                type="button"
                :disabled="submittingId === row.id"
                @click="runAction(nextAction(row.status), row)"
              >
                {{ submittingId === row.id ? '提交中…' : nextAction(row.status) }}
              </button>
            </template>
            <span v-else class="muted-text">已办结</span>
          </td>
          <td class="row-actions">
            <RouterLink class="link" :to="`/pumpstation/${row.id}`">查看详情</RouterLink>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无泵站设施数据，可先登记泵站</td>
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

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type HistoryRecord = { action: string; from: string; to: string; time: string }
type DetailRow = Row & { history?: HistoryRecord[] }

const ENDPOINT = '/api/pumpstation'
const columns = ["泵站编号", "泵站名称", "服务区域", "装机台数", "设计流量", "上次检修日", "值守方式", "泵站状态"]
// 状态顺序与后端口径保持一致：每个状态只有一个合法的下一步动作。
const nextActionByStatus: Record<string, string> = {
  '待接管': '办理接管',
  '运行正常': '标记减量',
  '减量运行': '安排检修',
}
const stats = ref([
  { label: '在运泵站', value: 0 },
  { label: '减量运行泵站', value: 0 },
  { label: '停运检修泵站', value: 0 },
])

const rows = ref<DetailRow[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
// 记录正在提交的行，同一台泵站的动作在返回前不能点第二次。
const submittingId = ref<number | null>(null)

function nextAction(status: unknown): string {
  return nextActionByStatus[String(status)] ?? ''
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
  if (submittingId.value !== null) {
    return
  }
  errorMessage.value = ''
  submittingId.value = Number(row.id)
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = await response.json().catch(() => null)
    // 业务是否被接受由服务端 ok 决定，被拦下（重复/越序）时原样展示服务端原因。
    if (!response.ok || !payload || payload.ok === false) {
      throw new Error(payload?.message ?? '泵站设施动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '泵站设施操作失败'
  } finally {
    submittingId.value = null
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    // 统计卡片要反映全量口径（不受筛选影响），单独取一页足够大的数据。
    const [listResponse, statsResponse] = await Promise.all([
      request(`${ENDPOINT}?${query}`),
      request(`${ENDPOINT}?page=1&size=200`),
    ])
    if (!listResponse.ok) {
      throw new Error('泵站列表读取失败')
    }
    const payload = await listResponse.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    if (statsResponse.ok) {
      const all = await statsResponse.json()
      const allRows: Row[] = all.items ?? []
      stats.value = [
        { label: '在运泵站', value: allRows.filter((item) => item['泵站状态'] === '运行正常').length },
        { label: '减量运行泵站', value: allRows.filter((item) => item['泵站状态'] === '减量运行').length },
        { label: '停运检修泵站', value: allRows.filter((item) => item['泵站状态'] === '停运检修').length },
      ]
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '泵站设施列表读取失败'
  }
}

onMounted(reload)
</script>
