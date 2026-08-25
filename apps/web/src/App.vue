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

const activeView = ref<'overview' | 'catalog' | 'knowledge'>('overview')
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
async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options)
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as { detail?: string }
    throw new Error(payload.detail || `请求失败：${response.status}`)
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
      <div class="system-pill" :class="{ ready: systemReady }"><i></i>{{ systemReady ? 'SYSTEM READY' : 'CONNECTING' }}</div>
    </nav>
    <div v-if="error" class="error-banner">{{ error }} <button @click="loadWorkspace">重试</button></div>
    <div v-if="loading" class="loading-screen"><i></i><span>正在扫描制造数据资产…</span></div>

    <template v-else>
      <section v-if="activeView === 'overview'" class="overview-view">
        <div class="hero-grid">
          <article class="hero-copy"><p class="section-code">PHASE 01 / DATA & KNOWLEDGE FOUNDATION</p><h2>先让 Agent<br />真正<span>看懂数据</span></h2><p>目录来自 PostgreSQL 实时扫描，指标口径与 Join 规则由业务知识明确约束。后续 RAG 和 Text-to-SQL 只在这套证据上工作。</p><button class="primary-action" @click="activeView = 'catalog'">进入数据目录 <b>→</b></button></article>
          <article class="date-card"><span>DATASET ANCHOR</span><strong>{{ summary?.dataset_max_business_date }}</strong><p>所有“本月 / 最近 30 天”等相对时间均以此业务日期为准。</p></article>
        </div>
        <div class="stat-strip">
          <div><small>TABLES</small><strong>{{ summary?.table_count }}</strong><span>9 主表 + 1 留出表</span></div><div><small>COLUMNS</small><strong>{{ summary?.column_count }}</strong><span>含注释与脱敏样例</span></div>
          <div><small>RELATIONS</small><strong>{{ summary?.relation_count }}</strong><span>真实外键关系</span></div><div><small>ROWS</small><strong>{{ formatNumber(summary?.total_rows) }}</strong><span>可解释演示记录</span></div>
        </div>
        <div class="topic-grid">
          <article v-for="(topic, index) in topics" :key="topic.topic_code" :style="{ '--topic': topic.accent_color }"><div class="topic-number">0{{ index + 1 }}</div><span>{{ topic.topic_code.toUpperCase() }}</span><h3>{{ topic.topic_name }}</h3><p>{{ topic.description }}</p><footer><b>{{ topic.metric_count }}</b> 指标 · <b>{{ topic.rule_count }}</b> 强规则 · <b>{{ topic.object_count }}</b> 对象</footer></article>
        </div>
        <section class="next-band"><span>NEXT / PHASE 02</span><h3>{{ bootstrap?.next_milestone }}</h3><p>理解 → 精确 Schema 检索 → SQL → 安全执行 → 柱状图 → 结论</p><div><i></i></div></section>
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
    </template>

    <div v-if="metricEditorOpen" class="modal-backdrop" @click.self="metricEditorOpen = false"><form class="metric-editor" @submit.prevent="saveMetric"><header><div><p class="section-code">METRIC DEFINITION</p><h2>{{ editingMetric ? '编辑指标口径' : '新增指标口径' }}</h2></div><button type="button" @click="metricEditorOpen = false">×</button></header><div class="form-grid"><label>指标编码<input v-model="metricForm.metric_code" :disabled="editingMetric" required pattern="[a-z][a-z0-9_]{2,48}" /></label><label>业务主题<select v-model="metricForm.topic_code"><option v-for="topic in topics" :key="topic.topic_code" :value="topic.topic_code">{{ topic.topic_name }}</option></select></label><label>指标名称<input v-model="metricForm.metric_name" required /></label><label>单位<input v-model="metricForm.unit" required /></label><label class="wide">业务说明<textarea v-model="metricForm.description" required></textarea></label><label class="wide">计算公式<textarea v-model="metricForm.formula" class="formula-input" required></textarea></label><label>统计粒度<input v-model="metricForm.grain" required /></label><label>状态<select v-model="metricForm.status"><option value="draft">草稿</option><option value="published">已发布</option><option value="disabled">已停用</option></select></label><label class="wide">可用维度（顿号分隔）<input v-model="dimensionText" /></label><label class="wide">映射表（顿号分隔）<input v-model="mappedTableText" /></label></div><footer><button type="button" @click="metricEditorOpen = false">取消</button><button class="save" type="submit">保存口径</button></footer></form></div>
  </main>
</template>
