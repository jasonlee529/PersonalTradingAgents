import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, Form, Input, Message, Select, Tag } from '@arco-design/web-react'
import { IconCheck, IconClose, IconDelete, IconEdit, IconEye, IconPlus, IconRefresh } from '@arco-design/web-react/icon'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import DataList from '../components/DataList'
import EmptyState from '../components/EmptyState'
import { portfolioApi } from '../api/client'
import { usePortfolioStore, type HoldingDetail } from '../store/usePortfolioStore'

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

function formatNumber(value: number | null | undefined, digits = 2) {
  return value == null ? '-' : value.toFixed(digits)
}

function calcPnl(row: HoldingDetail) {
  const quantity = row.position?.quantity ?? 0
  const avgCost = row.position?.avg_cost ?? 0
  const currentPrice = row.position?.current_price
  if (currentPrice == null || quantity <= 0) return null
  return (currentPrice - avgCost) * quantity
}

export default function PortfolioPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { setHoldings, setSelectedSymbol } = usePortfolioStore()
  const [form] = Form.useForm()
  const [editingSymbol, setEditingSymbol] = useState<string | null>(null)
  const [editQty, setEditQty] = useState('')
  const [editCost, setEditCost] = useState('')

  const { data } = useQuery({
    queryKey: ['holdings'],
    queryFn: async () => {
      const resp = await portfolioApi.list()
      return resp.data as HoldingDetail[]
    },
  })

  useEffect(() => {
    if (data) setHoldings(data)
  }, [data, setHoldings])

  const addMutation = useMutation({
    mutationFn: portfolioApi.add,
    onSuccess: () => {
      Message.success('添加成功，正在后台收集数据')
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
    mutationFn: ({ symbol, quantity, avg_cost, current_price }: { symbol: string; quantity: number; avg_cost: number; current_price?: number | null }) =>
      portfolioApi.updatePosition(symbol, { quantity, avg_cost, current_price: current_price ?? null }),
    onSuccess: () => {
      Message.success('持仓已更新')
      setEditingSymbol(null)
      setEditQty('')
      setEditCost('')
      queryClient.invalidateQueries({ queryKey: ['holdings'] })
    },
    onError: () => Message.error('更新失败'),
  })

  const startEdit = (row: HoldingDetail) => {
    setEditingSymbol(row.holding.symbol)
    setEditQty(String(row.position?.quantity ?? 0))
    setEditCost(row.position?.avg_cost != null ? String(row.position.avg_cost) : '')
  }

  const cancelEdit = () => {
    setEditingSymbol(null)
    setEditQty('')
    setEditCost('')
  }

  const saveEdit = (symbol: string) => {
    const quantity = Number.parseInt(editQty, 10)
    const avgCost = Number.parseFloat(editCost)
    if (Number.isNaN(quantity) || quantity < 0) {
      Message.warning('数量不合法')
      return
    }
    if (Number.isNaN(avgCost) || avgCost < 0) {
      Message.warning('成本价不合法')
      return
    }
    updatePositionMutation.mutate({ symbol, quantity, avg_cost: avgCost })
  }

  const columns = [
    {
      title: '代码',
      dataIndex: 'symbol',
      width: 90,
      render: (_: unknown, row: HoldingDetail) => (
        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{row.holding.symbol}</span>
      ),
    },
    {
      title: '名称',
      dataIndex: 'name',
      width: 120,
      render: (_: unknown, row: HoldingDetail) => row.holding.name || '-',
    },
    {
      title: '市场',
      dataIndex: 'market',
      width: 70,
      render: (_: unknown, row: HoldingDetail) => ({ CN: 'A股', HK: '港股', US: '美股' }[row.holding.market] || row.holding.market),
    },
    {
      title: '数量',
      dataIndex: 'quantity',
      width: 100,
      render: (_: unknown, row: HoldingDetail) => editingSymbol === row.holding.symbol ? (
        <Input type="number" size="mini" value={editQty} onChange={setEditQty} style={{ width: 86, fontFamily: 'var(--font-mono)' }} />
      ) : (
        <span style={{ fontFamily: 'var(--font-mono)' }}>{row.position?.quantity?.toLocaleString() ?? 0}</span>
      ),
    },
    {
      title: '成本价',
      dataIndex: 'avg_cost',
      width: 110,
      render: (_: unknown, row: HoldingDetail) => editingSymbol === row.holding.symbol ? (
        <Input type="number" step={0.001} size="mini" value={editCost} onChange={setEditCost} style={{ width: 96, fontFamily: 'var(--font-mono)' }} />
      ) : (
        <span style={{ fontFamily: 'var(--font-mono)' }}>{formatNumber(row.position?.avg_cost, 3)}</span>
      ),
    },
    {
      title: '当前价',
      dataIndex: 'current_price',
      width: 110,
      render: (_: unknown, row: HoldingDetail) => (
        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{formatNumber(row.position?.current_price, 3)}</span>
      ),
    },
    {
      title: '市值',
      dataIndex: 'market_value',
      width: 110,
      render: (_: unknown, row: HoldingDetail) => (
        <span style={{ fontFamily: 'var(--font-mono)' }}>{formatNumber(row.position?.market_value, 2)}</span>
      ),
    },
    {
      title: '收益',
      dataIndex: 'unrealized_pnl',
      width: 110,
      render: (_: unknown, row: HoldingDetail) => {
        const pnl = calcPnl(row)
        if (pnl == null) return '-'
        const sign = pnl >= 0 ? '+' : ''
        return (
          <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: pnl >= 0 ? 'var(--color-up)' : 'var(--color-down)' }}>
            {sign}{pnl.toFixed(2)}
          </span>
        )
      },
    },
    {
      title: '状态',
      dataIndex: 'data_status',
      width: 90,
      render: (_: unknown, row: HoldingDetail) => (
        <Tag size="small" color={statusColor[row.holding.data_status] || 'default'}>{statusMap[row.holding.data_status] || row.holding.data_status}</Tag>
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
      <span
        style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 13, color: 'rgb(var(--primary-6))', cursor: 'pointer', textDecoration: 'none' }}
        onClick={(e) => { e.stopPropagation(); navigate(`/stock?symbol=${row.holding.symbol}`) }}
        onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.textDecoration = 'underline' }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.textDecoration = 'none' }}
      >{row.holding.symbol}</span>
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
      width: 130,
      render: (_: unknown, row: HoldingDetail) => (
        <div style={{ display: 'flex', gap: 4, justifyContent: 'center' }}>
          {editingSymbol === row.holding.symbol ? (
            <>
              <Button type="text" size="small" icon={<IconCheck />} onClick={() => saveEdit(row.holding.symbol)} loading={updatePositionMutation.isPending} />
              <Button type="text" size="small" icon={<IconClose />} onClick={cancelEdit} />
            </>
          ) : (
            <>
              <Button type="text" size="small" icon={<IconEye />} onClick={() => { setSelectedSymbol(row.holding.symbol); navigate('/stock') }} />
              <Button type="text" size="small" icon={<IconEdit />} onClick={() => startEdit(row)} />
              <Button type="text" size="small" status="danger" icon={<IconDelete />} onClick={() => removeMutation.mutate({ symbol: row.holding.symbol })} />
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
        <Button type="primary" onClick={() => navigate('/portfolio/snapshot')}>持仓快照</Button>
      </div>

      <Card title="添加持仓" style={{ marginBottom: 24 }} className="animate-fade-in-up stagger-1 card-glow-hover">
        <Form form={form} layout="inline" onSubmit={(v) => addMutation.mutate(v)}>
          <FormItem field="symbol" rules={[{ required: true, message: '请输入代码' }]}>
            <Input placeholder="股票代码" style={{ width: 140 }} />
          </FormItem>
          <FormItem field="market" initialValue="CN">
            <Select style={{ width: 100 }}>
              <Select.Option value="CN">A股</Select.Option>
              <Select.Option value="HK">港股</Select.Option>
              <Select.Option value="US">美股</Select.Option>
            </Select>
          </FormItem>
          <FormItem>
            <Button type="primary" htmlType="submit" icon={<IconPlus />} loading={addMutation.isPending}>添加</Button>
          </FormItem>
        </Form>
      </Card>

      <Card
        title="持仓列表"
        className="animate-fade-in-up stagger-2 card-glow-hover"
        extra={<Button icon={<IconRefresh />} loading={refreshMutation.isPending} onClick={() => refreshMutation.mutate()}>刷新价格</Button>}
      >
        {(data || []).length === 0 ? (
          <EmptyState icon="📊" title="暂无持仓" description="添加第一只股票后，可以在这里维护数量、成本价和当前价。" />
        ) : (
          <DataList
            columns={columns}
            data={data || []}
            rowKey={(r: HoldingDetail) => r.holding.symbol}
            onRow={(record: HoldingDetail) => ({
              onClick: () => {
                if (editingSymbol) return
                navigate(`/stock?symbol=${record.holding.symbol}`)
              },
              style: { cursor: editingSymbol ? 'default' : 'pointer' },
            })}
            pagination={false}
          />
        )}
      </Card>
    </div>
  )
}
