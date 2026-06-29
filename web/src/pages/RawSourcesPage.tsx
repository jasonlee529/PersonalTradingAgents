import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button, Card, Tag, Modal, Descriptions, Spin } from '@arco-design/web-react'
import { IconArrowLeft, IconEye, IconPlus, IconRefresh, IconEdit, IconStorage } from '@arco-design/web-react/icon'
import { useQuery } from '@tanstack/react-query'
import DataList from '../components/DataList'
import EmptyState from '../components/EmptyState'
import { rawApi, type RawSource } from '../api/client'
import { labelForOrigin, labelForSourceKind, labelForTag } from '../utils/displayLabels'

interface RawSourcesPageProps {
  sourceKind?: string
  title?: string
  subtitle?: string
  emptyTitle?: string
  emptyDescription?: string
}

export default function RawSourcesPage({
  sourceKind,
  title = '原始材料',
  subtitle = '查看知识库写入前的公告、新闻、研报、分析输出和手动材料。',
  emptyTitle = '暂无原始材料',
  emptyDescription = '新增材料或运行分析后，源材料会进入这里。',
}: RawSourcesPageProps = {}) {
  const navigate = useNavigate()
  const [viewVisible, setViewVisible] = useState(false)
  const [selectedSource, setSelectedSource] = useState<RawSource | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['raw-sources', sourceKind || 'all'],
    queryFn: async () => {
      const resp = await rawApi.list({ source_kind: sourceKind, limit: 100 })
      return resp.data as RawSource[]
    },
  })

  const openViewModal = async (row: RawSource) => {
    setSelectedSource(row)
    setViewVisible(true)
    if (!row.markdown) {
      setDetailLoading(true)
      try {
        const resp = await rawApi.detail(row.source_id)
        setSelectedSource(resp.data as RawSource)
      } catch {
        // keep row as fallback
      } finally {
        setDetailLoading(false)
      }
    }
  }

  const columns = [
    {
      title: '类型',
      dataIndex: 'source_kind',
      width: 120,
      render: (value: string) => <Tag color="arcoblue">{labelForSourceKind(value)}</Tag>,
    },
    {
      title: '标题',
      dataIndex: 'title',
      render: (value: string, row: RawSource) => (
        <div style={{ minWidth: 0, textAlign: 'center' }}>
          <div style={{ color: 'var(--text-primary)', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {value}
          </div>
          <div style={{ color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', fontSize: 11, marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {row.source_id}
          </div>
        </div>
      ),
    },
    {
      title: '股票',
      dataIndex: 'symbol',
      width: 110,
      render: (_: string, row: RawSource) => row.symbol || row.symbols?.join(', ') || '-',
    },
    {
      title: '日期',
      dataIndex: 'trade_date',
      width: 120,
      render: (value: string, row: RawSource) => value || row.published_at?.slice(0, 10) || row.captured_at?.slice(0, 10) || '-',
    },
    {
      title: '标签',
      dataIndex: 'tags',
      width: 180,
      render: (tags: string[]) => (
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', justifyContent: 'center' }}>
          {(tags || []).slice(0, 3).map((tag) => {
            const label = labelForTag(tag)
            const short = label.length > 16 ? label.slice(0, 15) + '…' : label
            return (
              <Tag key={tag} title={tag} size="small">
                {short}
              </Tag>
            )
          })}
        </div>
      ),
    },
    {
      title: '操作',
      width: 80,
      render: (_: unknown, row: RawSource) => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2, alignItems: 'center' }}>
          <Button type="text" size="small" icon={<IconEye />} onClick={() => openViewModal(row)}>
            查看
          </Button>
          {row.source_kind === 'manual_source' && (
            <Button type="text" size="small" icon={<IconEdit />} onClick={() => navigate(`/knowledge/raw/${encodeURIComponent(row.source_id)}/edit`)}>
              编辑
            </Button>
          )}
        </div>
      ),
    },
  ]

  return (
    <div>
      <div
        className="page-header"
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 24,
          padding: '20px 22px',
          border: '1px solid var(--border-medium)',
          borderRadius: 'var(--radius-lg)',
          background: 'linear-gradient(135deg, rgba(232,87,51,0.12), rgba(96,165,250,0.06)), var(--bg-card)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, minWidth: 0 }}>
          <div style={{ width: 44, height: 44, borderRadius: 10, display: 'grid', placeItems: 'center', background: 'var(--accent-soft)', color: 'var(--accent)', border: '1px solid var(--border-accent)' }}>
            <IconStorage style={{ fontSize: 22 }} />
          </div>
          <div style={{ minWidth: 0 }}>
            <h2 className="page-header-title" style={{ margin: 0 }}>{title}</h2>
            <div style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 6 }}>
              {subtitle}
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <Button icon={<IconArrowLeft />} onClick={() => navigate('/wiki')}>返回知识库</Button>
          <Button icon={<IconRefresh />} onClick={() => refetch()}>刷新</Button>
          <Button type="primary" icon={<IconPlus />} onClick={() => navigate('/knowledge/raw/new')}>新增材料</Button>
        </div>
      </div>

      <Card>
        {(data || []).length === 0 && !isLoading ? (
          <EmptyState title={emptyTitle} description={emptyDescription} />
        ) : (
          <DataList
            columns={columns}
            data={data || []}
            rowKey="source_id"
            loading={isLoading}
            pagination={{ pageSize: 20 }}
            scroll={{ y: 'calc(100vh - 360px)' }}
          />
        )}
      </Card>

      <Modal
        title={selectedSource?.title || '材料详情'}
        visible={viewVisible}
        onOk={() => setViewVisible(false)}
        onCancel={() => setViewVisible(false)}
        autoFocus={false}
        style={{ width: 960 }}
        className="analysis-report-modal"
      >
        {detailLoading ? (
          <div style={{ display: 'grid', placeItems: 'center', minHeight: 200 }}>
            <Spin size={36} />
          </div>
        ) : selectedSource ? (
          <div>
            <div className="analysis-report-modal-tags" style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                <Tag color="arcoblue">{labelForSourceKind(selectedSource.source_kind)}</Tag>
                <Tag>{labelForOrigin(selectedSource.origin)}</Tag>
                {(selectedSource.tags || []).slice(0, 5).map((tag) => (
                  <Tag key={tag} size="small" title={tag}>{labelForTag(tag)}</Tag>
                ))}
              </div>
              {selectedSource.source_kind === 'manual_source' && (
                <Button type="text" size="small" icon={<IconEdit />} onClick={() => {
                  setViewVisible(false)
                  navigate(`/knowledge/raw/${encodeURIComponent(selectedSource.source_id)}/edit`)
                }}>
                  编辑
                </Button>
              )}
            </div>

            <Descriptions
              column={2}
              data={[
                { label: '来源ID', value: <span style={{ fontFamily: 'var(--font-mono)', wordBreak: 'break-all', fontSize: 12 }}>{selectedSource.source_id}</span> },
                { label: '股票', value: selectedSource.symbol || selectedSource.symbols?.join(', ') || '-' },
                { label: '交易日', value: selectedSource.trade_date || '-' },
                { label: '发布时间', value: selectedSource.published_at || '-' },
              ]}
            />

            <div className="report-content" style={{ marginTop: 16, padding: 20, maxHeight: '60vh', overflow: 'auto', border: '1px solid var(--border-subtle)', borderRadius: 8 }}>
              {selectedSource.markdown ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{selectedSource.markdown}</ReactMarkdown>
              ) : (
                <div style={{ color: 'var(--text-muted)' }}>暂无正文内容</div>
              )}
            </div>
          </div>
        ) : null}
      </Modal>
    </div>
  )
}
