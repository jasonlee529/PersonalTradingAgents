import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button, Card, Descriptions, Message, Modal, Spin, Tag } from '@arco-design/web-react'
import { IconArrowLeft, IconCheckCircle } from '@arco-design/web-react/icon'
import { useMutation, useQuery } from '@tanstack/react-query'
import { rawApi, wikiApi, type RawSource } from '../api/client'
import {
  labelForOrigin,
  labelForPageType,
  labelForSourceKind,
  labelForTag,
  labelForWikiIngestStatus,
} from '../utils/displayLabels'

export default function RawSourceDetailPage() {
  const params = useParams()
  const navigate = useNavigate()
  const sourceId = params.sourceId ? decodeURIComponent(params.sourceId) : ''
  const [applyResult, setApplyResult] = useState<any>(null)
  const [applyVisible, setApplyVisible] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['raw-source', sourceId],
    queryFn: async () => {
      const resp = await rawApi.detail(sourceId)
      return resp.data as RawSource
    },
    enabled: !!sourceId,
  })

  const verifyMutation = useMutation({
    mutationFn: () => rawApi.verify(sourceId),
    onSuccess: () => Message.success('Hash 校验通过'),
    onError: (err: any) => Message.error(err?.response?.data?.detail || 'Hash 校验失败'),
  })

  const wikiApplyMutation = useMutation({
    mutationFn: () => wikiApi.ingestSource(sourceId, {}),
    onSuccess: (resp) => {
      setApplyResult(resp.data)
      setApplyVisible(true)
    },
    onError: (err: any) => Message.error(err?.response?.data?.detail || '写入知识库失败'),
  })

  if (isLoading) {
    return (
      <div style={{ display: 'grid', placeItems: 'center', minHeight: 360 }}>
        <Spin size={36} />
      </div>
    )
  }

  if (!data) {
    return (
      <Card>
        <Button icon={<IconArrowLeft />} onClick={() => navigate('/knowledge/raw')}>返回</Button>
        <div style={{ padding: 40, color: 'var(--text-muted)' }}>材料不存在</div>
      </Card>
    )
  }

  const metadata = data.metadata || {}
  const ingestStatusColor = (status: string) => {
    if (status === 'completed') return 'green'
    if (status === 'failed') return 'red'
    if (status === 'skipped') return 'gray'
    return 'orange'
  }

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
            <Button type="text" icon={<IconArrowLeft />} onClick={() => navigate('/knowledge/raw')}>
              返回列表
            </Button>
            <Button type="text" onClick={() => navigate('/wiki')}>
              返回知识库
            </Button>
          </div>
          <h2 className="page-header-title" style={{ margin: 0 }}>{data.title}</h2>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <Button icon={<IconCheckCircle />} loading={verifyMutation.isPending} onClick={() => verifyMutation.mutate()}>
            校验 Hash
          </Button>
          <Button type="primary" loading={wikiApplyMutation.isPending} onClick={() => wikiApplyMutation.mutate()}>
            写入知识库
          </Button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '360px minmax(0, 1fr)', gap: 20, alignItems: 'start' }}>
        <Card title="元数据" className="metadata-card">
          <Descriptions
            column={1}
            border
            size="medium"
            data={[
              { label: '来源ID', value: <span style={{ fontFamily: 'var(--font-mono)', wordBreak: 'break-all' }}>{data.source_id}</span> },
              { label: '类型', value: labelForSourceKind(data.source_kind) },
              { label: '来源', value: labelForOrigin(data.origin) },
              { label: '股票', value: data.symbol || data.symbols?.join(', ') || '-' },
              { label: '交易日', value: data.trade_date || '-' },
              { label: '发布时间', value: data.published_at || '-' },
              { label: '采集时间', value: data.captured_at || '-' },
              { label: '路径', value: <span style={{ fontFamily: 'var(--font-mono)', wordBreak: 'break-all' }}>{data.content_path}</span> },
              { label: 'SHA256', value: <span style={{ fontFamily: 'var(--font-mono)', wordBreak: 'break-all' }}>{data.content_sha256}</span> },
            ]}
          />
          <div style={{ marginTop: 16, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {(data.tags || []).map((tag) => <Tag key={tag} title={tag}>{labelForTag(tag)}</Tag>)}
          </div>
          <pre style={{ marginTop: 18, padding: 12, border: '1px solid var(--border-subtle)', borderRadius: 8, background: 'rgba(245,241,235,0.025)', color: 'var(--text-secondary)', overflow: 'auto', maxHeight: 360, fontSize: 12 }}>
            {JSON.stringify(metadata, null, 2)}
          </pre>
        </Card>

        <Card title="Markdown 正文">
          <div className="report-content" style={{ padding: 18, maxHeight: 'calc(100vh - 250px)', overflow: 'auto' }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.markdown || ''}</ReactMarkdown>
          </div>
        </Card>
      </div>

      <Modal
        title="知识库写入结果"
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
              <strong>更新的页面:</strong>
              <ul>
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
