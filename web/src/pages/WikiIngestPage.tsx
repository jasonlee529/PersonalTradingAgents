import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, Message, Modal, Spin, Tag } from '@arco-design/web-react'
import { IconPlayArrow, IconStorage } from '@arco-design/web-react/icon'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { wikiApi } from '../api/client'
import {
  labelForPageType,
  labelForSourceKind,
  labelForWikiIngestStatus,
  labelForWikiSourceStatus,
} from '../utils/displayLabels'
import DataList from '../components/DataList'
import EmptyState from '../components/EmptyState'

const RUNNING_STATUSES = new Set(['queued', 'planning', 'applying'])
const MAX_RUNNING = 10

export default function WikiIngestPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [applyResult, setApplyResult] = useState<any>(null)
  const [applyVisible, setApplyVisible] = useState(false)
  const [localRunning, setLocalRunning] = useState<Record<string, string>>({})

  const { data: pendingSources, isLoading } = useQuery({
    queryKey: ['wiki-pending-sources'],
    queryFn: async () => {
      const resp = await wikiApi.pendingSources({ limit: 100 })
      return resp.data as any[]
    },
    refetchInterval: (query) => {
      const rows = (query.state.data || []) as any[]
      return rows.some((row) => RUNNING_STATUSES.has(row.wiki_status)) ? 2500 : false
    },
  })

  const displaySources = useMemo(() => {
    return (pendingSources || []).map((source) => {
      const localStatus = localRunning[source.source_id]
      if (localStatus && (!source.wiki_status || source.wiki_status === 'pending')) {
        return { ...source, wiki_status: localStatus }
      }
      return source
    })
  }, [pendingSources, localRunning])

  const runningCount = useMemo(
    () => displaySources.filter((source) => RUNNING_STATUSES.has(source.wiki_status)).length,
    [displaySources],
  )

  const batchableSources = useMemo(
    () => displaySources.filter((source) => !RUNNING_STATUSES.has(source.wiki_status)).slice(0, MAX_RUNNING - runningCount),
    [displaySources, runningCount],
  )

  const applyMutation = useMutation({
    mutationFn: (sourceId: string) => wikiApi.ingestSource(sourceId, {}),
    onSuccess: (resp) => {
      const data = resp.data
      const sourceIds = data.source_ids || []
      if (RUNNING_STATUSES.has(data.status)) {
        setLocalRunning((prev) => {
          const next = { ...prev }
          sourceIds.forEach((sourceId: string) => {
            next[sourceId] = data.status
          })
          return next
        })
        Message.success(data.status === 'queued' ? '已加入写入队列' : '正在写入')
      } else {
        setApplyResult(data)
        setApplyVisible(true)
      }
      queryClient.invalidateQueries({ queryKey: ['wiki-pending-sources'] })
    },
    onError: (err: any, sourceId) => {
      setLocalRunning((prev) => {
        const next = { ...prev }
        delete next[sourceId]
        return next
      })
      Message.error(err?.response?.data?.detail || '执行失败')
      queryClient.invalidateQueries({ queryKey: ['wiki-pending-sources'] })
    },
  })

  const batchMutation = useMutation({
    mutationFn: (sourceIds: string[]) => wikiApi.ingestBatch({ source_ids: sourceIds }),
    onSuccess: (resp) => {
      const data = resp.data
      const queuedIds = (data.results || [])
        .filter((result: any) => RUNNING_STATUSES.has(result.status))
        .map((result: any) => result.source_id)

      if (queuedIds.length > 0) {
        setLocalRunning((prev) => {
          const next = { ...prev }
          queuedIds.forEach((sourceId: string) => {
            next[sourceId] = 'queued'
          })
          return next
        })
        Message.success(`已批量加入写入队列：${queuedIds.length} 条`)
      } else if (data.batch_status === 'skipped') {
        Message.info('没有需要批量写入的材料')
      } else {
        Message.warning('批量写入未产生新的队列任务')
      }

      queryClient.invalidateQueries({ queryKey: ['wiki-pending-sources'] })
      queryClient.invalidateQueries({ queryKey: ['wiki-ingest-runs'] })
    },
    onError: (err: any) => {
      Message.error(err?.response?.data?.detail || '批量执行失败')
      queryClient.invalidateQueries({ queryKey: ['wiki-pending-sources'] })
    },
  })

  const sourceStatusColor = (status: string) => {
    if (status === 'queued') return 'blue'
    if (status === 'planning') return 'cyan'
    if (status === 'applying') return 'arcoblue'
    if (status === 'pending') return 'orange'
    if (status === 'processed') return 'green'
    if (status === 'failed') return 'red'
    if (status === 'needs_reprocess') return 'purple'
    return 'gray'
  }

  const ingestStatusColor = (status: string) => {
    if (RUNNING_STATUSES.has(status)) return 'blue'
    if (status === 'completed') return 'green'
    if (status === 'failed') return 'red'
    if (status === 'skipped') return 'gray'
    return 'orange'
  }

  const columns = [
    { title: '类型', dataIndex: 'source_kind', width: 100, render: (v: string) => <Tag title={v}>{labelForSourceKind(v)}</Tag> },
    { title: '标题', dataIndex: 'title' },
    { title: '股票', dataIndex: 'symbol', width: 90, render: (v: string) => v || '-' },
    { title: '交易日', dataIndex: 'trade_date', width: 110, render: (v: string) => v || '-' },
    {
      title: '状态',
      dataIndex: 'wiki_status',
      width: 110,
      render: (v: string) => {
        const status = v || 'pending'
        return <Tag color={sourceStatusColor(status)} title={status}>{labelForWikiSourceStatus(status)}</Tag>
      },
    },
    {
      title: '操作',
      width: 180,
      render: (_: any, record: any) => {
        const isRunning = RUNNING_STATUSES.has(record.wiki_status)
        const isSubmitting = applyMutation.isPending && applyMutation.variables === record.source_id
        const limitReached = runningCount >= MAX_RUNNING && !isRunning
        return (
          <div style={{ display: 'flex', gap: 6, justifyContent: 'center' }}>
            <Button
              size="mini"
              type="primary"
              icon={<IconPlayArrow />}
              loading={isSubmitting || isRunning}
              disabled={limitReached || isRunning}
              title={limitReached ? `执行中的记录已达到 ${MAX_RUNNING} 条` : undefined}
              onClick={() => {
                if (limitReached) {
                  Message.warning(`最多允许 ${MAX_RUNNING} 条记录处于执行中`)
                  return
                }
                setLocalRunning((prev) => ({ ...prev, [record.source_id]: 'queued' }))
                applyMutation.mutate(record.source_id)
              }}
            >
              {isRunning ? '执行中' : '执行'}
            </Button>
            <Button size="mini" onClick={() => navigate(`/knowledge/raw/${encodeURIComponent(record.source_id)}`)}>
              源文件
            </Button>
          </div>
        )
      },
    },
  ]

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h2 className="page-header-title" style={{ margin: 0 }}>写入队列</h2>
          <div style={{ marginTop: 6, color: 'var(--color-text-3)', fontSize: 13 }}>
            执行中 {runningCount} / {MAX_RUNNING}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Button
            type="primary"
            icon={<IconPlayArrow />}
            loading={batchMutation.isPending}
            disabled={batchableSources.length === 0 || batchMutation.isPending}
            onClick={() => {
              const sourceIds = batchableSources.map((source) => source.source_id)
              if (sourceIds.length === 0) {
                Message.info('没有可批量写入的材料')
                return
              }
              batchMutation.mutate(sourceIds)
            }}
          >
            批量执行
          </Button>
          <Button icon={<IconStorage />} onClick={() => navigate('/wiki')}>知识库首页</Button>
        </div>
      </div>

      <Card>
        {isLoading ? (
          <div style={{ display: 'grid', placeItems: 'center', minHeight: 200 }}>
            <Spin size={36} />
          </div>
        ) : displaySources.length === 0 ? (
          <EmptyState title="暂无待处理源" description="所有源已处理完毕。" />
        ) : (
          <DataList
            columns={columns}
            data={displaySources}
            rowKey="source_id"
            loading={isLoading}
            pagination={{ pageSize: 20 }}
          />
        )}
      </Card>

      <Modal
        title="执行结果"
        visible={applyVisible}
        onOk={() => setApplyVisible(false)}
        onCancel={() => setApplyVisible(false)}
        autoFocus={false}
        style={{ width: 600 }}
      >
        {applyResult && (
          <div>
            <div style={{ marginBottom: 12 }}>
              <Tag color={ingestStatusColor(applyResult.status)} title={applyResult.status}>
                {labelForWikiIngestStatus(applyResult.status)}
              </Tag>
            </div>
            <div style={{ marginBottom: 12 }}>
              <strong>更新的页面</strong>
              <ul>
                {(applyResult.pages_touched || []).length === 0 && (
                  <li>暂无页面变更</li>
                )}
                {(applyResult.pages_touched || []).map((p: any) => (
                  <li key={p.page_id}>
                    <span
                      style={{ cursor: 'pointer', color: 'var(--color-primary)' }}
                      onClick={() => {
                        setApplyVisible(false)
                        navigate(`/wiki/pages/${encodeURIComponent(p.page_id)}`)
                      }}
                    >
                      {p.title} ({labelForPageType(p.page_type)})
                    </span>
                  </li>
                ))}
              </ul>
            </div>
            {(applyResult.warnings || []).length > 0 && (
              <div style={{ color: 'orange' }}>
                <strong>警告:</strong>
                <ul>
                  {applyResult.warnings.map((w: string, i: number) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}
