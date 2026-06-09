import { useEffect, useMemo, useRef, useState } from 'react'
import { Button, Card, Message, Modal, Progress, Spin, Tag } from '@arco-design/web-react'
import { IconArrowLeft, IconEye, IconRefresh } from '@arco-design/web-react/icon'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useNavigate, useParams } from 'react-router-dom'
import { analysisApi, AnalysisStatus, AnalysisStep, portfolioApi } from '../api/client'
import { usePortfolioStore, type HoldingDetail } from '../store/usePortfolioStore'


const statusText: Record<string, string> = {
  pending: '等待',
  running: '执行中',
  done: '完成',
  error: '异常',
  completed: '完成',
  not_found: '未找到',
}

const statusColor: Record<string, string> = {
  pending: 'gray',
  running: 'blue',
  done: 'green',
  completed: 'green',
  error: 'red',
}

const NODE_WIDTH = 270
const NODE_HEIGHT = 96
const CANVAS_HEIGHT = 690

// ── 布局配置（调整间距只需改这里）─────────────────────────────────────────────
const PAD_X = 44
const COL_GAP = 64
const ROW_GAP = 22

// 列定义：每列包含的节点
const COLUMNS = [
  { id: 'data', label: '分析模块', nodeIds: ['prepare_data'] },
  { id: 'analyst_left', label: '分析师团队', nodeIds: ['analyst_market', 'analyst_sentiment', 'analyst_news'] },
  { id: 'analyst_right', label: '分析师团队', nodeIds: ['analyst_fundamentals', 'analyst_catalyst', 'analyst_flow_risk'] },
  { id: 'research', label: '研究团队辩论', nodeIds: ['debate_bull', 'debate_judge', 'debate_bear'] },
  { id: 'trader', label: '交易执行', nodeIds: ['trader_plan'] },
  { id: 'risk', label: '风控团队', nodeIds: ['risk_aggressive', 'risk_neutral', 'risk_conservative'] },
  { id: 'final', label: '最终决策', nodeIds: ['final_decision'] },
]

// 组背景框：起始列索引 → 结束列索引（含）
const GROUP_DEFS = [
  { id: 'analysis', label: '分析师团队', colStart: 1, colEnd: 2 },
  { id: 'debate', label: '研究团队辩论', colStart: 3, colEnd: 3 },
  { id: 'trading', label: '交易执行', colStart: 4, colEnd: 4 },
  { id: 'risk', label: '风控团队', colStart: 5, colEnd: 5 },
  { id: 'final', label: '最终决策', colStart: 6, colEnd: 6 },
]

// 动态计算画布宽度
const COL_COUNT = COLUMNS.length
const CANVAS_WIDTH = PAD_X * 2 + COL_COUNT * NODE_WIDTH + (COL_COUNT - 1) * COL_GAP

// 每列 x 坐标
const COL_X = COLUMNS.map((_, i) => PAD_X + i * (NODE_WIDTH + COL_GAP))

// 节点位置
const NODE_POS: Record<string, { x: number; y: number }> = {}
COLUMNS.forEach((col, colIdx) => {
  const count = col.nodeIds.length
  const totalH = count * NODE_HEIGHT + (count - 1) * ROW_GAP
  const startY = (CANVAS_HEIGHT - totalH) / 2
  col.nodeIds.forEach((id, idx) => {
    NODE_POS[id] = { x: COL_X[colIdx], y: Math.round(startY + idx * (NODE_HEIGHT + ROW_GAP)) }
  })
})

// 组背景框位置（根据组内节点实际分布自适应高度）
const GROUP_RENDERS = GROUP_DEFS.map(g => {
  const nodeIds: string[] = []
  for (let i = g.colStart; i <= g.colEnd; i++) {
    nodeIds.push(...COLUMNS[i].nodeIds)
  }
  const ys = nodeIds.map(id => NODE_POS[id].y)
  const minY = Math.min(...ys)
  const maxBottom = Math.max(...ys) + NODE_HEIGHT

  const x = COL_X[g.colStart] - 12
  const y = minY - 20
  const span = g.colEnd - g.colStart
  const width = (span + 1) * NODE_WIDTH + span * COL_GAP + 24
  const height = maxBottom - y + 20
  return { ...g, x, y, width, height }
})

type FlowNodeSpec = {
  id: string
  fallbackLabel: string
  group: string
  artifactKey?: string
  x: number
  y: number
}

const FLOW_NODES: FlowNodeSpec[] = [
  { id: 'prepare_data', fallbackLabel: '准备数据', group: '分析模块', x: NODE_POS['prepare_data'].x, y: NODE_POS['prepare_data'].y },
  { id: 'analyst_market', fallbackLabel: '市场结构', group: '分析师团队', artifactKey: 'market_report', x: NODE_POS['analyst_market'].x, y: NODE_POS['analyst_market'].y },
  { id: 'analyst_sentiment', fallbackLabel: '情绪叙事', group: '分析师团队', artifactKey: 'sentiment_report', x: NODE_POS['analyst_sentiment'].x, y: NODE_POS['analyst_sentiment'].y },
  { id: 'analyst_news', fallbackLabel: '新闻事件', group: '分析师团队', artifactKey: 'news_report', x: NODE_POS['analyst_news'].x, y: NODE_POS['analyst_news'].y },
  { id: 'analyst_fundamentals', fallbackLabel: '基本面', group: '分析师团队', artifactKey: 'fundamentals_report', x: NODE_POS['analyst_fundamentals'].x, y: NODE_POS['analyst_fundamentals'].y },
  { id: 'analyst_catalyst', fallbackLabel: '政策催化', group: '分析师团队', artifactKey: 'catalyst_report', x: NODE_POS['analyst_catalyst'].x, y: NODE_POS['analyst_catalyst'].y },
  { id: 'analyst_flow_risk', fallbackLabel: '资金风险', group: '分析师团队', artifactKey: 'flow_risk_report', x: NODE_POS['analyst_flow_risk'].x, y: NODE_POS['analyst_flow_risk'].y },
  { id: 'debate_bull', fallbackLabel: '多头论证', group: '研究团队', x: NODE_POS['debate_bull'].x, y: NODE_POS['debate_bull'].y },
  { id: 'debate_judge', fallbackLabel: '研究总监', group: '研究团队', artifactKey: 'investment_plan', x: NODE_POS['debate_judge'].x, y: NODE_POS['debate_judge'].y },
  { id: 'debate_bear', fallbackLabel: '空头质询', group: '研究团队', x: NODE_POS['debate_bear'].x, y: NODE_POS['debate_bear'].y },
  { id: 'trader_plan', fallbackLabel: '交易员', group: '交易执行', artifactKey: 'trader_investment_plan', x: NODE_POS['trader_plan'].x, y: NODE_POS['trader_plan'].y },
  { id: 'risk_aggressive', fallbackLabel: '进攻风控', group: '风控团队', x: NODE_POS['risk_aggressive'].x, y: NODE_POS['risk_aggressive'].y },
  { id: 'risk_neutral', fallbackLabel: '中立风控', group: '风控团队', x: NODE_POS['risk_neutral'].x, y: NODE_POS['risk_neutral'].y },
  { id: 'risk_conservative', fallbackLabel: '稳健风控', group: '风控团队', x: NODE_POS['risk_conservative'].x, y: NODE_POS['risk_conservative'].y },
  { id: 'final_decision', fallbackLabel: '组合经理', group: '最终决策', artifactKey: 'final_trade_decision', x: NODE_POS['final_decision'].x, y: NODE_POS['final_decision'].y },
]

const FLOW_EDGES = [
  ['prepare_data', 'analyst_market'],
  ['prepare_data', 'analyst_sentiment'],
  ['prepare_data', 'analyst_news'],
  ['prepare_data', 'analyst_fundamentals'],
  ['prepare_data', 'analyst_catalyst'],
  ['prepare_data', 'analyst_flow_risk'],
  ['analyst_market', 'debate_bull'],
  ['analyst_sentiment', 'debate_bull'],
  ['analyst_news', 'debate_bull'],
  ['analyst_fundamentals', 'debate_bear'],
  ['analyst_catalyst', 'debate_bear'],
  ['analyst_flow_risk', 'debate_bear'],
  ['debate_bull', 'debate_judge'],
  ['debate_bear', 'debate_judge'],
  ['debate_judge', 'trader_plan'],
  ['trader_plan', 'risk_aggressive'],
  ['trader_plan', 'risk_neutral'],
  ['trader_plan', 'risk_conservative'],
  ['risk_aggressive', 'final_decision'],
  ['risk_neutral', 'final_decision'],
  ['risk_conservative', 'final_decision'],
]

const docTypeLabels: Record<string, string> = {
  market_report: '市场分析',
  sentiment_report: '情绪分析',
  news_report: '新闻分析',
  fundamentals_report: '基本面分析',
  catalyst_report: '政策分析',
  flow_risk_report: '资金与供给风险',
  investment_plan: '研究结论',
  trader_investment_plan: '交易计划',
  risk_debate: '风险评估',
  final_trade_decision: '最终决策',
  full_report: '完整报告',
  analysis: '分析报告',
}

function percent(steps: AnalysisStep[]) {
  if (!steps.length) return 0
  return Math.round((steps.filter((s) => s.status === 'done').length / steps.length) * 100)
}

function activeStep(job?: AnalysisStatus) {
  if (!job) return null
  return job.steps.find((s) => s.step_id === job.phase) || job.steps.find((s) => s.status === 'running') || null
}

function nodeStatus(nodeId: string, stepMap: Map<string, AnalysisStep>) {
  const step = stepMap.get(nodeId)
  return step?.status || 'pending'
}

function edgeActive(from: string, to: string, stepMap: Map<string, AnalysisStep>) {
  const fromStatus = nodeStatus(from, stepMap)
  const toStatus = nodeStatus(to, stepMap)
  return fromStatus === 'done' || fromStatus === 'running' || toStatus === 'running' || toStatus === 'done'
}

function getNodeArtifactKey(step?: AnalysisStep, spec?: FlowNodeSpec) {
  return step?.artifact_key || spec?.artifactKey || ''
}

export default function AnalysisDetailPage() {
  const { jobId = '' } = useParams()
  const navigate = useNavigate()
  const scrollRef = useRef<HTMLDivElement>(null)
  const queryClient = useQueryClient()
  const { holdings, setHoldings } = usePortfolioStore()
  const [selectedNodeId, setSelectedNodeId] = useState<string>('')
  const [reportVisible, setReportVisible] = useState(false)
  const [canvasScale, setCanvasScale] = useState(1)

  const { data: job, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['analysis-detail', jobId],
    queryFn: async () => {
      const resp = await analysisApi.status(jobId)
      return resp.data as AnalysisStatus
    },
    refetchInterval: (query) => {
      const data = query.state.data as AnalysisStatus | undefined
      if (!data) return 1500
      if (data.status === 'completed' || data.status === 'error' || data.status === 'not_found') return false
      return 1500
    },
  })

  useEffect(() => {
    if (!job || job.status === 'completed' || job.status === 'error' || job.status === 'not_found') return
    const id = setInterval(() => refetch(), 1500)
    return () => clearInterval(id)
  }, [job?.status, refetch])

  const retryMutation = useMutation({
    mutationFn: () => analysisApi.retry(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['analysis-detail', jobId] })
      Message.success('已重新提交分析任务')
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.detail || err?.message || '重试失败'
      Message.error(msg)
    },
  })

  const current = activeStep(job)
  const steps = job?.steps || []
  const stepMap = new Map(steps.map((s) => [s.step_id, s]))
  const donePercent = percent(steps)
  const holdingName = holdings.find((h) => h.holding.symbol === job?.symbol)?.holding.name
  const stockTitle = holdingName ? `${holdingName} (${job?.symbol})` : job?.symbol

  const selectedStep = useMemo(() => {
    if (!selectedNodeId) return undefined
    return steps.find((s) => s.step_id === selectedNodeId)
  }, [selectedNodeId, steps])

  const selectedSpec = useMemo(
    () => FLOW_NODES.find((n) => n.id === selectedNodeId),
    [selectedNodeId],
  )

  useEffect(() => {
    if (!job || selectedNodeId) return
    setSelectedNodeId(current?.step_id || steps.find((s) => s.detail?.trim())?.step_id || 'prepare_data')
  }, [current?.step_id, job, selectedNodeId, steps])

  useEffect(() => {
    if (!job?.symbol || holdingName || holdings.length > 0) return
    let cancelled = false
    portfolioApi.list().then((resp) => {
      if (!cancelled) setHoldings(resp.data as HoldingDetail[])
    }).catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [holdingName, holdings.length, job?.symbol, setHoldings])

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const updateScale = () => {
      const availableWidth = Math.max(320, el.clientWidth - 28)
      const availableHeight = Math.max(420, Math.min(window.innerHeight * 0.68, 690))
      const nextScale = Math.min(1, availableWidth / CANVAS_WIDTH, availableHeight / CANVAS_HEIGHT)
      setCanvasScale(nextScale)
    }
    updateScale()
    const observer = new ResizeObserver(updateScale)
    observer.observe(el)
    window.addEventListener('resize', updateScale)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', updateScale)
    }
  }, [isLoading])

  const openNodeReport = (nodeId: string) => {
    setSelectedNodeId(nodeId)
    setReportVisible(true)
  }

  if (isLoading) {
    return (
      <div className="analysis-detail-loading">
        <Spin size={36} />
      </div>
    )
  }

  if (!job || job.status === 'not_found') {
    return (
      <Card>
        <Button type="text" icon={<IconArrowLeft />} onClick={() => navigate('/analysis')}>返回</Button>
        <div className="empty-state">任务不存在或已过期。</div>
      </Card>
    )
  }

  return (
    <div className="analysis-detail-page">
      <div className="analysis-detail-head">
        <Button
          type="text"
          icon={<IconArrowLeft />}
          onClick={() => navigate('/analysis')}
          style={{
            border: '1px solid rgba(103, 232, 249, 0.18)',
            borderRadius: 8,
            padding: '4px 14px',
            color: 'rgba(148, 163, 184, 0.9)',
            fontSize: 13,
            fontWeight: 500,
            transition: 'all 0.2s ease',
          }}
          className="back-to-analysis-btn"
        >
          返回分析记录
        </Button>
        <div style={{ display: 'flex', gap: 8 }}>
          {job.status === 'error' && (
            <Button type="primary" icon={<IconRefresh />} loading={retryMutation.isPending} onClick={() => retryMutation.mutate()}>
              重新分析
            </Button>
          )}
          <Button type="secondary" icon={<IconRefresh />} loading={isFetching} onClick={() => refetch()}>刷新</Button>
        </div>
      </div>

      <section className="analysis-detail-hero">
        <div className="analysis-hero-copy">
          <div className="analysis-detail-kicker">TASK / {job.job_id}</div>
          <h2>{stockTitle} AI 协同投研工作流</h2>
          <p>{current ? `${current.label}: ${current.action || current.role}` : job.progress || '等待任务调度'}</p>
        </div>
        <div className="analysis-detail-meter">
          <div className={`workflow-core ${job.status === 'running' ? 'workflow-core-live' : ''}`}>
            <span>{current?.character || (job.status === 'completed' ? '✓' : 'AI')}</span>
          </div>
          <div className="workflow-meter-text">
            <strong>{donePercent}%</strong>
            <span>pipeline progress</span>
          </div>
          <Progress percent={donePercent} color="var(--accent)" />
          <Tag color={job.status === 'completed' ? 'green' : job.status === 'error' ? 'red' : 'blue'}>
            {statusText[job.status] || job.status}
          </Tag>
        </div>
      </section>

      <section className="workflow-canvas-shell">
        <div className="workflow-canvas-title">
          <div>
            <span />
            <strong>PersonalTradingAgents AI 投研工作流</strong>
          </div>
          <em>点击节点查看当前产物，状态和连线会随执行进度实时更新。</em>
        </div>

        <div className="workflow-canvas-scroll" ref={scrollRef}>
          <div
            className="workflow-canvas-wrapper"
            style={{ width: CANVAS_WIDTH * canvasScale, height: CANVAS_HEIGHT * canvasScale }}
          >
            <div
              className="workflow-canvas"
              style={{ width: CANVAS_WIDTH, height: CANVAS_HEIGHT, transform: `scale(${canvasScale})`, transformOrigin: 'top left' }}
            >
              {GROUP_RENDERS.map(g => (
                <div key={g.id} style={{ position: 'absolute', left: g.x, top: g.y, width: g.width, height: g.height, zIndex: 0 }}>
                  {/* 虚线框背景 */}
                  <div style={{
                    position: 'absolute', inset: 0,
                    border: '1px dashed rgba(103, 232, 249, 0.14)',
                    borderRadius: 12,
                    background: 'linear-gradient(180deg, rgba(103, 232, 249, 0.035), rgba(245, 241, 235, 0.008))',
                  }} />
                  {/* 标题标签 — 浮在框上方，独立背景防遮挡 */}
                  <div style={{
                    position: 'absolute', top: -9, left: 10,
                    padding: '1px 8px',
                    background: 'rgba(5, 10, 18, 0.92)',
                    borderRadius: 4,
                    zIndex: 3,
                  }}>
                    <span style={{
                      fontSize: 10,
                      fontWeight: 'bold',
                      color: 'rgba(148, 163, 184, 0.9)',
                      letterSpacing: '0.1em',
                      textTransform: 'uppercase',
                      fontFamily: 'var(--font-mono)',
                    }}>
                      {g.label}
                    </span>
                  </div>
                </div>
              ))}

              <svg className="workflow-edges" viewBox={`0 0 ${CANVAS_WIDTH} ${CANVAS_HEIGHT}`} preserveAspectRatio="none">
                {FLOW_EDGES.map(([from, to]) => {
                  const a = FLOW_NODES.find((n) => n.id === from)!
                  const b = FLOW_NODES.find((n) => n.id === to)!
                  const x1 = a.x + NODE_WIDTH
                  const y1 = a.y + NODE_HEIGHT / 2
                  const x2 = b.x
                  const y2 = b.y + NODE_HEIGHT / 2
                  const mid = Math.max(42, (x2 - x1) * 0.46)
                  const active = edgeActive(from, to, stepMap)
                  return (
                    <path
                      key={`${from}-${to}`}
                      className={`workflow-edge ${active ? 'workflow-edge-active' : ''}`}
                      d={`M ${x1} ${y1} C ${x1 + mid} ${y1}, ${x2 - mid} ${y2}, ${x2} ${y2}`}
                    />
                  )
                })}
              </svg>

              {FLOW_NODES.map((node) => {
                const step = stepMap.get(node.id)
                const status = step?.status || 'pending'
                return (
                  <FlowNode
                    key={node.id}
                    spec={node}
                    step={step}
                    status={status}
                    active={node.id === job.phase || status === 'running'}
                    selected={selectedStep?.step_id === node.id}
                    onSelect={() => openNodeReport(node.id)}
                  />
                )
              })}

              <div className="workflow-debate-current">
                <i />
                <i />
                <i />
              </div>
            </div>
          </div>
        </div>
      </section>

      <ReportModal
        visible={reportVisible}
        step={selectedStep}
        spec={selectedSpec}
        onClose={() => setReportVisible(false)}
      />
    </div>
  )
}

function FlowNode({
  spec,
  step,
  status,
  active,
  selected,
  onSelect,
}: {
  spec: FlowNodeSpec
  step?: AnalysisStep
  status: string
  active: boolean
  selected: boolean
  onSelect: () => void
}) {
  const hasArtifact = Boolean(step?.detail?.trim())
  const hasKnowledgeTarget = Boolean(getNodeArtifactKey(step, spec))
  const showArtifactBadge = hasArtifact || (hasKnowledgeTarget && status === 'running')
  const artifactBadgeText = hasArtifact ? '查看报告' : '生成中'
  const label = step?.label || spec.fallbackLabel
  const action = step?.action || step?.role || spec.group
  const character = step?.character || 'AI'

  return (
    <button
      type="button"
      className={`flow-node flow-node-${status} ${active ? 'flow-node-active' : ''} ${selected ? 'flow-node-selected' : ''}`}
      style={{ left: spec.x, top: spec.y }}
      onClick={onSelect}
    >
      <span className="flow-node-scan" />
      <div className="flow-node-main">
        <div className="flow-node-icon">{character}</div>
        <div className="flow-node-copy">
          <div className="flow-node-head">
            <strong>{label}</strong>
            <Tag color={statusColor[status] || 'gray'}>{statusText[status] || status}</Tag>
          </div>
          <p>{action}</p>
        </div>
      </div>
      {showArtifactBadge && (
        <span className={`flow-node-report-dot ${hasArtifact ? 'flow-node-report-ready' : ''}`}>
          <IconEye />
          {artifactBadgeText}
        </span>
      )}
    </button>
  )
}

function ReportModal({
  visible,
  step,
  spec,
  onClose,
}: {
  visible: boolean
  step?: AnalysisStep
  spec?: FlowNodeSpec
  onClose: () => void
}) {
  const artifactKey = getNodeArtifactKey(step, spec)
  const title = step?.label || spec?.fallbackLabel || '报告详情'
  const body = step?.detail || ''

  return (
    <Modal
      title={title}
      visible={visible}
      onOk={onClose}
      onCancel={onClose}
      autoFocus={false}
      style={{ width: 960 }}
      className="analysis-report-modal"
    >
      <div>
        <div className="analysis-report-modal-tags">
          {step && <Tag color={statusColor[step.status] || 'gray'}>{statusText[step.status] || step.status}</Tag>}
          <Tag color="arcoblue">{step?.module || spec?.group || '投研工作流'}</Tag>
          {step?.role && <Tag>{step.role}</Tag>}
          {artifactKey && <Tag color="green">{docTypeLabels[artifactKey] || artifactKey}</Tag>}
        </div>

        {body?.trim() ? (
          <div className="report-content" style={{ padding: 20, maxHeight: '68vh', overflow: 'auto' }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{body}</ReactMarkdown>
          </div>
        ) : (
          <div className="report-content analysis-report-empty">
            <strong>暂无研究报告</strong>
            <p>节点完成后，当前产物会第一时间从任务状态显示在这里。</p>
          </div>
        )}
      </div>
    </Modal>
  )
}
