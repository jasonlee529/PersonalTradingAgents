import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, Empty, Input, InputNumber, Select, Spin, Switch, Table, Tag, Badge } from '@arco-design/web-react'
import { IconRefresh, IconSearch, IconThunderbolt } from '@arco-design/web-react/icon'
import { useQuery } from '@tanstack/react-query'
import {
  strategyApi,
  type StrategyInfo,
  type StrategyMatchItem,
  type StrategyScanParams,
} from '../api/client'

function today(): string {
  const d = new Date()
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
  return num.toFixed(0)
}

export default function StrategiesPage() {
  const navigate = useNavigate()
  const [activeStrategyId, setActiveStrategyId] = useState<string>('')
  const [tradeDate, setTradeDate] = useState(today())
  const [market, setMarket] = useState('all')
  const [keyword, setKeyword] = useState('')

  // 策略参数（与放量回踩默认值对齐，可编辑）
  const [rallyDays, setRallyDays] = useState<number>(20)
  const [minRallyPct, setMinRallyPct] = useState<number>(30)
  const [maPeriod, setMaPeriod] = useState<number>(10)
  const [pullbackTolerance, setPullbackTolerance] = useState<number>(0.02)
  const [contractionRatio, setContractionRatio] = useState<number>(0.7)
  const [expansionRatio, setExpansionRatio] = useState<number>(1.5)
  const [minPullbackDays, setMinPullbackDays] = useState<number>(2)
  const [requireBounceUp, setRequireBounceUp] = useState<boolean>(true)
  const [maxStocks, setMaxStocks] = useState<number>(200)

  // 获取策略列表
  const { data: strategyListData, isLoading: listLoading } = useQuery({
    queryKey: ['strategies-list'],
    queryFn: async () => (await strategyApi.list()).data,
    staleTime: 300000,
  })

  const strategies = strategyListData?.strategies || []

  // 默认选中第一个策略
  if (!activeStrategyId && strategies.length > 0) {
    setActiveStrategyId(strategies[0].id)
  }

  const isParamsDirty = activeStrategyId === 'volume_pullback'

  const scanParams: StrategyScanParams = {
    trade_date: tradeDate,
    market,
    q: keyword.trim() || undefined,
    rally_days: rallyDays,
    min_rally_pct: minRallyPct,
    ma_period: maPeriod,
    pullback_tolerance: pullbackTolerance,
    contraction_ratio: contractionRatio,
    expansion_ratio: expansionRatio,
    min_pullback_days: minPullbackDays,
    require_bounce_up: requireBounceUp,
    max_stocks: maxStocks,
  }

  const { data, isLoading, refetch, isFetching, isError } = useQuery({
    queryKey: ['strategy-scan', activeStrategyId, scanParams],
    queryFn: async () => {
      const resp = await strategyApi.scan(activeStrategyId, scanParams)
      return resp.data
    },
    enabled: !!activeStrategyId,
    staleTime: 60000,
  })

  const items = data?.items || []

  const columns = [
    {
      title: '股票',
      dataIndex: 'symbol',
      width: 160,
      fixed: 'left' as const,
      sorter: (a: StrategyMatchItem, b: StrategyMatchItem) => a.symbol.localeCompare(b.symbol),
      render: (_: unknown, item: StrategyMatchItem) => (
        <Button
          type="text"
          size="small"
          onClick={() => navigate(`/stock?symbol=${encodeURIComponent(item.symbol)}`)}
        >
          {item.symbol} {item.name || ''}
        </Button>
      ),
    },
    {
      title: '市场',
      dataIndex: 'market',
      width: 80,
      sorter: (a: StrategyMatchItem, b: StrategyMatchItem) => a.market.localeCompare(b.market),
      render: (value: string) => {
        const label = value === 'sh' ? '沪市' : value === 'sz' ? '深市' : value === 'bj' ? '北交' : value
        const color = value === 'sh' ? 'red' : value === 'sz' ? 'arcoblue' : 'gray'
        return <Tag color={color}>{label}</Tag>
      },
    },
    {
      title: '最新价',
      dataIndex: 'latest_price',
      width: 90,
      sorter: (a: StrategyMatchItem, b: StrategyMatchItem) => (a.latest_price ?? 0) - (b.latest_price ?? 0),
      render: (value?: number) => displayNumber(value),
    },
    {
      title: '20日涨幅',
      dataIndex: 'rally_pct',
      width: 110,
      sorter: (a: StrategyMatchItem, b: StrategyMatchItem) => (a.rally_pct ?? 0) - (b.rally_pct ?? 0),
      defaultSortOrder: 'descend' as const,
      render: (value?: number) => (
        <span style={{ color: 'var(--color-up)', fontWeight: 600 }}>{displayNumber(value)}%</span>
      ),
    },
    {
      title: '峰值价',
      dataIndex: 'peak_price',
      width: 90,
      sorter: (a: StrategyMatchItem, b: StrategyMatchItem) => (a.peak_price ?? 0) - (b.peak_price ?? 0),
      render: (value?: number) => displayNumber(value),
    },
    {
      title: '峰值日期',
      dataIndex: 'peak_date',
      width: 110,
      sorter: (a: StrategyMatchItem, b: StrategyMatchItem) => String(a.peak_date ?? '').localeCompare(String(b.peak_date ?? '')),
    },
    {
      title: '回踩日期',
      dataIndex: 'touch_date',
      width: 110,
      sorter: (a: StrategyMatchItem, b: StrategyMatchItem) => String(a.touch_date ?? '').localeCompare(String(b.touch_date ?? '')),
    },
    {
      title: '缩量比',
      dataIndex: 'contraction_ratio',
      width: 90,
      sorter: (a: StrategyMatchItem, b: StrategyMatchItem) => (a.contraction_ratio ?? 0) - (b.contraction_ratio ?? 0),
      render: (value?: number) => (
        <Badge
          status={value !== null && value !== undefined && value <= 0.5 ? 'success' : 'default'}
          text={displayNumber(value, 2)}
        />
      ),
    },
    {
      title: '放量比',
      dataIndex: 'expansion_ratio',
      width: 90,
      sorter: (a: StrategyMatchItem, b: StrategyMatchItem) => (a.expansion_ratio ?? 0) - (b.expansion_ratio ?? 0),
      render: (value?: number) => (
        <span style={{ color: 'var(--color-up)', fontWeight: 600 }}>{displayNumber(value, 2)}</span>
      ),
    },
    {
      title: '今日量',
      dataIndex: 'latest_volume',
      width: 110,
      sorter: (a: StrategyMatchItem, b: StrategyMatchItem) => (a.latest_volume ?? 0) - (b.latest_volume ?? 0),
      render: (value?: number) => displayAmount(value),
    },
    {
      title: '收阳',
      dataIndex: 'bounce_up',
      width: 70,
      render: (value: boolean) => (value ? <Tag color="red" size="small">阳</Tag> : <Tag color="green" size="small">阴</Tag>),
    },
    {
      title: '策略描述',
      dataIndex: 'description',
      width: 320,
      ellipsis: true,
    },
  ]

  const activeStrategy: StrategyInfo | undefined = strategies.find((s) => s.id === activeStrategyId)

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h2 className="page-header-title">量化策略</h2>
          <div style={{ marginTop: 4, color: 'var(--text-muted)', fontSize: 13 }}>
            基于技术形态的全市场选股策略，支持参数自定义
          </div>
        </div>
        <Button
          type="primary"
          icon={<IconRefresh />}
          loading={isFetching}
          onClick={() => refetch()}
          disabled={!activeStrategyId}
        >
          重新扫描
        </Button>
      </div>

      {/* 策略卡片列表 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16, marginBottom: 24 }}>
        {listLoading ? (
          <Card><Spin /></Card>
        ) : (
          strategies.map((s) => {
            const isActive = s.id === activeStrategyId
            return (
              <Card
                key={s.id}
                className="card-glow-hover"
                hoverable
                style={{
                  cursor: 'pointer',
                  borderColor: isActive ? 'var(--border-accent)' : 'var(--border-subtle)',
                  borderWidth: isActive ? 2 : 1,
                }}
                onClick={() => setActiveStrategyId(s.id)}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <IconThunderbolt style={{ color: 'var(--color-up)', fontSize: 18 }} />
                  <span style={{ fontSize: 16, fontWeight: 600 }}>{s.name}</span>
                  {isActive && <Tag color="arcoblue" size="small">当前</Tag>}
                </div>
                <div style={{ color: 'var(--text-muted)', fontSize: 13, lineHeight: 1.6, minHeight: 42 }}>
                  {s.description}
                </div>
                <div style={{ marginTop: 8, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {s.params.slice(0, 4).map((p) => (
                    <Tag key={p.name} size="small" color="gray">
                      {p.name}: {String(p.default)}
                    </Tag>
                  ))}
                </div>
              </Card>
            )
          })
        )}
      </div>

      {/* 筛选条件 */}
      {activeStrategy && (
        <Card className="card-glow-hover" style={{ marginBottom: 20 }}>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            <Input
              value={tradeDate}
              onChange={setTradeDate}
              placeholder="YYYY-MM-DD"
              style={{ width: 150 }}
            />
            <Select value={market} onChange={setMarket} style={{ width: 120 }}>
              <Select.Option value="all">全部市场</Select.Option>
              <Select.Option value="sh">沪市</Select.Option>
              <Select.Option value="sz">深市</Select.Option>
              <Select.Option value="bj">北交所</Select.Option>
            </Select>
            <Input.Search
              value={keyword}
              onChange={setKeyword}
              placeholder="搜索代码或名称"
              style={{ width: 220 }}
              allowClear
            />
            <Tag color="orangered">{data?.total ?? 0} 只命中</Tag>
            <Tag color="gray">数据日期 {data?.trade_date || tradeDate}</Tag>
          </div>

          {/* 策略参数（仅放量回踩展示） */}
          {isParamsDirty && (
            <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--border-subtle)', display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
              <span style={{ fontSize: 13, color: 'var(--text-muted)', fontWeight: 600 }}>策略参数：</span>
              <ParamNumber label="回看天数" value={rallyDays} onChange={setRallyDays} min={5} max={60} />
              <ParamNumber label="最小涨幅%" value={minRallyPct} onChange={setMinRallyPct} min={0} max={500} />
              <ParamNumber label="均线周期" value={maPeriod} onChange={setMaPeriod} min={2} max={60} />
              <ParamNumber label="回踩容差" value={pullbackTolerance} onChange={setPullbackTolerance} min={0} max={0.2} step={0.01} />
              <ParamNumber label="缩量比" value={contractionRatio} onChange={setContractionRatio} min={0} max={2} step={0.05} />
              <ParamNumber label="放量比" value={expansionRatio} onChange={setExpansionRatio} min={1} max={10} step={0.1} />
              <ParamNumber label="最少回调日" value={minPullbackDays} onChange={setMinPullbackDays} min={1} max={20} />
              <ParamNumber label="扫描上限" value={maxStocks} onChange={setMaxStocks} min={10} max={1000} />
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>要求收阳</span>
                <Switch checked={requireBounceUp} onChange={setRequireBounceUp} size="small" />
              </div>
              <Button type="primary" icon={<IconSearch />} loading={isFetching} onClick={() => refetch()}>
                扫描
              </Button>
            </div>
          )}
        </Card>
      )}

      {/* 结果表格 */}
      <Card className="card-glow-hover">
        {isLoading ? (
          <div style={{ textAlign: 'center', padding: 64 }}>
            <Spin size={40} />
            <div style={{ marginTop: 16, color: 'var(--text-dim)' }}>
              正在扫描全市场「{activeStrategy?.name}」策略...
            </div>
          </div>
        ) : isError ? (
          <Empty
            description={
              <div>
                <div style={{ fontSize: 16, fontWeight: 500, marginBottom: 8 }}>扫描失败</div>
                <Button type="primary" onClick={() => refetch()}>重新加载</Button>
              </div>
            }
          />
        ) : items.length === 0 ? (
          <Empty
            description={
              <div>
                <div style={{ fontSize: 16, fontWeight: 500, marginBottom: 8 }}>
                  {data?.error ? '数据获取失败' : '暂无符合条件的股票'}
                </div>
                <div style={{ color: 'var(--text-dim)', marginBottom: 12 }}>
                  {data?.error || '请尝试调整策略参数或市场范围后重新扫描'}
                </div>
                <Button type="primary" onClick={() => refetch()}>重新扫描</Button>
              </div>
            }
          />
        ) : (
          <Table
            rowKey={(record) => record.symbol}
            columns={columns}
            data={items}
            loading={isFetching}
            pagination={{ pageSize: 20, showTotal: true, sizeCanChange: true }}
            scroll={{ x: 1700 }}
          />
        )}
      </Card>
    </div>
  )
}

function ParamNumber({
  label,
  value,
  onChange,
  min,
  max,
  step,
}: {
  label: string
  value: number
  onChange: (v: number) => void
  min?: number
  max?: number
  step?: number
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
        style={{ width: 80 }}
        size="small"
      />
    </div>
  )
}
