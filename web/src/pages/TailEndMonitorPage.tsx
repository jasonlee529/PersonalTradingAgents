import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, Empty, Input, InputNumber, Spin, Table, Tag, Message } from '@arco-design/web-react'
import { IconRefresh, IconSearch } from '@arco-design/web-react/icon'
import { useQuery } from '@tanstack/react-query'
import { tailEndApi, type TailEndItem, type TailEndScanParams } from '../api/client'
import KlineChart from '../components/KlineChart'

function displayNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return Number(value).toFixed(digits)
}

function displayMcap(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return `${Number(value).toFixed(1)}亿`
}

export default function TailEndMonitorPage() {
  const navigate = useNavigate()

  // 筛选参数
  const [turnoverMin, setTurnoverMin] = useState<number>(6)
  const [turnoverMax, setTurnoverMax] = useState<number>(15)
  const [mcapMin, setMcapMin] = useState<number>(50)
  const [mcapMax, setMcapMax] = useState<number>(300)
  const [changeMin, setChangeMin] = useState<number>(3)
  const [changeMax, setChangeMax] = useState<number>(6)
  const [volRatioMin, setVolRatioMin] = useState<number>(2)
  const [volRatioMax, setVolRatioMax] = useState<number>(5)
  const [keyword, setKeyword] = useState('')

  const scanParams: TailEndScanParams = {
    turnover_min: turnoverMin,
    turnover_max: turnoverMax,
    mcap_min: mcapMin,
    mcap_max: mcapMax,
    change_min: changeMin,
    change_max: changeMax,
    vol_ratio_min: volRatioMin,
    vol_ratio_max: volRatioMax,
    q: keyword.trim() || undefined,
  }

  const { data, isLoading, refetch, isFetching, isError } = useQuery({
    queryKey: ['tail-end-scan', scanParams],
    queryFn: async () => {
      const resp = await tailEndApi.scan(scanParams)
      return resp.data
    },
    staleTime: 30000,
    enabled: false, // 手动触发
  })

  const items = data?.items || []

  const openStock = (symbol: string) => {
    navigate(`/stock?symbol=${encodeURIComponent(symbol)}`)
  }

  const columns = [
    {
      title: '股票',
      dataIndex: 'symbol',
      width: 160,
      fixed: 'left' as const,
      render: (_: unknown, item: TailEndItem) => (
        <Button type="text" size="small" onClick={() => openStock(item.symbol)}>
          {item.symbol} {item.name}
        </Button>
      ),
    },
    {
      title: '市场',
      dataIndex: 'market',
      width: 70,
      render: (value: string) => {
        const label = value === 'sh' ? '沪市' : value === 'sz' ? '深市' : value
        const color = value === 'sh' ? 'red' : 'arcoblue'
        return <Tag color={color} size="small">{label}</Tag>
      },
    },
    {
      title: '最新价',
      dataIndex: 'price',
      width: 85,
      sorter: (a: TailEndItem, b: TailEndItem) => a.price - b.price,
      render: (value: number) => displayNumber(value),
    },
    {
      title: '全天涨幅',
      dataIndex: 'change_pct',
      width: 95,
      sorter: (a: TailEndItem, b: TailEndItem) => a.change_pct - b.change_pct,
      render: (value: number) => (
        <span style={{ color: value >= 0 ? 'var(--color-up)' : 'var(--color-down)', fontWeight: 600 }}>
          {value >= 0 ? '+' : ''}{displayNumber(value)}%
        </span>
      ),
    },
    {
      title: '14:30后涨幅',
      dataIndex: 'change_since_1430',
      width: 110,
      defaultSortOrder: 'descend' as const,
      sorter: (a: TailEndItem, b: TailEndItem) => (a.change_since_1430 ?? 0) - (b.change_since_1430 ?? 0),
      render: (value: number | null) => (
        <span style={{
          color: 'var(--color-up)',
          fontWeight: 700,
          fontSize: 14,
          background: 'rgba(255, 59, 48, 0.08)',
          padding: '2px 8px',
          borderRadius: 4,
        }}>
          {value !== null && value !== undefined ? `+${displayNumber(value)}%` : '-'}
        </span>
      ),
    },
    {
      title: '换手率',
      dataIndex: 'turnover_rate',
      width: 85,
      sorter: (a: TailEndItem, b: TailEndItem) => (a.turnover_rate ?? 0) - (b.turnover_rate ?? 0),
      render: (value: number | null) => value !== null ? `${displayNumber(value)}%` : '-',
    },
    {
      title: '市值',
      dataIndex: 'total_market_cap',
      width: 90,
      sorter: (a: TailEndItem, b: TailEndItem) => (a.total_market_cap ?? 0) - (b.total_market_cap ?? 0),
      render: (value: number | null) => displayMcap(value),
    },
    {
      title: '量比',
      dataIndex: 'volume_ratio',
      width: 75,
      sorter: (a: TailEndItem, b: TailEndItem) => (a.volume_ratio ?? 0) - (b.volume_ratio ?? 0),
      render: (value: number | null) => (
        <span style={{ fontWeight: 600 }}>{value !== null ? displayNumber(value, 1) : '-'}</span>
      ),
    },
    {
      title: '涨停标记',
      dataIndex: 'limit_up_date',
      width: 110,
      render: (value: string) => value ? (
        <Tag color="red" size="small">{value}</Tag>
      ) : (
        <Tag color="gray" size="small">无</Tag>
      ),
    },
    {
      title: '均价线',
      dataIndex: 'above_vwap',
      width: 80,
      render: (value: boolean) => value ? (
        <Tag color="green" size="small">✓ 达标</Tag>
      ) : (
        <Tag color="gray" size="small">-</Tag>
      ),
    },
  ]

  const handleScan = () => {
    refetch()
    Message.info('正在执行尾盘扫描...')
  }

  return (
    <div>
      {/* 页面标题 */}
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h2 className="page-header-title">尾盘策略</h2>
          <div style={{ marginTop: 4, color: 'var(--text-muted)', fontSize: 13 }}>
            尾盘时段实时监控，多维度筛选潜力股
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {data?.scan_time && (
            <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>
              扫描时间: {data.scan_time}
            </span>
          )}
          <Button
            type="primary"
            icon={<IconRefresh />}
            loading={isFetching}
            onClick={handleScan}
          >
            开始扫描
          </Button>
        </div>
      </div>

      {/* 筛选参数 */}
      <Card className="card-glow-hover" style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
          <ParamRange
            label="换手率(%)"
            min={turnoverMin}
            max={turnoverMax}
            onMinChange={setTurnoverMin}
            onMaxChange={setTurnoverMax}
            step={1}
          />
          <ParamRange
            label="市值(亿)"
            min={mcapMin}
            max={mcapMax}
            onMinChange={setMcapMin}
            onMaxChange={setMcapMax}
            step={10}
          />
          <ParamRange
            label="14:30后涨幅(%)"
            min={changeMin}
            max={changeMax}
            onMinChange={setChangeMin}
            onMaxChange={setChangeMax}
            step={0.5}
          />
          <ParamRange
            label="量比"
            min={volRatioMin}
            max={volRatioMax}
            onMinChange={setVolRatioMin}
            onMaxChange={setVolRatioMax}
            step={0.5}
          />
          <Input.Search
            value={keyword}
            onChange={setKeyword}
            placeholder="搜索代码或名称"
            style={{ width: 200 }}
            allowClear
          />
          <Button
            type="primary"
            icon={<IconSearch />}
            loading={isFetching}
            onClick={handleScan}
          >
            扫描
          </Button>
        </div>
        <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Tag color="blue">主板限定</Tag>
          <Tag color="blue">排除ST</Tag>
          <Tag color="blue">近20日有涨停</Tag>
          <Tag color="blue">全天在均价线之上</Tag>
          {data && <Tag color="orangered">{data.total} 只命中</Tag>}
        </div>
      </Card>

      {/* 结果表格 */}
      <Card className="card-glow-hover">
        {!data && !isLoading && !isError ? (
          <Empty
            description={
              <div>
                <div style={{ fontSize: 16, fontWeight: 500, marginBottom: 8 }}>
                  点击"开始扫描"执行尾盘策略
                </div>
                <div style={{ color: 'var(--text-dim)' }}>
                  筛选条件：换手率{turnoverMin}-{turnoverMax}%，市值{mcapMin}-{mcapMax}亿，
                  量比{volRatioMin}-{volRatioMax}，14:30后涨幅{changeMin}-{changeMax}%
                </div>
              </div>
            }
          />
        ) : isLoading ? (
          <div style={{ textAlign: 'center', padding: 64 }}>
            <Spin size={40} />
            <div style={{ marginTop: 16, color: 'var(--text-dim)' }}>
              正在扫描全市场尾盘数据...
            </div>
          </div>
        ) : isError ? (
          <Empty
            description={
              <div>
                <div style={{ fontSize: 16, fontWeight: 500, marginBottom: 8 }}>扫描失败</div>
                <Button type="primary" onClick={handleScan}>重新扫描</Button>
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
                  {data?.error || '请尝试调整筛选参数后重新扫描'}
                </div>
                <Button type="primary" onClick={handleScan}>重新扫描</Button>
              </div>
            }
          />
        ) : (
          <Table
            rowKey="symbol"
            columns={columns}
            data={items}
            loading={isFetching}
            pagination={{ pageSize: 20, showTotal: true, sizeCanChange: true }}
            scroll={{ x: 1200 }}
            expandedRowRender={(record: TailEndItem) => {
              if (!record.kline_3d || record.kline_3d.length === 0) {
                return <div style={{ padding: 16, color: 'var(--text-dim)' }}>暂无K线数据</div>
              }
              return (
                <div style={{ padding: '8px 16px', maxWidth: 800 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8, color: 'var(--text-secondary)' }}>
                    近3日走势
                  </div>
                  <KlineChart data={record.kline_3d} height={200} />
                </div>
              )
            }}
          />
        )}
      </Card>
    </div>
  )
}

function ParamRange({
  label,
  min,
  max,
  onMinChange,
  onMaxChange,
  step,
}: {
  label: string
  min: number
  max: number
  onMinChange: (v: number) => void
  onMaxChange: (v: number) => void
  step?: number
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <span style={{ fontSize: 13, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{label}</span>
      <InputNumber
        value={min}
        onChange={(v) => onMinChange(typeof v === 'number' ? v : min)}
        step={step ?? 1}
        style={{ width: 70 }}
        size="small"
      />
      <span style={{ color: 'var(--text-dim)' }}>~</span>
      <InputNumber
        value={max}
        onChange={(v) => onMaxChange(typeof v === 'number' ? v : max)}
        step={step ?? 1}
        style={{ width: 70 }}
        size="small"
      />
    </div>
  )
}
