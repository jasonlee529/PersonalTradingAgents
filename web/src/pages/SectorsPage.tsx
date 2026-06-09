import React, { useState, useEffect, useRef, useMemo } from 'react'
import {
  Button,
  Spin,
  Tag,
  Message,
  Empty,
  Modal,
} from '@arco-design/web-react'
import { IconRefresh, IconFile, IconHistory } from '@arco-design/web-react/icon'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  sectorsApi,
  type DiscoverStatus,
  type DirectionReport,
} from '../api/client'
import EmptyState from '../components/EmptyState'

const POLL_INTERVAL = 1500

const LS_JOB_KEY = 'sector_discovery_job_id'

const PHASE_ORDER = ['scout', 'validate', 'compare', 'deep_dive', 'report', 'done'] as const

const phaseToChinese: Record<string, string> = {
  scout: '方向发现',
  validate: '多维验证',
  compare: '排序筛选',
  deep_dive: '深度分析',
  report: '生成报告',
  done: '完成',
}

function formatReportTime(value?: string) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).replace(/\//g, '-')
}

const ReportContent = React.memo(function ReportContent({ content }: { content: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]}>
      {content}
    </ReactMarkdown>
  )
})

export default function SectorsPage() {
  const queryClient = useQueryClient()
  const [discoverJobId, setDiscoverJobId] = useState<string | null>(() => {
    return localStorage.getItem(LS_JOB_KEY)
  })
  const [discoverStatus, setDiscoverStatus] = useState<DiscoverStatus | null>(null)
  const [historyModalVisible, setHistoryModalVisible] = useState(false)
  const [selectedHistoryReport, setSelectedHistoryReport] = useState<DirectionReport | null>(null)
  const [activeTab, setActiveTab] = useState('today')
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const {
    data: todayData,
    isLoading: isLoadingToday,
    isError: isErrorToday,
  } = useQuery({
    queryKey: ['sectors', 'today'],
    queryFn: async () => {
      const res = await sectorsApi.today()
      return res.data as { reports: DirectionReport[] }
    },
    staleTime: 30000,
    refetchInterval: () => {
      // Only poll when a discovery is running; otherwise let manual refresh drive updates
      return discoverJobId ? 1500 : false
    },
  })

  const clearPoll = () => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current)
      pollTimerRef.current = null
    }
  }

  const pollStatus = async (jobId: string) => {
    try {
      const res = await sectorsApi.discoverStatus(jobId)
      const status = res.data as DiscoverStatus
      setDiscoverStatus(status)
      if (status.status === 'completed') {
        clearPoll()
        setDiscoverJobId(null)
        localStorage.removeItem(LS_JOB_KEY)
        queryClient.invalidateQueries({ queryKey: ['sectors', 'today'] })
        Message.success(status.message || '方向扫描完成')
      } else if (status.status === 'failed') {
        clearPoll()
        setDiscoverJobId(null)
        localStorage.removeItem(LS_JOB_KEY)
        Message.error(status.error || '扫描失败')
      }
    } catch (err: any) {
      clearPoll()
      setDiscoverJobId(null)
      Message.error(`查询进度失败: ${err?.response?.data?.detail || err.message}`)
    }
  }

  useEffect(() => {
    if (discoverJobId) {
      pollStatus(discoverJobId)
      pollTimerRef.current = setInterval(() => pollStatus(discoverJobId), POLL_INTERVAL)
    }
    return () => clearPoll()
  }, [discoverJobId])

  const discoverMutation = useMutation({
    mutationFn: () => sectorsApi.discover(),
    onSuccess: (res: any) => {
      const data = res.data as { job_id: string; status: string; message: string }
      setDiscoverJobId(data.job_id)
      localStorage.setItem(LS_JOB_KEY, data.job_id)
      setDiscoverStatus({
        job_id: data.job_id,
        status: 'pending',
        progress_pct: 0,
        phase: '',
        message: data.message,
        error: '',
        phases: [],
        result_summary: '',
        created_at: new Date().toISOString(),
      })
    },
    onError: (err: any) => {
      Message.error(`扫描失败: ${err?.response?.data?.detail || err.message}`)
    },
  })

  const isDiscovering = discoverJobId !== null

  const reports = useMemo(() => todayData?.reports || [], [todayData])
  const latestReport = reports[0]
  const historyReports = useMemo(() => reports.slice(1), [reports])

  const openHistoryModal = (report: DirectionReport) => {
    setSelectedHistoryReport(report)
    setHistoryModalVisible(true)
  }

  return (
    <div>
      {/* Header */}
      <div className="page-header" style={{ marginBottom: 24, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h2 className="page-header-title">今日方向</h2>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <Button
            type="primary"
            icon={<IconRefresh spin={isDiscovering} />}
            loading={discoverMutation.isPending}
            disabled={isDiscovering}
            onClick={() => discoverMutation.mutate()}
          >
            {isDiscovering ? '扫描中...' : '刷新方向'}
          </Button>
        </div>
      </div>

      {/* Progress dots only */}
      {isDiscovering && discoverStatus && (
        <div style={{ marginBottom: 24, padding: '16px 20px', background: 'var(--bg-card)', borderRadius: 'var(--radius-lg)', border: '1px solid var(--border-subtle)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            {PHASE_ORDER.map((phaseKey, idx) => {
              const phaseInfo = discoverStatus.phases.find((p) => p.phase === phaseKey)
              const status = phaseInfo?.status || 'pending'
              const isLast = idx === PHASE_ORDER.length - 1
              const dotColor =
                status === 'success'
                  ? '#00b42a'
                  : status === 'failure' || status === 'timeout'
                    ? '#f53f3f'
                    : status === 'running'
                      ? '#165dff'
                      : discoverStatus.status === 'completed' && phaseKey === 'done'
                        ? '#00b42a'
                        : '#c9cdd4'
              const isActive =
                status === 'running' ||
                (discoverStatus.status === 'completed' && phaseKey === 'done')
              return (
                <div key={phaseKey} style={{ display: 'flex', alignItems: 'center', flex: isLast ? 0 : 1 }}>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
                    <span
                      style={{
                        width: 12,
                        height: 12,
                        borderRadius: '50%',
                        background: dotColor,
                        boxShadow: isActive ? `0 0 0 5px ${dotColor}30` : 'none',
                        transition: 'all 0.3s',
                      }}
                    />
                    <span style={{ fontSize: 11, color: 'var(--text-dim)', whiteSpace: 'nowrap' }}>
                      {phaseToChinese[phaseKey]}
                    </span>
                  </div>
                  {!isLast && (
                    <div
                      style={{
                        flex: 1,
                        height: 2,
                        background: status === 'success' ? '#00b42a' : '#e5e6eb',
                        margin: '0 10px',
                        marginBottom: 20,
                        transition: 'background 0.3s',
                      }}
                    />
                  )}
                </div>
              )
            })}
          </div>
          {discoverStatus.error && (
            <div style={{ marginTop: 10, padding: 8, background: '#fff2f0', borderRadius: 4, fontSize: 12, color: '#f53f3f' }}>
              {discoverStatus.error}
            </div>
          )}
        </div>
      )}

      {/* Content */}
      {isLoadingToday ? (
        <div style={{ textAlign: 'center', padding: 60 }}>
          <Spin size={40} />
          <div style={{ marginTop: 16, color: 'var(--text-dim)' }}>加载中...</div>
        </div>
      ) : isErrorToday ? (
        <EmptyState title="加载失败" description="无法获取今日方向数据，请稍后重试" />
      ) : !latestReport ? (
        <Empty
          description={
            <div>
              <div style={{ fontSize: 16, fontWeight: 500, marginBottom: 8 }}>暂无方向报告</div>
              <div style={{ fontSize: 13, color: 'var(--text-dim)' }}>
                点击右上角"刷新方向"触发多智能体方向扫描
              </div>
            </div>
          }
        />
      ) : (
        <div className="segmented-tabs">
          <div className="segmented-tabs-nav">
            <div
              className={`segmented-tabs-item ${activeTab === 'today' ? 'segmented-tabs-item-active' : ''}`}
              onClick={() => setActiveTab('today')}
            >
              <IconFile />
              <span>今日方向</span>
            </div>
            <div
              className={`segmented-tabs-item ${activeTab === 'history' ? 'segmented-tabs-item-active' : ''}`}
              onClick={() => setActiveTab('history')}
            >
              <IconHistory />
              <span>历史方向 ({historyReports.length})</span>
            </div>
          </div>

          {activeTab === 'today' && (
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <div>
                  <h3 style={{ margin: 0, fontSize: 18, fontWeight: 600 }}>{latestReport.title || `${latestReport.date} 方向扫描`}</h3>
                  <div style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 4 }}>
                    {formatReportTime(latestReport.created_at)}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <Tag color="arcoblue">方向扫描</Tag>
                  <Tag>{latestReport.date}</Tag>
                  {latestReport.sectors?.length > 0 && (
                    <Tag color="green">{latestReport.sectors.length} 个方向</Tag>
                  )}
                </div>
              </div>

              <div
                className="report-content"
                style={{
                  padding: 24,
                  background: 'var(--bg-card)',
                  borderRadius: 'var(--radius-lg)',
                  border: '1px solid var(--border-subtle)',
                  lineHeight: 1.8,
                }}
              >
                <ReportContent content={latestReport.content || latestReport.summary || ''} />
              </div>
            </div>
          )}

          {activeTab === 'history' && (
            <div>
              {historyReports.length === 0 ? (
                <Empty description="暂无历史报告" />
              ) : (
                <div style={{ position: 'relative', paddingLeft: 20 }}>
                  {/* Timeline vertical line */}
                  <div
                    style={{
                      position: 'absolute',
                      left: 5,
                      top: 8,
                      bottom: 8,
                      width: 2,
                      background: 'var(--border-subtle)',
                    }}
                  />

                  {historyReports.map((report, idx) => (
                    <div
                      key={report.id}
                      onClick={() => openHistoryModal(report)}
                      style={{
                        position: 'relative',
                        padding: '12px 16px',
                        marginBottom: idx === historyReports.length - 1 ? 0 : 12,
                        background: 'var(--bg-card)',
                        borderRadius: 'var(--radius-md)',
                        border: '1px solid var(--border-subtle)',
                        cursor: 'pointer',
                        transition: 'all 0.2s',
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.borderColor = 'var(--accent)'
                        e.currentTarget.style.background = 'var(--bg-hover)'
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.borderColor = 'var(--border-subtle)'
                        e.currentTarget.style.background = 'var(--bg-card)'
                      }}
                    >
                      {/* Timeline dot */}
                      <div
                        style={{
                          position: 'absolute',
                          left: -16,
                          top: 18,
                          width: 8,
                          height: 8,
                          borderRadius: '50%',
                          background: 'var(--accent)',
                          border: '2px solid var(--bg-base)',
                        }}
                      />

                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <div>
                          <div style={{ fontWeight: 500, fontSize: 14, marginBottom: 4 }}>
                            {report.title || `${report.date} 方向扫描`}
                          </div>
                          <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>
                            {formatReportTime(report.created_at)} · {report.sectors?.length || 0} 个方向
                            {report.candidate_count !== undefined && (
                              <span> · 候选 {report.candidate_count} 个</span>
                            )}
                          </div>
                        </div>
                        <Tag size="small" color="arcoblue">查看</Tag>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* History Detail Modal */}
      <Modal
        title={selectedHistoryReport?.title || '历史报告'}
        visible={historyModalVisible}
        onOk={() => setHistoryModalVisible(false)}
        onCancel={() => setHistoryModalVisible(false)}
        autoFocus={false}
        style={{ width: 900 }}
        className="analysis-report-modal"
        footer={(
          <Button type="primary" onClick={() => setHistoryModalVisible(false)}>
            关闭
          </Button>
        )}
      >
        {selectedHistoryReport && (
          <div>
            <div className="analysis-report-modal-tags" style={{ marginBottom: 12 }}>
              <Tag color="arcoblue">方向扫描</Tag>
              <Tag>{selectedHistoryReport.date}</Tag>
              {selectedHistoryReport.sectors?.length > 0 && (
                <Tag color="green">{selectedHistoryReport.sectors.length} 个方向</Tag>
              )}
            </div>
            <div className="report-content" style={{ maxHeight: '65vh', overflow: 'auto', lineHeight: 1.8 }}>
              <ReportContent content={selectedHistoryReport.content || selectedHistoryReport.summary || ''} />
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
