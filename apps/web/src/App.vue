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
  evidence: { metric: { name: string; formula: string; version: string }; rule: string; tables: string[]; relations: Array<{ source_table: string; source_column: string; target_table: string; target_column: string }> }
  sql: { text: string; validation: string; referenced_tables: string[] }
  result: { columns: string[]; rows: Array<Record<string, string | number>>; row_count: number }
  chart: { type: string; title: string; x_field: string; y_field: string; unit: string; categories: string[]; series: Array<{ name: string; data: number[] }> }
  answer: string; trace: AgentTrace[]
}

const activeView = ref<'overview' | 'catalog' | 'knowledge' | 'agent'>('overview')
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
function chartHeight(value: number) { return `${Math.max(8, Math.min(100, (value - 90) * 10))}%` }
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
      <button :class="{ active: activeView === 'agent' }" @click="activeView = 'agent'">智能问析 <span>04</span></button>
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

      <section v-if="activeView === 'agent'" class="agent-view">
        <header class="agent-hero">
          <div>
            <p class="section-code">PHASE 02 / AGENT THIN SLICE</p>
            <h2>一句话，<span>走完分析链路</span></h2>
            <p>不是聊天演示：问题经过业务理解、证据检索、DeepSeek Text-to-SQL、安全校验与只读执行，最后生成图表和可追溯结论。</p>
          </div>
          <div class="agent-badge"><b>8</b><span>LANGGRAPH<br />NODES</span></div>
        </header>

        <form class="query-console" @submit.prevent="runAgent">
          <div class="console-index"><span>ASK</span><strong>01</strong></div>
          <label>
            <span>制造数据问题 / 当前 MVP 支持质量场景</span>
            <textarea v-model="agentQuestion" rows="2" maxlength="300" aria-label="分析问题"></textarea>
          </label>
          <button type="submit" :disabled="agentRunning">
            <span v-if="agentRunning" class="button-spinner"></span>
            {{ agentRunning ? 'Agent 分析中' : '启动智能问析' }}
            <b>{{ agentRunning ? '请稍候' : '→' }}</b>
          </button>
        </form>
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

          <section class="trace-section">
            <header><div><p class="section-code">VISIBLE REASONING PIPELINE</p><h3>Agent 执行轨迹</h3></div><span>{{ agentResult.trace.length }} / 8 COMPLETED</span></header>
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
            </section>
            <section class="sql-card">
              <header><div><p class="section-code">TEXT-TO-SQL ARTIFACT</p><h3>生成并执行的 SQL</h3></div><span><i></i>SQLGLOT {{ agentResult.sql.validation.toUpperCase() }}</span></header>
              <pre><code>{{ agentResult.sql.text }}</code></pre>
              <footer><span>READ ONLY TRANSACTION</span><span>TIMEOUT 5S</span><span>LIMIT ≤ 100</span></footer>
            </section>
          </div>

          <section class="result-section">
            <header><div><p class="section-code">EXECUTED RESULT / NOT MOCKED</p><h3>{{ agentResult.chart.title }}</h3></div><div class="date-range">{{ agentResult.time_range.start }}<b>→</b>{{ agentResult.time_range.end }}</div></header>
            <div class="result-grid">
              <div class="yield-chart" role="img" :aria-label="agentResult.chart.title">
                <div class="chart-scale"><span>100%</span><span>95%</span><span>90%</span></div>
                <div v-for="(category, index) in agentResult.chart.categories" :key="category" class="bar-column">
                  <strong>{{ agentResult.chart.series[0].data[index] }}%</strong>
                  <div class="bar-track"><i :style="{ height: chartHeight(agentResult.chart.series[0].data[index]) }"></i></div>
                  <span>{{ category }}</span>
                </div>
              </div>
              <div class="result-table-wrap">
                <table><thead><tr><th>工序</th><th>良率</th><th>检验数量</th></tr></thead><tbody><tr v-for="row in agentResult.result.rows" :key="String(row.process_name)"><td>{{ row.process_name }}</td><td><b>{{ row.yield_rate }}%</b></td><td>{{ formatNumber(Number(row.inspected_qty)) }}</td></tr></tbody></table>
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
