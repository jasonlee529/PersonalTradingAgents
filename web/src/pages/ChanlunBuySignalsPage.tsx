import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, Empty, Input, Select, Spin, Table, Tag, Badge } from '@arco-design/web-react'
import { IconRefresh } from '@arco-design/web-react/icon'
import { useQuery } from '@tanstack/react-query'
import { chanlunApi, type ChanlunBuySignalItem } from '../api/client'

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
  return num.toFixed(2)
}

function getSignalTypeTagColor(signalType: string): string {
  switch (signalType) {
    case 'type1':
      return 'red'
    case 'type2':
      return 'arcoblue'
    case 'type3':
      return 'green'
    default:
      return 'gray'
  }
}

function getConfidenceBadge(score: number): React.ReactNode {
  let status: 'success' | 'warning' | 'default' = 'default'
  if (score >= 0.7) status = 'success'
  else if (score >= 0.6) status = 'warning'
  return <Badge status={status} text={`${Math.round(score * 100)}%`} />
}

export default function ChanlunBuySignalsPage() {
  const navigate = useNavigate()
  const [tradeDate, setTradeDate] = useState(today())
  const [market, setMarket] = useState('all')
  const [signalType, setSignalType] = useState('all')
  const [keyword, setKeyword] = useState('')

  const { data, isLoading, refetch, isFetching, isError } = useQuery({
    queryKey: ['chanlun-buy-signals', tradeDate, market, signalType, keyword],
    queryFn: async () => {
      const resp = await chanlunApi.getBuySignals({
        trade_date: tradeDate,
        market,
        signal_type: signalType,
        q: keyword.trim() || undefined,
      })
      return resp.data
    },
    enabled: !!tradeDate,
    staleTime: 60000,
  })

  const items = data?.items || []

  const columns = [
    {
      title: '股票',
      dataIndex: 'symbol',
      width: 160,
      fixed: 'left' as const,
      render: (_: unknown, item: ChanlunBuySignalItem) => (
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
      title: '信号类型',
      dataIndex: 'signal_type_label',
      width: 100,
      render: (_: unknown, item: ChanlunBuySignalItem) => (
        <Tag color={getSignalTypeTagColor(item.signal_type)}>
          {item.signal_type_label}
        </Tag>
      ),
    },
    {
      title: '市场',
      dataIndex: 'market',
      width: 80,
      render: (value: string) => (
        <Tag color={value === 'sh' ? 'red' : 'arcoblue'}>
          {value === 'sh' ? '沪市' : '深市'}
        </Tag>
      ),
    },
    {
      title: '最新价',
      dataIndex: 'price',
      width: 90,
      render: (value?: number) => displayNumber(value),
    },
    {
      title: '涨跌幅',
      dataIndex: 'change_pct',
      width: 100,
      render: (value?: number) => {
        const num = Number(value)
        const color = num > 0 ? 'var(--color-up)' : num < 0 ? 'var(--color-down)' : 'inherit'
        return <span style={{ color, fontWeight: 600 }}>{displayNumber(value)}%</span>
      },
    },
    {
      title: '成交额',
      dataIndex: 'turnover',
      width: 120,
      render: (value?: number) => displayAmount(value),
    },
    {
      title: '换手率',
      dataIndex: 'turnover_rate',
      width: 90,
      render: (value?: number) => (value === null || value === undefined) ? '-' : `${displayNumber(value)}%`,
    },
    {
      title: '置信度',
      dataIndex: 'confidence_score',
      width: 100,
      render: (_: unknown, item: ChanlunBuySignalItem) => getConfidenceBadge(item.confidence_score),
    },
    {
      title: '中枢级别',
      dataIndex: 'pivot_level',
      width: 90,
    },
    {
      title: '背离类型',
      dataIndex: 'divergence_type',
      width: 130,
    },
    {
      title: '技术指标',
      dataIndex: 'macd_divergence',
      width: 130,
      render: (_: unknown, item: ChanlunBuySignalItem) => (
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {item.macd_divergence && <Tag color="orange" size="small">MACD</Tag>}
          {item.kdj_divergence && <Tag color="arcoblue" size="small">KDJ</Tag>}
          {item.rsi_divergence && <Tag color="green" size="small">RSI</Tag>}
        </div>
      ),
    },
    {
      title: '信号描述',
      dataIndex: 'description',
      width: 280,
      ellipsis: true,
    },
  ]

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h2 className="page-header-title">缠论买入信号</h2>
          <div style={{ marginTop: 4, color: 'var(--text-muted)', fontSize: 13 }}>
            基于缠论理论（一买、二买、三买）筛选出的潜在买入机会
          </div>
        </div>
        <Button
          type="primary"
          icon={<IconRefresh />}
          loading={isFetching}
          onClick={() => refetch()}
        >
          刷新数据
        </Button>
      </div>

      <Card className="card-glow-hover" style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <Input
            value={tradeDate}
            onChange={setTradeDate}
            placeholder="YYYY-MM-DD"
            style={{ width: 160 }}
          />
          <Select value={market} onChange={setMarket} style={{ width: 140 }}>
            <Select.Option value="all">全部市场</Select.Option>
            <Select.Option value="sh">沪市</Select.Option>
            <Select.Option value="sz">深市</Select.Option>
          </Select>
          <Select value={signalType} onChange={setSignalType} style={{ width: 160 }}>
            <Select.Option value="all">全部信号</Select.Option>
            <Select.Option value="type1">一买（下跌背驰）</Select.Option>
            <Select.Option value="type2">二买（回调确认）</Select.Option>
            <Select.Option value="type3">三买（突破回抽）</Select.Option>
          </Select>
          <Input.Search
            value={keyword}
            onChange={setKeyword}
            placeholder="搜索代码或名称"
            style={{ width: 240 }}
            allowClear
          />
          <Tag color="orangered">{data?.total ?? 0} 个信号</Tag>
          <Tag color="gray">数据日期 {data?.trade_date || tradeDate}</Tag>
        </div>
      </Card>

      <Card className="card-glow-hover">
        {isLoading ? (
          <div style={{ textAlign: 'center', padding: 64 }}>
            <Spin size={40} />
            <div style={{ marginTop: 16, color: 'var(--text-dim)' }}>正在扫描缠论信号...</div>
          </div>
        ) : isError ? (
          <Empty
            description={
              <div>
                <div style={{ fontSize: 16, fontWeight: 500, marginBottom: 8 }}>加载失败</div>
                <Button type="primary" onClick={() => refetch()}>重新加载</Button>
              </div>
            }
          />
        ) : items.length === 0 ? (
          <Empty
            description={
              <div>
                <div style={{ fontSize: 16, fontWeight: 500, marginBottom: 8 }}>
                  {data?.error ? '数据获取失败' : '暂无符合条件的缠论买入信号'}
                </div>
                <div style={{ color: 'var(--text-dim)', marginBottom: 12 }}>
                  {data?.error || '请尝试调整筛选条件或稍后再试'}
                </div>
                <Button type="primary" onClick={() => refetch()}>刷新数据</Button>
              </div>
            }
          />
        ) : (
          <Table
            rowKey={(record) => `${record.symbol}-${record.signal_type}`}
            columns={columns}
            data={items}
            loading={isFetching}
            pagination={{ pageSize: 20, showTotal: true, sizeCanChange: true }}
            scroll={{ x: 1800 }}
          />
        )}
      </Card>
    </div>
  )
}
