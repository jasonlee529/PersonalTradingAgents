import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, Empty, Input, Select, Spin, Table, Tag, Message } from '@arco-design/web-react'
import { IconRefresh } from '@arco-design/web-react/icon'
import { useQuery } from '@tanstack/react-query'
import { stockApi, type LimitUpStockItem, type LimitUpStockListResponse } from '../api/client'

function today(): string {
  return new Date().toISOString().slice(0, 10)
}

function displayNumber(value?: number | null, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return Number(value).toFixed(digits)
}

function displayAmount(value?: number | null): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  const number = Number(value)
  if (Math.abs(number) >= 100000000) return `${(number / 100000000).toFixed(2)}亿`
  if (Math.abs(number) >= 10000) return `${(number / 10000).toFixed(2)}万`
  return number.toFixed(2)
}

function marketLabel(market: string): string {
  if (market === 'sh') return '沪市主板'
  if (market === 'sz') return '深市主板'
  return market || '-'
}

export default function LimitUpPage() {
  const navigate = useNavigate()
  const [tradeDate, setTradeDate] = useState(today())
  const [market, setMarket] = useState('all')
  const [keyword, setKeyword] = useState('')

  const query = useQuery({
    queryKey: ['limit-up-stocks', tradeDate, market, keyword],
    queryFn: async () => {
      const resp = await stockApi.limitUp({
        trade_date: tradeDate,
        market,
        q: keyword.trim() || undefined,
        limit: 500,
        offset: 0,
      })
      return resp.data as LimitUpStockListResponse
    },
    enabled: !!tradeDate,
    staleTime: 30000,
  })

  const items = query.data?.items || []

  const openStock = (symbol: string) => {
    navigate(`/stock?symbol=${encodeURIComponent(symbol)}`)
  }

  const columns = [
    {
      title: '股票',
      dataIndex: 'symbol',
      width: 170,
      render: (_: unknown, item: LimitUpStockItem) => (
        <Button type="text" size="small" onClick={() => openStock(item.symbol)}>
          {item.symbol} {item.name || ''}
        </Button>
      ),
    },
    {
      title: '市场',
      dataIndex: 'market',
      width: 110,
      render: (value: string) => <Tag color={value === 'sh' ? 'red' : 'arcoblue'}>{marketLabel(value)}</Tag>,
    },
    {
      title: '最新价',
      dataIndex: 'price',
      width: 100,
      render: (value?: number | null) => displayNumber(value),
    },
    {
      title: '涨跌幅',
      dataIndex: 'change_pct',
      width: 100,
      render: (value?: number | null) => (
        <span style={{ color: 'var(--color-up)', fontWeight: 600 }}>{displayNumber(value)}%</span>
      ),
    },
    {
      title: '成交额',
      dataIndex: 'turnover',
      width: 110,
      render: (value?: number | null) => displayAmount(value),
    },
    {
      title: '成交量',
      dataIndex: 'volume',
      width: 110,
      render: (value?: number | null) => value?.toLocaleString() || '-',
    },
    {
      title: '换手率',
      dataIndex: 'turnover_rate',
      width: 100,
      render: (value?: number | null) => value === null || value === undefined ? '-' : `${displayNumber(value)}%`,
    },
    {
      title: '首次封板',
      dataIndex: 'first_limit_up_time',
      width: 110,
      render: (value?: string | null) => value || '-',
    },
    {
      title: '最后封板',
      dataIndex: 'last_limit_up_time',
      width: 110,
      render: (value?: string | null) => value || '-',
    },
    {
      title: '封单金额',
      dataIndex: 'seal_amount',
      width: 110,
      render: (value?: number | null) => displayAmount(value),
    },
    {
      title: '连板',
      dataIndex: 'consecutive_days',
      width: 80,
      render: (value?: number | null) => value ? `${value}板` : '-',
    },
    {
      title: '原因/行业',
      dataIndex: 'reason',
      width: 160,
      render: (value?: string) => value || '-',
    },
  ]

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h2 className="page-header-title">涨停池</h2>
          <div style={{ marginTop: 4, color: 'var(--text-muted)', fontSize: 13 }}>
            每日 A 股沪深主板涨停股票筛选
          </div>
        </div>
        <Button
          type="primary"
          icon={<IconRefresh />}
          loading={query.isFetching}
          onClick={() => {
            query.refetch()
            Message.info('正在刷新涨停池')
          }}
        >
          刷新
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
          <Select value={market} onChange={setMarket} style={{ width: 150 }}>
            <Select.Option value="all">全部主板</Select.Option>
            <Select.Option value="sh">沪市主板</Select.Option>
            <Select.Option value="sz">深市主板</Select.Option>
          </Select>
          <Input.Search
            value={keyword}
            onChange={setKeyword}
            placeholder="搜索代码或名称"
            style={{ width: 240 }}
            allowClear
          />
          <Tag color="orangered">{query.data?.total ?? 0} 只</Tag>
          <Tag color="gray">数据日期 {query.data?.trade_date || tradeDate}</Tag>
        </div>
      </Card>

      <Card className="card-glow-hover">
        {query.isLoading ? (
          <div style={{ textAlign: 'center', padding: 64 }}>
            <Spin size={40} />
            <div style={{ marginTop: 16, color: 'var(--text-dim)' }}>加载涨停股列表...</div>
          </div>
        ) : query.isError ? (
          <Empty
            description={
              <div>
                <div style={{ fontSize: 16, fontWeight: 500, marginBottom: 8 }}>加载失败</div>
                <div style={{ color: 'var(--text-dim)', marginBottom: 12 }}>无法获取涨停股列表，请稍后重试</div>
                <Button type="primary" onClick={() => query.refetch()}>重新加载</Button>
              </div>
            }
          />
        ) : items.length === 0 ? (
          <Empty
            description={
              <div>
                <div style={{ fontSize: 16, fontWeight: 500, marginBottom: 8 }}>暂无匹配结果</div>
                <div style={{ color: 'var(--text-dim)' }}>请调整交易日、市场范围或搜索关键字</div>
              </div>
            }
          />
        ) : (
          <Table
            rowKey="symbol"
            columns={columns}
            data={items}
            loading={query.isFetching}
            pagination={{ pageSize: 20, showTotal: true }}
            scroll={{ x: 1450 }}
          />
        )}
      </Card>
    </div>
  )
}
