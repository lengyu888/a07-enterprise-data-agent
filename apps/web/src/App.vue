<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

type ReadyPayload = { status: string; dependencies: { database: string; deepseek: string } }
type BootstrapPayload = { phase: string; next_milestone: string }
type CatalogSummary = { table_count: number; column_count: number; relation_count: number; total_rows: number; refreshed_at: string; dataset_max_business_date: string }
type CatalogTable = { id: number; schema_name: string; table_name: string; display_name: string; description: string; business_domain: string; row_count: number; column_count: number }
type CatalogColumn = { id: number; column_name: string; data_type: string; is_nullable: boolean; is_primary_key: boolean; description: string; sample_values: unknown[] }
type TableDetail = CatalogTable & { columns: CatalogColumn[] }
type Relation = { id: number; source_table: string; source_column: string; target_table: string; target_column: string; cardinality: string }
type Topic = { topic_code: string; topic_name: string; description: string; accent_color: string; metric_count: number; rule_count: number; object_count: number }
type Rule = { rule_code: string; topic_code: string; rule_name: string; rule_content: string }
type Synonym = { topic_code: string; canonical_term: string; synonym_term: string }
type Metric = { metric_code: string; topic_code: 'quality' | 'equipment' | 'production'; metric_name: string; description: string; formula: string; unit: string; grain: string; dimensions: string[]; mapped_tables: string[]; owner_name: string; version: string; status: 'draft' | 'published' | 'disabled' }
type AgentTrace = { node_name: string; display_name: string; status: string; duration_ms: number; summary: string; payload: Record<string, unknown> }
type AgentRun = {
  run_id: string; status: string; question: string; model: string; generation_mode: string; duration_ms: number
  time_range: { start: string; end: string; anchor: string }; plan: string[]
  evidence: { metric: { code: string; name: string; formula: string; version: string }; rule: string; rules: Array<Record<string, string>>; tables: string[]; relations: Array<{ source_table: string; source_column: string; target_table: string; target_column: string }>; items: Array<{ id: number; source_type: string; source_id: string; title: string; score: number; channels: string[] }>; retrieval: { strategy: string; top_k: number; channel_hits: Record<string, number>; context_reduction_pct: number } }
  sql: { text: string; validation: string; repair_count: number; referenced_tables: string[] }
  result: { columns: string[]; rows: Array<Record<string, string | number>>; row_count: number }
  chart: { type: string; title: string; x_field: string; y_field: string; unit: string; categories: string[]; series: Array<{ name: string; data: number[] }> }
  answer: string; trace: AgentTrace[]
}

type QualityBrief = {
  run_id: string; status: string; duration_ms: number
  period: { start: string; end: string; anchor: string; previous_month: string }
  assessment: {
    current_yield: number; previous_yield: number; yield_delta_pp: number; inspected_qty: number; unqualified_qty: number; status: string
    worst_process: { process_name: string; yield_rate: number; inspected_qty: number }
    top_defect: { defect_type: string; defect_count: number; defect_share: number; cumulative_share: number }
    vital_few: string[]
  }
  brief: { headline: string; summary: string; risks: string[]; actions: string[]; generation_mode: string }
  charts: {
    process: Array<{ process_name: string; yield_rate: number; inspected_qty: number }>
    pareto: Array<{ defect_type: string; defect_count: number; defect_share: number; cumulative_share: number }>
    trend: Array<{ business_date: string; yield_rate: number }>
  }
  evidence: Array<{ question: string; metric: string; metric_code: string; formula: string; tables: string[]; top_sources: string[] }>
  trace: AgentTrace[]
}

type EquipmentDiagnosis = {
  run_id: string; status: string; duration_ms: number
  period: { training: string; scoring: string; anchor: string }
  recipe: { code: string; name: string; algorithm: string; version: string; features: string[]; parameters: Record<string, number>; feature_sql: string; explanation_rule: string }
  assessment: { top_equipment: EquipmentRank; top_anomaly_date: string; top_anomaly_score: number; anomaly_rate_pct: number; status: string }
  ranking: EquipmentRank[]
  timeline: Array<{ business_date: string; anomaly_score: number; is_anomaly: boolean; downtime_minutes: number }>
  deviations: Array<{ feature: string; label: string; current: number; baseline_median: number; robust_deviation: number; change_pct: number | null }>
  reason_distribution: Array<{ event_reason: string; event_count: number; duration_minutes: number }>
  brief: { headline: string; summary: string; risks: string[]; actions: string[]; generation_mode: string }
  evidence: { metric: string; formula: string; tables: string[]; rules: string[]; retrieval: { strategy: string; context_reduction_pct: number }; sources: string[] }
  trace: AgentTrace[]
}
type EquipmentRank = { equipment_id: string; equipment_name: string; equipment_type: string; line_name: string; anomaly_days: number; max_anomaly_score: number; total_downtime_minutes: number; max_single_duration: number; alarm_count: number }

const activeView = ref<'overview' | 'catalog' | 'knowledge' | 'quality' | 'equipment' | 'agent'>('overview')
const ready = ref<ReadyPayload | null>(null)
const bootstrap = ref<BootstrapPayload | null>(null)
const summary = ref<CatalogSummary | null>(null)
const tables = ref<CatalogTable[]>([])
const relations = ref<Relation[]>([])
const tableDetail = ref<TableDetail | null>(null)
const topics = ref<Topic[]>([])
const rules = ref<Rule[]>([])
const synonyms = ref<Synonym[]>([])
const metrics = ref<Metric[]>([])
const selectedDomain = ref('全部')
const selectedTopic = ref('all')
const loading = ref(true)
const refreshing = ref(false)
const error = ref('')
const metricEditorOpen = ref(false)
const editingMetric = ref(false)
const dimensionText = ref('')
const mappedTableText = ref('')
const agentQuestion = ref('分析本月各工序良率，找出良率最低的工序')
const agentRunning = ref(false)
const agentError = ref('')
const agentResult = ref<AgentRun | null>(null)
const qualityBrief = ref<QualityBrief | null>(null)
const qualityBriefRunning = ref(false)
const qualityBriefError = ref('')
const equipmentDiagnosis = ref<EquipmentDiagnosis | null>(null)
const equipmentRunning = ref(false)
const equipmentError = ref('')
const agentExamples = [
  { scene: '质量分析', code: 'QUALITY', question: '分析本月各工序良率，找出良率最低的工序' },
  { scene: '设备停机', code: 'EQUIPMENT', question: '本月各设备非计划停机时长排名' },
  { scene: '生产达成', code: 'PRODUCTION', question: '本月各产线计划达成率' },
]
const metricForm = reactive<Metric>({ metric_code: '', topic_code: 'quality', metric_name: '', description: '', formula: '', unit: '%', grain: '日期×产线', dimensions: [], mapped_tables: [], owner_name: '比赛项目组', version: '1.0', status: 'draft' })

const systemReady = computed(() => ready.value?.status === 'ready')
const domains = computed(() => ['全部', ...new Set(tables.value.map((item) => item.business_domain))])
const visibleTables = computed(() => selectedDomain.value === '全部' ? tables.value : tables.value.filter((item) => item.business_domain === selectedDomain.value))
const visibleMetrics = computed(() => selectedTopic.value === 'all' ? metrics.value : metrics.value.filter((item) => item.topic_code === selectedTopic.value))
const graphTables = computed(() => tables.value.filter((table) => relations.value.some((relation) => relation.source_table === table.table_name || relation.target_table === table.table_name)))
const graphHeight = computed(() => {
  const factCount = graphTables.value.filter((table) => table.table_name.startsWith('fact_')).length
  const dimensionCount = graphTables.value.filter((table) => table.table_name.startsWith('dim_')).length
  return Math.max(470, Math.max(factCount, dimensionCount) * 74 + 90)
})

function graphPosition(tableName: string) {
  const isDimension = tableName.startsWith('dim_')
  const group = graphTables.value.filter((table) => table.table_name.startsWith(isDimension ? 'dim_' : 'fact_'))
  const index = Math.max(0, group.findIndex((item) => item.table_name === tableName))
  return { x: isDimension ? 540 : 42, y: 32 + index * 74 }
}
function formatNumber(value = 0) { return new Intl.NumberFormat('zh-CN').format(value) }
function formatDate(value?: string) { return value ? new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value)) : '—' }
function formatDuration(value = 0) { return value >= 1000 ? `${(value / 1000).toFixed(1)} s` : `${value} ms` }
const chartValues = computed(() => agentResult.value?.chart.series[0]?.data ?? [])
const chartBaseline = computed(() => {
  const values = chartValues.value
  if (!values.length) return 0
  const minimum = Math.min(...values)
  return agentResult.value?.chart.unit === '%' && minimum > 80 ? Math.floor(minimum - 2) : 0
})
const chartCeiling = computed(() => Math.max(...chartValues.value, chartBaseline.value + 1))
function chartHeight(value: number) { return `${Math.max(8, Math.min(100, 100 * (value - chartBaseline.value) / (chartCeiling.value - chartBaseline.value)))}%` }
function lineX(index: number) { return chartValues.value.length <= 1 ? 400 : 55 + index * 690 / (chartValues.value.length - 1) }
function lineY(value: number) { return 235 - 190 * (value - chartBaseline.value) / (chartCeiling.value - chartBaseline.value) }
const linePoints = computed(() => chartValues.value.map((value, index) => `${lineX(index)},${lineY(value)}`).join(' '))
const paretoLinePoints = computed(() => (agentResult.value?.chart.series[1]?.data ?? []).map((value, index, values) => `${values.length <= 1 ? 400 : 70 + index * 660 / (values.length - 1)},${245 - 2 * value}`).join(' '))
const qualityTrendPoints = computed(() => {
  const values = qualityBrief.value?.charts.trend.map((item) => item.yield_rate) ?? []
  if (!values.length) return ''
  const min = Math.floor(Math.min(...values) - 0.5); const max = Math.ceil(Math.max(...values) + 0.5)
  return values.map((value, index) => `${values.length <= 1 ? 400 : 45 + index * 710 / (values.length - 1)},${220 - 165 * (value - min) / Math.max(max - min, 1)}`).join(' ')
})
const qualityParetoMax = computed(() => Math.max(...(qualityBrief.value?.charts.pareto.map((item) => item.defect_count) ?? [1])))
const equipmentTimelinePoints = computed(() => (equipmentDiagnosis.value?.timeline ?? []).map((item, index, rows) => `${rows.length <= 1 ? 400 : 45 + index * 710 / (rows.length - 1)},${220 - 1.65 * item.anomaly_score}`).join(' '))
const equipmentDeviationMax = computed(() => Math.max(...(equipmentDiagnosis.value?.deviations.map((item) => Math.abs(item.robust_deviation)) ?? [1])))
const equipmentReasonMax = computed(() => Math.max(...(equipmentDiagnosis.value?.reason_distribution.map((item) => item.duration_minutes) ?? [1])))
function equipmentPointX(index: number) { const count = equipmentDiagnosis.value?.timeline.length ?? 1; return count <= 1 ? 400 : 45 + index * 710 / (count - 1) }
function equipmentPointY(score: number) { return 220 - 1.65 * score }
function columnLabel(column: string) { return ({ process_name: '工序', product_name: '产品', equipment_name: '设备', event_reason: '原因', line_name: '产线', business_date: '日期', business_month: '月份', defect_type: '缺陷类型', yield_rate: '良率', defect_rate: '不良率', defect_count: '缺陷数量', cumulative_share: '累计占比', alarm_count: '报警次数', downtime_count: '停机次数', downtime_minutes: '停机时长', final_output: '完工产量', plan_attainment: '计划达成率', inspected_qty: '检验数量' } as Record<string, string>)[column] || column }
function formatCell(value: string | number, column: string) { return typeof value === 'number' ? `${formatNumber(value)}${['yield_rate', 'defect_rate', 'plan_attainment', 'cumulative_share'].includes(column) ? '%' : ''}` : value }
async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options)
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as { detail?: string | { message?: string } }
    const detail = typeof payload.detail === 'string' ? payload.detail : payload.detail?.message
    throw new Error(detail || `请求失败：${response.status}`)
  }
  return response.status === 204 ? (undefined as T) : await response.json() as T
}

async function loadWorkspace() {
  loading.value = true; error.value = ''
  try {
    const [r, b, s, t, rel, knowledge, m] = await Promise.all([
      fetchJson<ReadyPayload>('/api/ready'), fetchJson<BootstrapPayload>('/api/v1/system/bootstrap'),
      fetchJson<CatalogSummary>('/api/v1/catalog/summary'), fetchJson<CatalogTable[]>('/api/v1/catalog/tables'),
      fetchJson<Relation[]>('/api/v1/catalog/relations'), fetchJson<{ topics: Topic[]; rules: Rule[]; synonyms: Synonym[] }>('/api/v1/knowledge/overview'),
      fetchJson<Metric[]>('/api/v1/knowledge/metrics'),
    ])
    ready.value = r; bootstrap.value = b; summary.value = s; tables.value = t; relations.value = rel
    topics.value = knowledge.topics; rules.value = knowledge.rules; synonyms.value = knowledge.synonyms; metrics.value = m
    if (!tableDetail.value && t.length) await selectTable(t[0].id)
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '无法读取数据底座' }
  finally { loading.value = false }
}
async function refreshCatalog() {
  refreshing.value = true
  try { await fetchJson('/api/v1/catalog/refresh', { method: 'POST' }); tableDetail.value = null; await loadWorkspace() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '目录刷新失败' }
  finally { refreshing.value = false }
}
async function selectTable(tableId: number) { tableDetail.value = await fetchJson<TableDetail>(`/api/v1/catalog/tables/${tableId}`) }
function newMetric() {
  Object.assign(metricForm, { metric_code: '', topic_code: 'quality', metric_name: '', description: '', formula: '', unit: '%', grain: '日期×产线', dimensions: [], mapped_tables: [], owner_name: '比赛项目组', version: '1.0', status: 'draft' })
  dimensionText.value = ''; mappedTableText.value = ''; editingMetric.value = false; metricEditorOpen.value = true
}
function editMetric(metric: Metric) {
  Object.assign(metricForm, metric); dimensionText.value = metric.dimensions.join('、'); mappedTableText.value = metric.mapped_tables.join('、')
  editingMetric.value = true; metricEditorOpen.value = true
}
async function saveMetric() {
  metricForm.dimensions = dimensionText.value.split(/[、,，]/).map((item) => item.trim()).filter(Boolean)
  metricForm.mapped_tables = mappedTableText.value.split(/[、,，]/).map((item) => item.trim()).filter(Boolean)
  const path = editingMetric.value ? `/api/v1/knowledge/metrics/${metricForm.metric_code}` : '/api/v1/knowledge/metrics'
  await fetchJson(path, { method: editingMetric.value ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(metricForm) })
  metricEditorOpen.value = false; metrics.value = await fetchJson<Metric[]>('/api/v1/knowledge/metrics')
}
async function runAgent() {
  if (agentRunning.value || !agentQuestion.value.trim()) return
  agentRunning.value = true; agentError.value = ''; agentResult.value = null
  try {
    agentResult.value = await fetchJson<AgentRun>('/api/v1/agent/runs', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: agentQuestion.value.trim() }),
    })
  } catch (cause) { agentError.value = cause instanceof Error ? cause.message : 'Agent 执行失败' }
  finally { agentRunning.value = false }
}
async function generateQualityBrief() {
  if (qualityBriefRunning.value) return
  qualityBriefRunning.value = true; qualityBriefError.value = ''
  try { qualityBrief.value = await fetchJson<QualityBrief>('/api/v1/agent/quality/brief', { method: 'POST' }) }
  catch (cause) { qualityBriefError.value = cause instanceof Error ? cause.message : '质量简报生成失败' }
  finally { qualityBriefRunning.value = false }
}
function openQualityQuestion(question: string) {
  agentQuestion.value = question; agentResult.value = null; agentError.value = ''; activeView.value = 'agent'
}
async function generateEquipmentDiagnosis() {
  if (equipmentRunning.value) return
  equipmentRunning.value = true; equipmentError.value = ''
  try { equipmentDiagnosis.value = await fetchJson<EquipmentDiagnosis>('/api/v1/agent/equipment/diagnosis', { method: 'POST' }) }
  catch (cause) { equipmentError.value = cause instanceof Error ? cause.message : '设备异常诊断失败' }
  finally { equipmentRunning.value = false }
}
function openEquipmentQuestion(question: string) {
  agentQuestion.value = question; agentResult.value = null; agentError.value = ''; activeView.value = 'agent'
}
onMounted(loadWorkspace)
</script>

<template>
  <main class="shell">
    <div class="blueprint" aria-hidden="true"></div>
    <header class="masthead">
      <div class="brand-lockup"><div class="mark">A<span>07</span></div><div><p class="eyebrow">MANUFACTURING INTELLIGENCE / CONTEST BUILD</p><h1>企业数据底座 <em>智能问析 Agent</em></h1></div></div>
      <div class="phase-stamp"><span>BUILD PHASE</span><strong>{{ bootstrap?.phase ?? '—' }}</strong></div>
    </header>
    <nav class="view-nav" aria-label="主功能导航">
      <button :class="{ active: activeView === 'overview' }" @click="activeView = 'overview'">总览 <span>01</span></button>
      <button :class="{ active: activeView === 'catalog' }" @click="activeView = 'catalog'">数据目录 <span>02</span></button>
      <button :class="{ active: activeView === 'knowledge' }" @click="activeView = 'knowledge'">业务知识 <span>03</span></button>
      <button :class="{ active: activeView === 'quality' }" @click="activeView = 'quality'">质量驾驶舱 <span>04</span></button>
      <button :class="{ active: activeView === 'equipment' }" @click="activeView = 'equipment'">设备诊断 <span>05</span></button>
      <button :class="{ active: activeView === 'agent' }" @click="activeView = 'agent'">智能问析 <span>06</span></button>
      <div class="system-pill" :class="{ ready: systemReady }"><i></i>{{ systemReady ? 'SYSTEM READY' : 'CONNECTING' }}</div>
    </nav>
    <div v-if="error" class="error-banner">{{ error }} <button @click="loadWorkspace">重试</button></div>
    <div v-if="loading" class="loading-screen"><i></i><span>正在扫描制造数据资产…</span></div>

    <template v-else>
      <section v-if="activeView === 'overview'" class="overview-view">
        <div class="hero-grid">
          <article class="hero-copy"><p class="section-code">PHASE 05 / EQUIPMENT ANOMALY SPECIALIZATION</p><h2>在停机之前<br />发现<span>行为偏离</span></h2><p>审核 Recipe 将日粒度特征 SQL、Isolation Forest 与稳健偏离解释连成可复现算法链，再由 DeepSeek 形成有边界的设备诊断。</p><button class="primary-action" @click="activeView = 'equipment'">打开设备诊断 <b>→</b></button></article>
          <article class="date-card"><span>DATASET ANCHOR</span><strong>{{ summary?.dataset_max_business_date }}</strong><p>所有“本月 / 最近 30 天”等相对时间均以此业务日期为准。</p></article>
        </div>
        <div class="stat-strip">
          <div><small>TABLES</small><strong>{{ summary?.table_count }}</strong><span>9 主表 + 1 留出表</span></div><div><small>COLUMNS</small><strong>{{ summary?.column_count }}</strong><span>含注释与脱敏样例</span></div>
          <div><small>RELATIONS</small><strong>{{ summary?.relation_count }}</strong><span>真实外键关系</span></div><div><small>ROWS</small><strong>{{ formatNumber(summary?.total_rows) }}</strong><span>可解释演示记录</span></div>
        </div>
        <div class="topic-grid">
          <article v-for="(topic, index) in topics" :key="topic.topic_code" :style="{ '--topic': topic.accent_color }"><div class="topic-number">0{{ index + 1 }}</div><span>{{ topic.topic_code.toUpperCase() }}</span><h3>{{ topic.topic_name }}</h3><p>{{ topic.description }}</p><footer><b>{{ topic.metric_count }}</b> 指标 · <b>{{ topic.rule_count }}</b> 强规则 · <b>{{ topic.object_count }}</b> 对象</footer></article>
        </div>
        <section class="next-band"><span>NEXT / PHASE 04</span><h3>{{ bootstrap?.next_milestone }}</h3><p>混合 RAG → DeepSeek 规划 → Text-to-SQL → 安全执行/修复 → 动态图表 → 有据结论</p><div><i></i></div></section>
      </section>

      <section v-if="activeView === 'catalog'" class="catalog-view">
        <header class="section-header"><div><p class="section-code">LIVE POSTGRESQL CATALOG</p><h2>数据资源目录</h2></div><div class="header-actions"><span>最近扫描 {{ formatDate(summary?.refreshed_at) }}</span><button @click="refreshCatalog" :disabled="refreshing">{{ refreshing ? '扫描中…' : '刷新元数据' }}</button></div></header>
        <div class="filter-row"><button v-for="domain in domains" :key="domain" :class="{ active: selectedDomain === domain }" @click="selectedDomain = domain">{{ domain }}</button></div>
        <div class="catalog-layout">
          <aside class="table-list"><button v-for="table in visibleTables" :key="table.id" :class="{ active: tableDetail?.id === table.id }" @click="selectTable(table.id)"><span>{{ table.business_domain }}</span><strong>{{ table.display_name }}</strong><code>{{ table.schema_name }}.{{ table.table_name }}</code><small>{{ table.column_count }} 字段 · {{ formatNumber(table.row_count) }} 行</small></button></aside>
          <article v-if="tableDetail" class="table-inspector">
            <header><div><span>TABLE / {{ tableDetail.business_domain }}</span><h3>{{ tableDetail.display_name }}</h3><code>{{ tableDetail.schema_name }}.{{ tableDetail.table_name }}</code></div><b>{{ formatNumber(tableDetail.row_count) }}<small>ROWS</small></b></header>
            <p class="table-description">{{ tableDetail.description }}</p>
            <div class="column-table"><div class="column-head"><span>字段 / 类型</span><span>业务说明</span><span>样例值</span></div><div v-for="column in tableDetail.columns" :key="column.id" class="column-row"><span><code>{{ column.column_name }}</code><small>{{ column.data_type }} <i v-if="column.is_primary_key">PK</i></small></span><span>{{ column.description || '—' }}</span><span class="samples"><kbd v-for="sample in column.sample_values" :key="String(sample)">{{ sample }}</kbd></span></div></div>
          </article>
        </div>
        <section class="relation-section"><div class="relation-copy"><p class="section-code">VERIFIED JOIN PATHS</p><h3>真实关系图</h3><p>仅展示数据库外键，不允许模型猜测连接键。事实表沿多对一关系连接到维表和上游事实。</p><strong>{{ relations.length }}<small> VERIFIED EDGES</small></strong></div><div class="relation-canvas"><svg :viewBox="`0 0 760 ${graphHeight}`" role="img" aria-label="数据表关系图"><defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" /></marker></defs><line v-for="relation in relations" :key="relation.id" :x1="graphPosition(relation.source_table).x + 176" :y1="graphPosition(relation.source_table).y + 22" :x2="graphPosition(relation.target_table).x" :y2="graphPosition(relation.target_table).y + 22" marker-end="url(#arrow)" /><g v-for="table in graphTables" :key="table.id" :transform="`translate(${graphPosition(table.table_name).x} ${graphPosition(table.table_name).y})`"><rect width="176" height="44" rx="2" /><text x="12" y="18">{{ table.display_name }}</text><text class="code" x="12" y="34">{{ table.table_name }}</text></g></svg></div></section>
      </section>

      <section v-if="activeView === 'knowledge'" class="knowledge-view">
        <header class="section-header"><div><p class="section-code">BUSINESS SEMANTIC LAYER</p><h2>业务知识管理</h2></div><button class="primary-action compact" @click="newMetric">新增指标 <b>＋</b></button></header>
        <div class="topic-tabs"><button :class="{ active: selectedTopic === 'all' }" @click="selectedTopic = 'all'">全部</button><button v-for="topic in topics" :key="topic.topic_code" :class="{ active: selectedTopic === topic.topic_code }" @click="selectedTopic = topic.topic_code">{{ topic.topic_name }}</button></div>
        <div class="knowledge-layout"><div class="metric-list"><article v-for="metric in visibleMetrics" :key="metric.metric_code" @click="editMetric(metric)"><header><span>{{ topics.find((item) => item.topic_code === metric.topic_code)?.topic_name }}</span><i :class="metric.status">{{ metric.status }}</i></header><h3>{{ metric.metric_name }} <small>{{ metric.unit }}</small></h3><p>{{ metric.description }}</p><code>{{ metric.formula }}</code><footer><span>粒度：{{ metric.grain }}</span><span>v{{ metric.version }} · {{ metric.owner_name }}</span></footer></article></div><aside class="rule-stack"><div><p class="section-code">NON-NEGOTIABLE</p><h3>Agent 强规则</h3></div><article v-for="rule in rules" :key="rule.rule_code"><span>{{ rule.topic_code }}</span><strong>{{ rule.rule_name }}</strong><p>{{ rule.rule_content }}</p></article><div class="synonym-cloud"><p class="section-code">SYNONYMS</p><span v-for="item in synonyms" :key="`${item.canonical_term}-${item.synonym_term}`">{{ item.synonym_term }} → {{ item.canonical_term }}</span></div></aside></div>
      </section>

      <section v-if="activeView === 'quality'" class="quality-view">
        <header class="quality-hero">
          <div class="quality-hero-copy">
            <p class="section-code">PHASE 04 / QUALITY INTELLIGENCE ROOM</p>
            <h2>质量，不止一个<span>良率</span></h2>
            <p>LangGraph 将良率环比、工序短板、缺陷 Pareto 和每日趋势编排成同一份有据简报。所有数据截至 <b>2025-12-29</b>，不把相关性包装成根因。</p>
            <div class="quality-actions">
              <button class="quality-generate" :disabled="qualityBriefRunning" @click="generateQualityBrief">
                <span v-if="qualityBriefRunning" class="button-spinner"></span>
                {{ qualityBriefRunning ? '正在编排质量简报' : qualityBrief ? '重新生成质量简报' : '生成本月质量简报' }} <b>↗</b>
              </button>
              <small>RAG × 3 · READ-ONLY SQL × 4 · DEEPSEEK BRIEF</small>
            </div>
          </div>
          <div class="quality-seal" aria-hidden="true"><small>QUALITY</small><strong>04</strong><span>DEC / 2025</span></div>
        </header>

        <div class="quality-question-strip">
          <span>下钻问析</span>
          <button @click="openQualityQuestion('本月缺陷类型 Pareto 分析')"><b>01</b> 缺陷 Pareto <i>→</i></button>
          <button @click="openQualityQuestion('最近30天每日良率趋势')"><b>02</b> 每日良率趋势 <i>→</i></button>
          <button @click="openQualityQuestion('对比本月与上月总体良率')"><b>03</b> 月度环比 <i>→</i></button>
        </div>

        <div v-if="qualityBriefError" class="agent-error"><strong>质量简报未完成</strong><p>{{ qualityBriefError }}</p><button @click="generateQualityBrief">重新生成</button></div>
        <div v-if="qualityBriefRunning" class="quality-loading">
          <div class="quality-loader"><i></i><i></i><i></i><i></i></div>
          <div><span>LANGGRAPH QUALITY BRIEF</span><h3>正在汇集质量证据与真实指标</h3><p>检索三组 EvidenceBundle，执行四组只读聚合，再由 DeepSeek 形成管理层简报。</p></div>
        </div>
        <section v-else-if="!qualityBrief" class="quality-empty">
          <div class="empty-figure"><span>Q</span><i></i></div>
          <div><p class="section-code">READY TO COMPOSE</p><h3>一键生成可演示的质量分析闭环</h3><p>不是静态仪表盘。点击后现场运行 LangGraph、RAG、PostgreSQL 与 DeepSeek，并展示完整轨迹。</p></div>
        </section>

        <template v-if="qualityBrief && !qualityBriefRunning">
          <section class="quality-kpis">
            <article class="kpi-primary"><span>本月总体良率</span><strong>{{ qualityBrief.assessment.current_yield }}<small>%</small></strong><p :class="qualityBrief.assessment.yield_delta_pp < 0 ? 'down' : 'up'">{{ qualityBrief.assessment.yield_delta_pp > 0 ? '+' : '' }}{{ qualityBrief.assessment.yield_delta_pp }} pp <i>环比</i></p></article>
            <article><span>检验数量</span><strong>{{ formatNumber(qualityBrief.assessment.inspected_qty) }}</strong><small>件 / 12.01—12.29</small></article>
            <article><span>最低良率工序</span><strong>{{ qualityBrief.assessment.worst_process.process_name }}</strong><small>{{ qualityBrief.assessment.worst_process.yield_rate }}% · {{ formatNumber(qualityBrief.assessment.worst_process.inspected_qty) }} 件检验</small></article>
            <article class="kpi-alert"><span>首要缺陷</span><strong>{{ qualityBrief.assessment.top_defect.defect_type }}</strong><small>占全部缺陷 {{ qualityBrief.assessment.top_defect.defect_share }}%</small></article>
          </section>

          <div class="quality-chart-grid">
            <section class="quality-panel pareto-panel">
              <header><div><p class="section-code">DEFECT PARETO / 80-20</p><h3>关键缺陷贡献</h3></div><span>{{ qualityBrief.assessment.vital_few.length }} VITAL FEW</span></header>
              <div class="quality-pareto" role="img" aria-label="缺陷 Pareto 图">
                <div v-for="item in qualityBrief.charts.pareto" :key="item.defect_type" class="pareto-item">
                  <div><span>{{ item.defect_type }}</span><b>{{ formatNumber(item.defect_count) }}</b></div>
                  <i><em :style="{ width: `${100 * item.defect_count / qualityParetoMax}%` }"></em></i>
                  <small>{{ item.defect_share }}% / 累计 {{ item.cumulative_share }}%</small>
                </div>
              </div>
              <footer>累计占比达到 80% 前：<b>{{ qualityBrief.assessment.vital_few.join('、') }}</b></footer>
            </section>

            <section class="quality-panel trend-panel">
              <header><div><p class="section-code">30-DAY YIELD SIGNAL</p><h3>每日良率走势</h3></div><span>30 POINTS</span></header>
              <div class="quality-trend">
                <svg viewBox="0 0 800 260" preserveAspectRatio="none" role="img" aria-label="最近30天每日良率趋势">
                  <line v-for="y in [55, 137, 220]" :key="y" x1="45" :y1="y" x2="755" :y2="y" />
                  <polyline :points="qualityTrendPoints" />
                  <circle v-if="qualityBrief.charts.trend.length" cx="755" :cy="qualityTrendPoints.split(' ').at(-1)?.split(',')[1]" r="7" />
                </svg>
                <div class="trend-axis"><span>{{ qualityBrief.charts.trend[0]?.business_date.slice(5) }}</span><span>{{ qualityBrief.charts.trend.at(-1)?.business_date.slice(5) }}</span></div>
              </div>
              <div class="process-pulse"><span v-for="item in qualityBrief.charts.process" :key="item.process_name"><b>{{ item.yield_rate }}%</b>{{ item.process_name }}</span></div>
            </section>
          </div>

          <section class="quality-brief-card">
            <header><div><p class="section-code">DEEPSEEK MANAGEMENT BRIEF</p><h3>{{ qualityBrief.brief.headline }}</h3></div><span>{{ qualityBrief.brief.generation_mode.toUpperCase() }}</span></header>
            <p class="brief-summary">{{ qualityBrief.brief.summary }}</p>
            <div class="brief-columns">
              <div><span>风险观察</span><ol><li v-for="risk in qualityBrief.brief.risks" :key="risk">{{ risk }}</li></ol></div>
              <div><span>建议动作</span><ol><li v-for="action in qualityBrief.brief.actions" :key="action">{{ action }}</li></ol></div>
            </div>
            <footer><code>{{ qualityBrief.run_id }}</code><span>{{ formatDuration(qualityBrief.duration_ms) }} · 数据边界 {{ qualityBrief.period.start }}—{{ qualityBrief.period.end }}</span></footer>
          </section>

          <section class="quality-proof-grid">
            <div class="quality-proof"><p class="section-code">EVIDENCE PACKS</p><article v-for="item in qualityBrief.evidence" :key="item.metric_code"><b>{{ item.metric }}</b><code>{{ item.formula }}</code><span>{{ item.tables.join(' + ') }}</span></article></div>
            <div class="quality-proof"><p class="section-code">LANGGRAPH TRACE</p><article v-for="(step, index) in qualityBrief.trace" :key="step.node_name"><b>0{{ index + 1 }} · {{ step.display_name }}</b><span>{{ step.summary }}</span><small>{{ formatDuration(step.duration_ms) }}</small></article></div>
          </section>
        </template>
      </section>

      <section v-if="activeView === 'equipment'" class="equipment-view">
        <header class="equipment-hero">
          <div class="equipment-intro">
            <p class="section-code">PHASE 05 / MACHINE BEHAVIOR DOSSIER</p>
            <h2>别等停机，<br /><span>先看偏离</span></h2>
            <p>用 61 天历史设备日作为基线，对 29 天评分窗口进行无监督异常识别。算法说明“哪里不一样”，DeepSeek 帮助组织核查路径，但不替代根因分析。</p>
            <button class="equipment-run" :disabled="equipmentRunning" @click="generateEquipmentDiagnosis"><span v-if="equipmentRunning" class="button-spinner"></span>{{ equipmentRunning ? '正在执行异常 Recipe' : equipmentDiagnosis ? '重新运行设备诊断' : '运行设备异常诊断' }} <b>↗</b></button>
          </div>
          <div class="machine-poster" aria-hidden="true">
            <span>IF</span><svg viewBox="0 0 280 90"><polyline points="0,45 35,44 48,18 63,72 78,43 130,44 146,36 159,50 176,43 230,44 242,8 254,80 268,44 280,45" /></svg>
            <small>ISOLATION FOREST<br />DAILY FEATURE RECIPE</small>
          </div>
        </header>

        <div class="equipment-query-strip"><span>SQL 下钻</span><button @click="openEquipmentQuestion('本月各设备报警次数排名')"><b>01</b> 报警频次 <i>→</i></button><button @click="openEquipmentQuestion('本月各设备非计划停机次数排名')"><b>02</b> 停机次数 <i>→</i></button><button @click="openEquipmentQuestion('本月各设备非计划停机时长排名')"><b>03</b> 停机时长 <i>→</i></button></div>
        <div v-if="equipmentError" class="agent-error"><strong>设备诊断未完成</strong><p>{{ equipmentError }}</p><button @click="generateEquipmentDiagnosis">重新运行</button></div>
        <div v-if="equipmentRunning" class="equipment-loading"><div class="radar-loader"><i></i><b></b><span></span></div><div><p class="section-code">RECIPE IS RUNNING</p><h3>正在训练基线并扫描设备日偏离</h3><p>Feature SQL → StandardScaler → Isolation Forest → Median/IQR Explanation → DeepSeek Brief</p></div></div>
        <section v-else-if="!equipmentDiagnosis" class="equipment-empty"><div class="machine-index"><b>E08</b><span>KNOWN SIGNAL / HIDDEN FROM MODEL</span></div><div><p class="section-code">AUDITABLE ANOMALY WORKFLOW</p><h3>一次运行，展示从特征到解释的完整算法证据</h3><p>系统不会读取预设答案。E08 的异常模式埋在设备事件数据中，需由固定 Recipe 现场识别。</p></div></section>

        <template v-if="equipmentDiagnosis && !equipmentRunning">
          <section class="equipment-alert-band">
            <div class="alert-identity"><span>TOP ANOMALY</span><strong>{{ equipmentDiagnosis.assessment.top_equipment.equipment_id }}</strong><h3>{{ equipmentDiagnosis.assessment.top_equipment.equipment_name }}</h3><p>{{ equipmentDiagnosis.assessment.top_equipment.line_name }}</p></div>
            <div><span>异常日</span><strong>{{ equipmentDiagnosis.assessment.top_equipment.anomaly_days }}<small>/29</small></strong><p>{{ equipmentDiagnosis.assessment.anomaly_rate_pct }}% 评分窗口</p></div>
            <div><span>最大单次停机</span><strong>{{ equipmentDiagnosis.assessment.top_equipment.max_single_duration }}<small> min</small></strong><p>{{ equipmentDiagnosis.assessment.top_anomaly_date }}</p></div>
            <div><span>模型评分峰值</span><strong>{{ equipmentDiagnosis.assessment.top_anomaly_score }}</strong><p>0—100 相对尺度</p></div>
            <div class="model-ticket"><span>MODEL RECIPE</span><b>{{ equipmentDiagnosis.recipe.algorithm }}</b><code>v{{ equipmentDiagnosis.recipe.version }} · seed {{ equipmentDiagnosis.recipe.parameters.random_state }}</code></div>
          </section>

          <div class="equipment-main-grid">
            <section class="equipment-panel fleet-panel"><header><div><p class="section-code">FLEET ANOMALY RANK</p><h3>九台设备扫描</h3></div><span>29 DAYS</span></header><div class="fleet-list"><article v-for="(item, index) in equipmentDiagnosis.ranking" :key="item.equipment_id" :class="{ hot: index === 0 }"><b>{{ String(index + 1).padStart(2, '0') }}</b><div><strong>{{ item.equipment_name }}</strong><span>{{ item.equipment_id }} · {{ item.equipment_type }}</span></div><i><em :style="{ width: `${item.max_anomaly_score}%` }"></em></i><small>{{ item.anomaly_days }} 异常日</small></article></div></section>
            <section class="equipment-panel signal-panel"><header><div><p class="section-code">ANOMALY SIGNAL / TOP MACHINE</p><h3>{{ equipmentDiagnosis.assessment.top_equipment.equipment_name }} 时间信号</h3></div><span>IF SCORE</span></header><div class="signal-chart"><svg viewBox="0 0 800 260" preserveAspectRatio="none"><line v-for="y in [55, 137, 220]" :key="y" x1="45" :y1="y" x2="755" :y2="y" /><polyline :points="equipmentTimelinePoints" /><g v-for="(item, index) in equipmentDiagnosis.timeline" :key="item.business_date"><circle v-if="item.is_anomaly" :cx="equipmentPointX(index)" :cy="equipmentPointY(item.anomaly_score)" r="6" /></g></svg><div><span>{{ equipmentDiagnosis.timeline[0]?.business_date.slice(5) }}</span><b>异常阈值由训练基线确定</b><span>{{ equipmentDiagnosis.timeline.at(-1)?.business_date.slice(5) }}</span></div></div><footer><span>停机累计 <b>{{ formatNumber(equipmentDiagnosis.assessment.top_equipment.total_downtime_minutes) }} min</b></span><span>报警事件 <b>{{ equipmentDiagnosis.assessment.top_equipment.alarm_count }} 次</b></span></footer></section>
          </div>

          <section class="deviation-section"><header><div><p class="section-code">ROBUST DEVIATION EXPLANATION</p><h3>它为什么被判为异常</h3></div><p>当前最高异常日相对该设备历史中位数 / IQR，不代表因果根因。</p></header><div class="deviation-grid"><article v-for="(item, index) in equipmentDiagnosis.deviations" :key="item.feature"><span>0{{ index + 1 }} · {{ item.feature }}</span><h4>{{ item.label }}</h4><div><b>{{ item.current }}</b><i><em :style="{ width: `${100 * Math.abs(item.robust_deviation) / equipmentDeviationMax}%` }"></em></i><small>基线 {{ item.baseline_median }}</small></div><footer><strong>{{ item.robust_deviation > 0 ? '+' : '' }}{{ item.robust_deviation }} IQR</strong><span v-if="item.change_pct !== null">{{ item.change_pct > 0 ? '+' : '' }}{{ item.change_pct }}%</span><span v-else>基线为 0</span></footer></article></div></section>

          <div class="equipment-insight-grid">
            <section class="reason-card"><header><p class="section-code">EVENT REASON / REVIEW CLUES</p><h3>事件原因线索</h3></header><div><article v-for="item in equipmentDiagnosis.reason_distribution" :key="item.event_reason"><span>{{ item.event_reason }}</span><i><em :style="{ width: `${100 * item.duration_minutes / equipmentReasonMax}%` }"></em></i><b>{{ formatNumber(item.duration_minutes) }} min</b></article></div><footer>原因分布仅用于安排核查，不作为模型根因结论。</footer></section>
            <section class="equipment-brief"><header><p class="section-code">DEEPSEEK RELIABILITY BRIEF</p><span>{{ equipmentDiagnosis.brief.generation_mode.toUpperCase() }}</span></header><h3>{{ equipmentDiagnosis.brief.headline }}</h3><p>{{ equipmentDiagnosis.brief.summary }}</p><div><article><b>风险观察</b><ul><li v-for="risk in equipmentDiagnosis.brief.risks" :key="risk">{{ risk }}</li></ul></article><article><b>建议动作</b><ul><li v-for="action in equipmentDiagnosis.brief.actions" :key="action">{{ action }}</li></ul></article></div></section>
          </div>

          <section class="equipment-proof-grid"><article class="recipe-proof"><p class="section-code">RECIPE CONTRACT</p><h3>{{ equipmentDiagnosis.recipe.name }}</h3><div><span v-for="feature in equipmentDiagnosis.recipe.features" :key="feature">{{ feature }}</span></div><p>{{ equipmentDiagnosis.recipe.explanation_rule }}</p><details><summary>查看审核 Feature SQL</summary><pre>{{ equipmentDiagnosis.recipe.feature_sql }}</pre></details></article><article class="equipment-trace"><p class="section-code">LANGGRAPH / 5 NODES</p><div v-for="(step, index) in equipmentDiagnosis.trace" :key="step.node_name"><b>0{{ index + 1 }}</b><span><strong>{{ step.display_name }}</strong>{{ step.summary }}</span><small>{{ formatDuration(step.duration_ms) }}</small></div><footer><code>{{ equipmentDiagnosis.run_id }}</code><span>{{ formatDuration(equipmentDiagnosis.duration_ms) }}</span></footer></article></section>
        </template>
      </section>

      <section v-if="activeView === 'agent'" class="agent-view">
        <header class="agent-hero">
          <div>
            <p class="section-code">PHASE 05 / RAG + SQL + ALGORITHM RECIPES</p>
            <h2>一句话，<span>走完分析链路</span></h2>
            <p>不是聊天演示：问题经过业务理解、证据检索、DeepSeek Text-to-SQL、安全校验与只读执行，最后生成图表和可追溯结论。</p>
          </div>
          <div class="agent-badge"><b>3</b><span>RAG ROUTES<br />RRF FUSION</span></div>
        </header>

        <form class="query-console" @submit.prevent="runAgent">
          <div class="console-index"><span>ASK</span><strong>01</strong></div>
          <label>
            <span>制造数据问题 / 质量 · 设备 · 生产基础问析</span>
            <textarea v-model="agentQuestion" rows="2" maxlength="300" aria-label="分析问题"></textarea>
          </label>
          <button type="submit" :disabled="agentRunning">
            <span v-if="agentRunning" class="button-spinner"></span>
            {{ agentRunning ? 'Agent 分析中' : '启动智能问析' }}
            <b>{{ agentRunning ? '请稍候' : '→' }}</b>
          </button>
        </form>
        <div class="example-switcher">
          <span>QUICK TEST /</span>
          <button v-for="example in agentExamples" :key="example.code" :class="{ active: agentQuestion === example.question }" @click="agentQuestion = example.question">
            <small>{{ example.code }}</small><b>{{ example.scene }}</b><i>→</i>
          </button>
        </div>
        <div v-if="agentRunning" class="agent-progress"><i></i><p><strong>DeepSeek 正在推理并生成 SQL</strong><span>完整链路通常需要 30–90 秒，请保持页面开启。</span></p></div>
        <div v-if="agentError" class="agent-error"><strong>本次执行未完成</strong><p>{{ agentError }}</p><button @click="runAgent">重新运行</button></div>

        <template v-if="agentResult">
          <section class="run-summary">
            <div><span>RUN STATUS</span><strong><i></i>{{ agentResult.status.toUpperCase() }}</strong></div>
            <div><span>MODEL</span><strong>{{ agentResult.model }}</strong></div>
            <div><span>SQL MODE</span><strong>{{ agentResult.generation_mode === 'deepseek' ? 'DEEPSEEK' : 'GUARDED FALLBACK' }}</strong></div>
            <div><span>DURATION</span><strong>{{ formatDuration(agentResult.duration_ms) }}</strong></div>
            <code>{{ agentResult.run_id }}</code>
          </section>

          <section class="rag-ledger">
            <div class="rag-title"><p class="section-code">HYBRID RETRIEVAL LEDGER</p><h3>EvidenceBundle 是怎么找出来的</h3><span>{{ agentResult.evidence.retrieval.strategy }}</span></div>
            <div v-for="channel in ['exact', 'fuzzy', 'vector']" :key="channel" class="rag-channel"><span>{{ channel.toUpperCase() }}</span><strong>{{ agentResult.evidence.retrieval.channel_hits[channel] ?? 0 }}</strong><small>候选命中</small></div>
            <div class="rag-reduction"><span>CONTEXT CUT</span><strong>{{ agentResult.evidence.retrieval.context_reduction_pct }}%</strong><small>相对全量上下文</small></div>
          </section>

          <section class="trace-section">
            <header><div><p class="section-code">VISIBLE EXECUTION PIPELINE</p><h3>Agent 执行轨迹</h3></div><span>{{ agentResult.trace.filter((step) => step.status === 'completed').length }} STEPS COMPLETED</span></header>
            <div class="trace-rail">
              <article v-for="(step, index) in agentResult.trace" :key="step.node_name">
                <div class="trace-number">{{ String(index + 1).padStart(2, '0') }}</div>
                <div><span>{{ step.node_name }}</span><h4>{{ step.display_name }}</h4><p>{{ step.summary }}</p></div>
                <time>{{ formatDuration(step.duration_ms) }}</time>
              </article>
            </div>
          </section>

          <div class="evidence-sql-grid">
            <section class="evidence-card">
              <header><p class="section-code">GROUNDED EVIDENCE</p><h3>本次证据包</h3></header>
              <div class="metric-proof"><span>指标口径 · v{{ agentResult.evidence.metric.version }}</span><strong>{{ agentResult.evidence.metric.name }}</strong><code>{{ agentResult.evidence.metric.formula }}</code></div>
              <div class="rule-proof"><span>强规则</span><p>{{ agentResult.evidence.rule }}</p></div>
              <div class="table-proof"><span v-for="table in agentResult.evidence.tables" :key="table">{{ table }}</span></div>
              <div v-for="relation in agentResult.evidence.relations" :key="relation.source_table" class="join-proof"><code>{{ relation.source_table }}.{{ relation.source_column }}</code><b>→ VERIFIED JOIN →</b><code>{{ relation.target_table }}.{{ relation.target_column }}</code></div>
              <div class="source-proof"><span v-for="item in agentResult.evidence.items.slice(0, 6)" :key="item.id"><b>{{ item.source_type }}</b>{{ item.title }}<small>{{ item.channels.join(' + ') }}</small></span></div>
            </section>
            <section class="sql-card">
              <header><div><p class="section-code">TEXT-TO-SQL ARTIFACT</p><h3>生成并执行的 SQL</h3></div><span><i></i>SQLGLOT {{ agentResult.sql.validation.toUpperCase() }} · REPAIR {{ agentResult.sql.repair_count }}/2</span></header>
              <pre><code>{{ agentResult.sql.text }}</code></pre>
              <footer><span>READ ONLY TRANSACTION</span><span>TIMEOUT 5S</span><span>LIMIT ≤ 100</span></footer>
            </section>
          </div>

          <section class="result-section">
            <header><div><p class="section-code">EXECUTED RESULT / NOT MOCKED</p><h3>{{ agentResult.chart.title }}</h3></div><div class="date-range">{{ agentResult.time_range.start }}<b>→</b>{{ agentResult.time_range.end }}</div></header>
            <div class="result-grid">
              <div class="yield-chart" role="img" :aria-label="agentResult.chart.title">
                <div class="chart-scale"><span>{{ chartCeiling }}{{ agentResult.chart.unit }}</span><span>{{ ((chartCeiling + chartBaseline) / 2).toFixed(1) }}{{ agentResult.chart.unit }}</span><span>{{ chartBaseline }}{{ agentResult.chart.unit }}</span></div>
                <template v-if="agentResult.chart.type === 'bar'">
                  <div v-for="(category, index) in agentResult.chart.categories" :key="category" class="bar-column">
                    <strong>{{ agentResult.chart.series[0].data[index] }}{{ agentResult.chart.unit }}</strong>
                    <div class="bar-track"><i :style="{ height: chartHeight(agentResult.chart.series[0].data[index]) }"></i></div>
                    <span>{{ category }}</span>
                  </div>
                </template>
                <div v-else-if="agentResult.chart.type === 'pareto'" class="pareto-combo">
                  <div class="pareto-combo-bars"><div v-for="(category, index) in agentResult.chart.categories" :key="category"><strong>{{ formatNumber(agentResult.chart.series[0].data[index]) }}</strong><i><em :style="{ height: chartHeight(agentResult.chart.series[0].data[index]) }"></em></i><span>{{ category }}</span></div></div>
                  <svg viewBox="0 0 800 280" preserveAspectRatio="none" aria-hidden="true"><polyline :points="paretoLinePoints" /><g v-for="(value, index) in agentResult.chart.series[1].data" :key="index"><circle :cx="agentResult.chart.series[1].data.length <= 1 ? 400 : 70 + index * 660 / (agentResult.chart.series[1].data.length - 1)" :cy="245 - 2 * value" r="6" /><text :x="agentResult.chart.series[1].data.length <= 1 ? 400 : 70 + index * 660 / (agentResult.chart.series[1].data.length - 1)" :y="230 - 2 * value">{{ value }}%</text></g></svg>
                </div>
                <svg v-else class="line-plot" viewBox="0 0 800 280" preserveAspectRatio="none" aria-hidden="true">
                  <line v-for="y in [45, 140, 235]" :key="y" x1="55" :y1="y" x2="745" :y2="y" />
                  <polyline :points="linePoints" />
                  <g v-for="(value, index) in agentResult.chart.series[0].data" :key="index"><circle :cx="lineX(index)" :cy="lineY(value)" r="6" /><text :x="lineX(index)" :y="lineY(value) - 13">{{ value }}</text><text class="axis-label" :x="lineX(index)" y="262">{{ agentResult.chart.categories[index].slice(5) }}</text></g>
                </svg>
              </div>
              <div class="result-table-wrap">
                <table><thead><tr><th v-for="column in agentResult.result.columns" :key="column">{{ columnLabel(column) }}</th></tr></thead><tbody><tr v-for="(row, rowIndex) in agentResult.result.rows" :key="rowIndex"><td v-for="column in agentResult.result.columns" :key="column"><b v-if="column === agentResult.chart.y_field">{{ formatCell(row[column], column) }}</b><template v-else>{{ formatCell(row[column], column) }}</template></td></tr></tbody></table>
                <p>{{ agentResult.result.row_count }} ROWS · PostgreSQL 实时查询结果</p>
              </div>
            </div>
          </section>

          <section class="answer-card"><span>AGENT CONCLUSION</span><div class="quote-mark">“</div><p>{{ agentResult.answer }}</p><footer>结论基于检验数据与已发布指标口径 <b>·</b> 不推断未提供的根因</footer></section>
        </template>
      </section>
    </template>

    <div v-if="metricEditorOpen" class="modal-backdrop" @click.self="metricEditorOpen = false"><form class="metric-editor" @submit.prevent="saveMetric"><header><div><p class="section-code">METRIC DEFINITION</p><h2>{{ editingMetric ? '编辑指标口径' : '新增指标口径' }}</h2></div><button type="button" @click="metricEditorOpen = false">×</button></header><div class="form-grid"><label>指标编码<input v-model="metricForm.metric_code" :disabled="editingMetric" required pattern="[a-z][a-z0-9_]{2,48}" /></label><label>业务主题<select v-model="metricForm.topic_code"><option v-for="topic in topics" :key="topic.topic_code" :value="topic.topic_code">{{ topic.topic_name }}</option></select></label><label>指标名称<input v-model="metricForm.metric_name" required /></label><label>单位<input v-model="metricForm.unit" required /></label><label class="wide">业务说明<textarea v-model="metricForm.description" required></textarea></label><label class="wide">计算公式<textarea v-model="metricForm.formula" class="formula-input" required></textarea></label><label>统计粒度<input v-model="metricForm.grain" required /></label><label>状态<select v-model="metricForm.status"><option value="draft">草稿</option><option value="published">已发布</option><option value="disabled">已停用</option></select></label><label class="wide">可用维度（顿号分隔）<input v-model="dimensionText" /></label><label class="wide">映射表（顿号分隔）<input v-model="mappedTableText" /></label></div><footer><button type="button" @click="metricEditorOpen = false">取消</button><button class="save" type="submit">保存口径</button></footer></form></div>
  </main>
</template>
