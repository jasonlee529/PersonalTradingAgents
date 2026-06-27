import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Button, Card, Empty, Input, InputNumber, Select, Spin, Table, Tag, Statistic, Grid,
} from '@arco-design/web-react'
import { IconPlayArrowFill, IconRefresh } from '@arco-design/web-react/icon'
import { useQuery, useMutation } from '@tanstack/react-query'
import {
  backtestApi,
  strategyApi,
  type BacktestRequest,
  type BacktestResponse,
  type BacktestTradeItem,
} from '../api/client'

const { Row, Col } = Grid

function todayMinus(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() - days)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function displayNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return Number(value).toFixed(digits)
}

function displayAmount(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  const num = Number(value)
  if (Math.abs(num) >= 100000000) return `${(num / 100000000).toFixed(2)}亿`
  if (Math.abs(num) >= 10000) return `${(num / 10000).toFixed(2)}万`
  return num.toFixed(2)
}

function getActionTag(action: string) {
  switch (action) {
    case 'buy': return <Tag color="arcoblue" size="small">买入</Tag>
    case 'sell_stop': return <Tag color="red" size="small">止损</Tag>
    case 'sell_profit': return <Tag color="green" size="small">止盈</Tag>
    default: return <Tag size="small">{action}</Tag>
  }
}

export default function BacktestPage() {
  const navigate = useNavigate()
  const [strategyId, setStrategyId] = useState('strong_pullback')
  const [startDate, setStartDate] = useState(todayMinus(120))
  const [endDate, setEndDate] = useState(todayMinus(0))
  const [market, setMarket] = useState('all')
  const [maxUniverse, setMaxUniverse] = useState(50)
  const [initialCapital, setInitialCapital] = useState(1000000)
  const [maxHoldings, setMaxHoldings] = useState(5)
  const [maxPositionPct, setMaxPositionPct] = useState(0.2)
  const [stopLossType, setStopLossType] = useState('ma20')
  const [stopLossPct, setStopLossPct] = useState(0.08)
  const [slippage, setSlippage] = useState(0.003)
  const [symbols, setSymbols] = useState('')

  const { data: strategyList } = useQuery({
    queryKey: ['strategies-list'],
    queryFn: async () => (await strategyApi.list()).data,
    staleTime: 300000,
  })
  const strategies = strategyList?.strategies || []

  const mutation = useMutation({
    mutationFn: async (req: BacktestRequest) => (await backtestApi.run(req)).data,
  })

  const result: BacktestResponse | undefined = mutation.data
  const metrics = result?.metrics
  const isRunning = mutation.isPending

  const handleRun = () => {
    const req: BacktestRequest = {
      strategy_id: strategyId,
      start_date: startDate,
      end_date: endDate,
      market,
      max_universe: maxUniverse,
      initial_capital: initialCapital,
      max_holdings: maxHoldings,
      max_position_pct: maxPositionPct,
      stop_loss_type: stopLossType,
      stop_loss_pct: stopLossPct,
      slippage,
      symbols: symbols.trim() ? symbols.split(/[\s,]+/).filter(Boolean) : [],
    }
    mutation.mutate(req)
  }

  const tradeColumns = [
    {
      title: '日期', dataIndex: 'date', width: 110,
      sorter: (a: BacktestTradeItem, b: BacktestTradeItem) => a.date.localeCompare(b.date),
    },
    {
      title: '操作', dataIndex: 'action', width: 80,
      render: (value: string) => getActionTag(value),
    },
    {
      title: '股票', dataIndex: 'symbol', width: 140,
      render: (_: unknown, item: BacktestTradeItem) => (
        <Button type="text" size="small"
          onClick={() => navigate(`/stock?symbol=${encodeURIComponent(item.symbol)}`)}>
          {item.symbol} {item.name || ''}
        </Button>
      ),
    },
    { title: '价格', dataIndex: 'price', width: 80, render: (v: number) => displayNumber(v) },
    { title: '股数', dataIndex: 'shares', width: 80 },
    { title: '金额', dataIndex: 'amount', width: 110, render: (v: number) => displayAmount(v) },
    {
      title: '盈亏', dataIndex: 'pnl', width: 100,
      sorter: (a: BacktestTradeItem, b: BacktestTradeItem) => a.pnl - b.pnl,
      render: (v: number, item: BacktestTradeItem) => {
        if (item.action === 'buy') return '-'
        const color = v > 0 ? 'var(--color-up)' : 'var(--color-down)'
        return <span style={{ color, fontWeight: 600 }}>{displayAmount(v)}</span>
      },
    },
    {
      title: '盈亏%', dataIndex: 'pnl_pct', width: 80,
      render: (v: number, item: BacktestTradeItem) => {
        if (item.action === 'buy') return '-'
        const color = v > 0 ? 'var(--color-up)' : 'var(--color-down)'
        return <span style={{ color }}>{displayNumber(v)}%</span>
      },
    },
    { title: '持仓天数', dataIndex: 'holding_days', width: 80 },
    { title: '原因', dataIndex: 'reason', width: 80 },
  ]

  // 简易权益曲线（文本迷你图）
  const equityCurve = result?.equity_curve || []
  const equityValues = equityCurve.map((p) => p.equity)
  const minEq = equityValues.length ? Math.min(...equityValues) : 0
  const maxEq = equityValues.length ? Math.max(...equityValues) : 0
  const range = maxEq - minEq || 1

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h2 className="page-header-title">策略回测</h2>
          <div style={{ marginTop: 4, color: 'var(--text-muted)', fontSize: 13 }}>
            历史回测评估策略绩效（A股T+1、涨跌停、滑点）
          </div>
        </div>
        <Button
          type="primary"
          icon={<IconPlayArrowFill />}
          loading={isRunning}
          onClick={handleRun}
          size="large"
        >
          开始回测
        </Button>
      </div>

      {/* 回测配置 */}
      <Card className="card-glow-hover" style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
          <Select value={strategyId} onChange={setStrategyId} style={{ width: 180 }}>
            {strategies.map((s) => (
              <Select.Option key={s.id} value={s.id}>{s.name}</Select.Option>
            ))}
          </Select>
          <ParamText label="开始" value={startDate} onChange={setStartDate} width={120} />
          <ParamText label="结束" value={endDate} onChange={setEndDate} width={120} />
          <Select value={market} onChange={setMarket} style={{ width: 120 }}>
            <Select.Option value="all">全市场</Select.Option>
            <Select.Option value="sh">沪市</Select.Option>
            <Select.Option value="sz">深市</Select.Option>
          </Select>
          <ParamNumber label="股票池上限" value={maxUniverse} onChange={setMaxUniverse} min={5} max={500} />
          <ParamNumber label="初始资金" value={initialCapital} onChange={setInitialCapital} min={10000} max={100000000} step={100000} width={130} />
        </div>
        <div style={{ marginTop: 12, display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
          <ParamNumber label="最大持仓" value={maxHoldings} onChange={setMaxHoldings} min={1} max={20} />
          <ParamNumber label="单票仓位%" value={maxPositionPct * 100} onChange={(v) => setMaxPositionPct(v / 100)} min={5} max={50} step={5} />
          <Select value={stopLossType} onChange={setStopLossType} style={{ width: 130 }}>
            <Select.Option value="ma20">止损:MA20</Select.Option>
            <Select.Option value="fixed">止损:固定%</Select.Option>
          </Select>
          {stopLossType === 'fixed' && (
            <ParamNumber label="止损%" value={stopLossPct * 100} onChange={(v) => setStopLossPct(v / 100)} min={1} max={20} step={1} />
          )}
          <ParamNumber label="滑点%" value={slippage * 100} onChange={(v) => setSlippage(v / 100)} min={0} max={2} step={0.1} />
          <Input
            value={symbols}
            onChange={setSymbols}
            placeholder="指定股票(逗号分隔，留空用市场TopN)"
            style={{ width: 280 }}
          />
        </div>
      </Card>

      {/* 错误提示 */}
      {result?.error && (
        <Card style={{ marginBottom: 20, borderColor: 'var(--color-down)' }}>
          <div style={{ color: 'var(--color-down)', fontWeight: 500 }}>回测失败: {result.error}</div>
        </Card>
      )}

      {/* 回测中 */}
      {isRunning && (
        <Card style={{ marginBottom: 20 }}>
          <div style={{ textAlign: 'center', padding: 48 }}>
            <Spin size={40} />
            <div style={{ marginTop: 16, color: 'var(--text-dim)' }}>正在回测中，请耐心等待...</div>
          </div>
        </Card>
      )}

      {/* 绩效指标 */}
      {metrics && !isRunning && (
        <Card className="card-glow-hover" style={{ marginBottom: 20 }}>
          <Row gutter={[16, 16]}>
            <Col span={6}>
              <Statistic title="累计收益" value={metrics.total_return_pct}
                suffix="%" precision={2}
                styleValue={{ color: metrics.total_return_pct >= 0 ? 'var(--color-up)' : 'var(--color-down)' }} />
            </Col>
            <Col span={6}>
              <Statistic title="年化收益" value={metrics.annualized_return_pct}
                suffix="%" precision={2}
                styleValue={{ color: metrics.annualized_return_pct >= 0 ? 'var(--color-up)' : 'var(--color-down)' }} />
            </Col>
            <Col span={6}>
              <Statistic title="最大回撤" value={metrics.max_drawdown_pct}
                suffix="%" precision={2}
                styleValue={{ color: 'var(--color-down)' }} />
            </Col>
            <Col span={6}>
              <Statistic title="波动率" value={metrics.volatility_pct} suffix="%" precision={2} />
            </Col>
            <Col span={6}>
              <Statistic title="胜率" value={metrics.win_rate_pct} suffix="%" precision={1} />
            </Col>
            <Col span={6}>
              <Statistic title="盈亏比" value={metrics.profit_loss_ratio} precision={2} />
            </Col>
            <Col span={6}>
              <Statistic title="交易次数" value={metrics.total_trades} />
            </Col>
            <Col span={6}>
              <Statistic title="平均持仓天数" value={metrics.avg_holding_days} precision={1} />
            </Col>
          </Row>
          <div style={{ marginTop: 12, display: 'flex', gap: 12, color: 'var(--text-muted)', fontSize: 13 }}>
            <Tag color="gray">股票池: {result?.universe_size} 只</Tag>
            <Tag color="gray">回测天数: {result?.trading_days} 天</Tag>
            <Tag color="gray">初始资金: {displayAmount(metrics.initial_capital)}</Tag>
            <Tag color="gray">最终权益: {displayAmount(metrics.final_equity)}</Tag>
          </div>
        </Card>
      )}

      {/* 权益曲线 */}
      {equityCurve.length > 0 && !isRunning && (
        <Card className="card-glow-hover" title="权益曲线" style={{ marginBottom: 20 }}>
          <div style={{ position: 'relative', height: 200, overflow: 'hidden' }}>
            <svg width="100%" height="200" preserveAspectRatio="none" style={{ display: 'block' }}>
              <polyline
                fill="none"
                stroke="var(--border-accent)"
                strokeWidth="2"
                points={equityValues.map((v, i) => {
                  const x = (i / (equityValues.length - 1 || 1)) * 100
                  const y = 190 - ((v - minEq) / range) * 180
                  return `${x},${y}`
                }).join(' ')}
              />
            </svg>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-dim)', fontSize: 12, marginTop: 8 }}>
            <span>{equityCurve[0]?.date}</span>
            <span>最高: {displayAmount(maxEq)}</span>
            <span>最低: {displayAmount(minEq)}</span>
            <span>{equityCurve[equityCurve.length - 1]?.date}</span>
          </div>
        </Card>
      )}

      {/* 交易记录 */}
      {result && !isRunning && (
        <Card className="card-glow-hover">
          <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 16, fontWeight: 600 }}>交易记录</span>
            <Button icon={<IconRefresh />} onClick={() => mutation.reset()} size="small">清除</Button>
          </div>
          {result.trades.length === 0 ? (
            <Empty description="无交易记录" />
          ) : (
            <Table
              rowKey={(record: BacktestTradeItem, index?: number) => `${record.date}-${record.symbol}-${record.action}-${index ?? 0}`}
              columns={tradeColumns}
              data={result.trades}
              pagination={{ pageSize: 20, showTotal: true }}
              scroll={{ x: 1100 }}
              size="small"
            />
          )}
        </Card>
      )}

      {/* 空状态 */}
      {!result && !isRunning && (
        <Card>
          <Empty
            description={
              <div>
                <div style={{ fontSize: 16, fontWeight: 500, marginBottom: 8 }}>尚未回测</div>
                <div style={{ color: 'var(--text-dim)', marginBottom: 12 }}>
                  配置回测参数后点击"开始回测"按钮
                </div>
                <Button type="primary" icon={<IconPlayArrowFill />} onClick={handleRun}>开始回测</Button>
              </div>
            }
          />
        </Card>
      )}
    </div>
  )
}

function ParamNumber({
  label, value, onChange, min, max, step, width = 100,
}: {
  label: string
  value: number
  onChange: (v: number) => void
  min?: number
  max?: number
  step?: number
  width?: number
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>{label}</span>
      <InputNumber
        value={value}
        onChange={(v) => onChange(typeof v === 'number' ? v : value)}
        min={min}
        max={max}
        step={step ?? 1}
        style={{ width }}
        size="small"
      />
    </div>
  )
}

function ParamText({
  label, value, onChange, width = 120,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  width?: number
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>{label}</span>
      <Input
        value={value}
        onChange={onChange}
        style={{ width }}
        size="small"
      />
    </div>
  )
}
