import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Button, Input, Select, Form, Message, Tag } from '@arco-design/web-react'
import DataList from '../components/DataList'
import { IconPlus, IconRefresh, IconDelete, IconEye, IconCalendar, IconEdit, IconCheck, IconClose } from '@arco-design/web-react/icon'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { portfolioApi, type TradeRecord } from '../api/client'
import { usePortfolioStore, type HoldingDetail } from '../store/usePortfolioStore'
import EmptyState from '../components/EmptyState'

const FormItem = Form.Item

const statusMap: Record<string, string> = {
  pending: '待收集',
  collecting: '收集中',
  ready: '就绪',
  error: '错误',
}

const statusColor: Record<string, string> = {
  pending: 'gray',
  collecting: 'blue',
  ready: 'green',
  error: 'red',
}

const actionLabels: Record<string, string> = {
  buy: '买入',
  sell: '卖出',
  add: '加仓',
  reduce: '减仓',
  clear: '清仓',
  hold: '持有',
  watch: '观察',
}

const actionTagStyle: Record<string, { bg: string; color: string; border: string }> = {
  buy:    { bg: '#e8f5e9', color: '#2e7d32', border: '#a5d6a7' },
  sell:   { bg: '#ffebee', color: '#c62828', border: '#ef9a9a' },
  add:    { bg: '#e8f5e9', color: '#2e7d32', border: '#a5d6a7' },
  reduce: { bg: '#fff3e0', color: '#e65100', border: '#ffcc80' },
  clear:  { bg: '#ffebee', color: '#c62828', border: '#ef9a9a' },
  hold:   { bg: '#e3f2fd', color: '#1565c0', border: '#90caf9' },
  watch:  { bg: '#f5f5f5', color: '#616161', border: '#e0e0e0' },
}

export default function PortfolioPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { setHoldings, setSelectedSymbol } = usePortfolioStore()
  const [form] = Form.useForm()
  const [tradeFilterForm] = Form.useForm()
  const [tradeSymbolFilter, setTradeSymbolFilter] = useState('')
  const [editingSymbol, setEditingSymbol] = useState<string | null>(null)
  const [editQty, setEditQty] = useState('')
  const [editCost, setEditCost] = useState('')
  const [editPnl, setEditPnl] = useState('')

  const { data } = useQuery({
    queryKey: ['holdings'],
    queryFn: async () => {
      const resp = await portfolioApi.list()
      return resp.data as HoldingDetail[]
    },
  })

  const { data: tradesData } = useQuery({
    queryKey: ['trades', tradeSymbolFilter],
    queryFn: async () => {
      const resp = await portfolioApi.trades({ symbol: tradeSymbolFilter || undefined, limit: 50 })
      return resp.data as TradeRecord[]
    },
  })

  useEffect(() => {
    if (data) setHoldings(data)
  }, [data, setHoldings])

  const addMutation = useMutation({
    mutationFn: portfolioApi.add,
    onSuccess: () => {
      Message.success('添加成功，正在后台收集数据...')
      form.resetFields()
      queryClient.invalidateQueries({ queryKey: ['holdings'] })
    },
    onError: () => Message.error('添加失败'),
  })

  const removeMutation = useMutation({
    mutationFn: ({ symbol }: { symbol: string }) => portfolioApi.remove(symbol),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['holdings'] }),
  })

  const refreshMutation = useMutation({
    mutationFn: portfolioApi.refreshPrices,
    onSuccess: () => {
      Message.success('价格已刷新')
      queryClient.invalidateQueries({ queryKey: ['holdings'] })
    },
  })

  const updatePositionMutation = useMutation({
    mutationFn: ({ symbol, quantity, avg_cost, unrealized_pnl }: { symbol: string; quantity: number; avg_cost: number; unrealized_pnl?: number }) =>
      portfolioApi.updatePosition(symbol, { quantity, avg_cost, unrealized_pnl: unrealized_pnl ?? null }),
    onSuccess: () => {
      Message.success('持仓已更新')
      setEditingSymbol(null)
      setEditQty('')
      setEditCost('')
      setEditPnl('')
      queryClient.invalidateQueries({ queryKey: ['holdings'] })
    },
    onError: () => Message.error('更新失败'),
  })

  const startEdit = (row: HoldingDetail) => {
    setEditingSymbol(row.holding.symbol)
    setEditQty(String(row.position?.quantity ?? 0))
    setEditCost(String(row.position?.avg_cost ?? 0))
    setEditPnl(row.position?.unrealized_pnl != null ? String(row.position.unrealized_pnl) : '')
  }

  const cancelEdit = () => {
    setEditingSymbol(null)
    setEditQty('')
    setEditCost('')
    setEditPnl('')
  }

  const saveEdit = (symbol: string) => {
    const qty = parseInt(editQty, 10)
    const cost = parseFloat(editCost)
    if (Number.isNaN(qty) || qty < 0) {
      Message.warning('数量不合法')
      return
    }
    if (Number.isNaN(cost) || cost < 0) {
      Message.warning('成本价不合法')
      return
    }
    const pnlVal = editPnl.trim() !== '' ? parseFloat(editPnl) : undefined
    if (editPnl.trim() !== '' && (Number.isNaN(pnlVal!) || pnlVal === undefined)) {
      Message.warning('盈亏不合法')
      return
    }
    updatePositionMutation.mutate({ symbol, quantity: qty, avg_cost: cost, unrealized_pnl: pnlVal })
  }

  const tradeColumns = [
    {
      title: '日期',
      dataIndex: 'recorded_at',
      width: 160,
      render: (value: string) => value ? new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '-',
    },
    {
      title: '股票',
      dataIndex: 'symbol',
      width: 90,
      render: (value: string) => <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{value}</span>,
    },
    {
      title: '操作',
      dataIndex: 'action',
      width: 80,
      render: (value: string) => {
        const s = actionTagStyle[value] || actionTagStyle.watch
        return (
          <span style={{
            display: 'inline-block',
            padding: '2px 8px',
            borderRadius: 4,
            fontSize: 12,
            fontWeight: 600,
            background: s.bg,
            color: s.color,
            border: `1px solid ${s.border}`,
            whiteSpace: 'nowrap',
          }}>
            {actionLabels[value] || value}
          </span>
        )
      },
    },
    {
      title: '数量',
      dataIndex: 'quantity',
      width: 80,
      render: (value: number) => <span style={{ fontFamily: 'var(--font-mono)' }}>{value?.toLocaleString() ?? '-'}</span>,
    },
    {
      title: '价格',
      dataIndex: 'price',
      width: 90,
      render: (value: number) => <span style={{ fontFamily: 'var(--font-mono)' }}>{value?.toFixed(2) ?? '-'}</span>,
    },
    {
      title: '金额',
      dataIndex: 'amount',
      width: 100,
      render: (value: number) => <span style={{ fontFamily: 'var(--font-mono)' }}>{value?.toFixed(2) ?? '-'}</span>,
    },
    {
      title: '持仓变化',
      width: 120,
      render: (_: unknown, row: TradeRecord) => (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>
          {row.old_quantity} → {row.new_quantity}
        </span>
      ),
    },
    {
      title: '理由',
      dataIndex: 'reason',
      render: (value: string) => value || '-',
    },
  ]

  const columns = [
    { title: '代码', dataIndex: 'symbol', width: 80, render: (_: unknown, row: HoldingDetail) => (
      <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 13, color: 'var(--text-primary)' }}>{row.holding.symbol}</span>
    )},
    { title: '名称', dataIndex: 'name', width: 100, render: (_: unknown, row: HoldingDetail) => (
      <span style={{ fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block' }} title={row.holding.name}>{row.holding.name}</span>
    )},
    { title: '市场', dataIndex: 'market', width: 55, render: (_: unknown, row: HoldingDetail) => {
      const marketMap: Record<string, string> = { CN: 'A股', HK: '港股', US: '美股' }
      return <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{marketMap[row.holding.market] || row.holding.market}</span>
    }},
    { title: '数量', dataIndex: 'quantity', width: 85, render: (_: unknown, row: HoldingDetail) => {
      if (editingSymbol === row.holding.symbol) {
        return (
          <Input
            type="number"
            size="mini"
            value={editQty}
            onChange={setEditQty}
            style={{ width: 70, fontFamily: 'var(--font-mono)' }}
          />
        )
      }
      return <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}>{row.position?.quantity?.toLocaleString() ?? 0}</span>
    }},
    { title: '成本价', dataIndex: 'avg_cost', width: 90, render: (_: unknown, row: HoldingDetail) => {
      if (editingSymbol === row.holding.symbol) {
        return (
          <Input
            type="number"
            size="mini"
            value={editCost}
            onChange={setEditCost}
            style={{ width: 75, fontFamily: 'var(--font-mono)' }}
          />
        )
      }
      return <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}>{row.position?.avg_cost?.toFixed(2) ?? '-'}</span>
    }},
    { title: '现价', dataIndex: 'current_price', width: 90, render: (_: unknown, row: HoldingDetail) => (
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{row.position?.current_price?.toFixed(2) ?? '-'}</span>
    )},
    { title: '市值', dataIndex: 'market_value', width: 95, render: (_: unknown, row: HoldingDetail) => (
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600 }}>{row.position?.market_value?.toFixed(2) ?? '-'}</span>
    )},
    { title: '盈亏', dataIndex: 'unrealized_pnl', width: 95, render: (_: unknown, row: HoldingDetail) => {
      if (editingSymbol === row.holding.symbol) {
        return (
          <Input
            type="number"
            size="mini"
            value={editPnl}
            onChange={setEditPnl}
            style={{ width: 75, fontFamily: 'var(--font-mono)' }}
          />
        )
      }
      const pnl = row.position?.unrealized_pnl
      if (pnl === undefined || pnl === null) return '-'
      const color = pnl >= 0 ? 'var(--color-up)' : 'var(--color-down)'
      const sign = pnl >= 0 ? '+' : ''
      return (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600, color }}>
          {sign}{pnl.toFixed(2)}
        </span>
      )
    }},
    { title: '状态', dataIndex: 'data_status', width: 75, render: (_: unknown, row: HoldingDetail) => (
      <Tag size="small" color={statusColor[row.holding.data_status] || 'default'}>{statusMap[row.holding.data_status] || row.holding.data_status}</Tag>
    )},
    {
      title: '操作',
      width: 120,
      render: (_: unknown, row: HoldingDetail) => (
        <div style={{ display: 'flex', gap: 4, justifyContent: 'center' }}>
          {editingSymbol === row.holding.symbol ? (
            <>
              <Button
                type="text"
                size="small"
                icon={<IconCheck />}
                onClick={() => saveEdit(row.holding.symbol)}
                loading={updatePositionMutation.isPending}
              />
              <Button
                type="text"
                size="small"
                icon={<IconClose />}
                onClick={cancelEdit}
              />
            </>
          ) : (
            <>
              <Button
                type="text"
                size="small"
                icon={<IconEye />}
                onClick={() => {
                  setSelectedSymbol(row.holding.symbol)
                  navigate('/stock')
                }}
              />
              <Button
                type="text"
                size="small"
                icon={<IconEdit />}
                onClick={() => startEdit(row)}
              />
              <Button
                type="text"
                size="small"
                status="danger"
                icon={<IconDelete />}
                onClick={() => removeMutation.mutate({ symbol: row.holding.symbol })}
              />
            </>
          )}
        </div>
      ),
    },
  ]

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 className="page-header-title">我的持仓</h2>
        <Button type="primary" icon={<IconCalendar />} onClick={() => navigate('/trades/daily')}>
          每日操作
        </Button>
      </div>

      <Card
        title="添加持仓"
        style={{ marginBottom: 24 }}
        className="animate-fade-in-up stagger-1 card-glow-hover"
      >
        <Form form={form} layout="inline" onSubmit={(v) => addMutation.mutate(v)}>
          <FormItem field="symbol" rules={[{ required: true, message: '请输入代码' }]}>
            <Input placeholder="股票代码" style={{ width: 140 }} />
          </FormItem>
          <FormItem field="market" initialValue="CN">
            <Select style={{ width: 100 }}>
              <Select.Option value="CN">A股</Select.Option>
              <Select.Option value="HK">港股</Select.Option>
            </Select>
          </FormItem>
          <FormItem>
            <Button type="primary" htmlType="submit" icon={<IconPlus />} loading={addMutation.isPending}>
              添加
            </Button>
          </FormItem>
        </Form>
      </Card>

      <Card
        title="持仓列表"
        className="animate-fade-in-up stagger-2 card-glow-hover"
        style={{ marginBottom: 24 }}
        extra={
          <Button icon={<IconRefresh />} loading={refreshMutation.isPending} onClick={() => refreshMutation.mutate()}>
            刷新价格
          </Button>
        }
      >
        {(data || []).length === 0 ? (
          <EmptyState
            icon="📊"
            title="暂无持仓"
            description="添加您的第一支股票，开始 AI 投研分析。"
          />
        ) : (
          <DataList
            columns={columns}
            data={data || []}
            rowKey={(r: HoldingDetail) => r.holding.symbol}
            onRow={(record: HoldingDetail) => ({
              onClick: () => {
                if (editingSymbol) return
                setSelectedSymbol(record.holding.symbol)
              },
              style: { cursor: editingSymbol ? 'default' : 'pointer' },
            })}
            pagination={false}
          />
        )}
      </Card>

      <Card
        title="最近交易记录"
        className="animate-fade-in-up stagger-3 card-glow-hover"
      >
        <Form layout="inline" form={tradeFilterForm} onValuesChange={(_, v) => setTradeSymbolFilter(v.symbol || '')}>
          <FormItem field="symbol">
            <Input placeholder="股票代码" style={{ width: 140 }} />
          </FormItem>
          <FormItem>
            <Button icon={<IconRefresh />} onClick={() => queryClient.invalidateQueries({ queryKey: ['trades'] })}>
              刷新
            </Button>
          </FormItem>
        </Form>
        {(tradesData || []).length === 0 ? (
          <EmptyState
            icon="📝"
            title="暂无交易记录"
            description="在“每日操作”中录入交易，持仓会自动更新。"
          />
        ) : (
          <DataList
            columns={tradeColumns}
            data={tradesData || []}
            rowKey={(r: TradeRecord) => String(r.id)}
            pagination={{ pageSize: 10 }}
            scroll={{ y: 'calc(100vh - 480px)' }}
          />
        )}
      </Card>
    </div>
  )
}
