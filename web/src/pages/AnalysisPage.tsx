import { useEffect, useState } from 'react'
import {
  Button,
  Card,
  Form,
  Grid,
  Message,
  Select,
  Switch,
  Tag,
} from '@arco-design/web-react'
import DataList from '../components/DataList'
import { IconHistory, IconRobot } from '@arco-design/web-react/icon'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { analysisApi, configApi, portfolioApi, settingsApi, type LLMProviderInfo } from '../api/client'
import EmptyState from '../components/EmptyState'
import { usePortfolioStore, type HoldingDetail } from '../store/usePortfolioStore'

const { Row, Col } = Grid
const FormItem = Form.Item

const languageOptions = [
  { label: '中文', value: 'Chinese' },
  { label: 'English', value: 'English' },
]

const depthOptions = [
  { label: '深度研究', value: 'deep' },
  { label: '快速分析', value: 'quick' },
]

interface AnalysisFormValues {
  symbol: string
  output_language: string
  analysts: string[]
  research_depth: string
  llm_provider: string
  thinking_agents: boolean
}

interface AnalysisJobListItem {
  job_id: string
  symbol: string
  status: string
  progress: string
  created_at: string
}

const statusColors: Record<string, string> = {
  completed: 'green',
  error: 'red',
  running: 'blue',
  pending: 'gray',
  not_found: 'gray',
}

const statusText: Record<string, string> = {
  completed: '完成',
  error: '失败',
  running: '运行中',
  pending: '等待中',
}

export default function AnalysisPage() {
  const [form] = Form.useForm<AnalysisFormValues>()
  const [analystOptions, setAnalystOptions] = useState<{ label: string; value: string }[]>([])
  const [defaultAnalysts, setDefaultAnalysts] = useState<string[]>(['market', 'social', 'news', 'fundamentals'])
  const [searchText, setSearchText] = useState('')
  const { holdings, selectedSymbol, setHoldings } = usePortfolioStore()
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const { data: llmProvidersData } = useQuery({
    queryKey: ['llm-providers'],
    queryFn: async () => {
      const resp = await settingsApi.llmProviders()
      return resp.data as { providers: LLMProviderInfo[] }
    },
  })

  const llmOptions = (llmProvidersData?.providers || []).map((provider) => ({
    label: provider.label,
    value: provider.id,
  }))

  const { data: holdingsData } = useQuery({
    queryKey: ['holdings'],
    queryFn: async () => {
      const resp = await portfolioApi.list()
      return resp.data as HoldingDetail[]
    },
  })

  useEffect(() => {
    if (holdingsData) setHoldings(holdingsData)
  }, [holdingsData, setHoldings])

  useEffect(() => {
    configApi.analysts().then((resp) => {
      const data = resp.data as { analysts: Array<{ name: string; label: string }>; defaults: string[] }
      const visible = data.analysts
      setAnalystOptions(visible.map((a) => ({ label: a.label, value: a.name })))
      setDefaultAnalysts(data.defaults)
      form.setFieldValue('analysts', data.defaults)
    }).catch(() => {
      const fallback = [
        { label: '市场分析', value: 'market' },
        { label: '情绪分析', value: 'social' },
        { label: '新闻分析', value: 'news' },
        { label: '基本面分析', value: 'fundamentals' },
        { label: '政策与产业催化', value: 'catalyst' },
        { label: '资金与供给风险', value: 'flow_risk' },
      ]
      setAnalystOptions(fallback)
      form.setFieldValue('analysts', fallback.map((a) => a.value))
    })
  }, [form])

  useEffect(() => {
    if (!selectedSymbol) return
    form.setFieldValue('symbol', selectedSymbol)
  }, [selectedSymbol, holdings, form])

  const holdingOptions = holdings.map((h) => ({
    label: `${h.holding.symbol} - ${h.holding.name}`,
    value: h.holding.symbol,
  }))

  const filteredOptions = searchText
    ? holdingOptions.filter((opt) => {
        const input = searchText.toLowerCase()
        const val = String(opt.value).toLowerCase()
        const label = String(opt.label).toLowerCase()
        return val.includes(input) || label.includes(input)
      })
    : holdingOptions

  const startMutation = useMutation({
    mutationFn: async (values: AnalysisFormValues) => {
      const resp = await analysisApi.start({
        symbol: values.symbol.trim(),
        output_language: values.output_language,
        analysts: values.analysts.length > 0 ? values.analysts : undefined,
        research_depth: values.research_depth,
        llm_provider: values.llm_provider,
        thinking_agents: values.thinking_agents,
      })
      return resp.data as { job_id: string }
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['analysis-jobs'] })
      Message.success('分析任务已启动')
      navigate(`/analysis/${data.job_id}`)
    },
    onError: () => {
      Message.error('启动分析失败')
    },
  })

  const { data: historyData, isLoading: historyLoading } = useQuery({
    queryKey: ['analysis-jobs'],
    queryFn: async () => {
      const resp = await analysisApi.jobs({ limit: 50 })
      return (resp.data || []) as AnalysisJobListItem[]
    },
  })

  const historyColumns = [
    {
      title: '任务ID',
      dataIndex: 'job_id',
      width: 160,
      ellipsis: true,
    },
    {
      title: '股票',
      dataIndex: 'symbol',
      width: 110,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (v: string) => (
        <Tag size="small" color={statusColors[v] || 'default'}>
          {statusText[v] || v}
        </Tag>
      ),
    },
    {
      title: '进度',
      dataIndex: 'progress',
      ellipsis: true,
      render: (v: string) => v || '-',
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 180,
      render: (v: string) => (v ? new Date(v).toLocaleString() : '-'),
    },
    {
      title: '操作',
      width: 120,
      render: (_: unknown, row: AnalysisJobListItem) => (
        <Button type="text" size="small" onClick={() => navigate(`/analysis/${row.job_id}`)}>
          查看详情
        </Button>
      ),
    },
  ]

  const handleStart = () => {
    form.validate().then((values) => startMutation.mutate(values))
  }

  return (
    <div>
      <div className="page-header">
        <h2 className="page-header-title">AI 分析</h2>
      </div>

      <Card className="animate-fade-in-up stagger-1" title="分析配置" style={{ marginBottom: 32 }}>
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            output_language: 'Chinese',
            analysts: defaultAnalysts,
            research_depth: 'deep',
            llm_provider: 'deepseek',
            thinking_agents: true,
          }}
        >
          <Row gutter={[20, 0]}>
            <Col span={6}>
              <FormItem label="选择持仓" field="symbol" rules={[{ required: true, message: '请选择持仓股票' }]}>
                <Select
                  showSearch
                  allowClear
                  placeholder="输入代码或名称筛选持仓"
                  filterOption={false}
                  options={filteredOptions}
                  onSearch={setSearchText}
                  onChange={(v) => {
                    form.setFieldValue('symbol', v)
                  }}
                />
              </FormItem>
            </Col>
            <Col span={6}>
              <FormItem label="输出语言" field="output_language">
                <Select options={languageOptions} />
              </FormItem>
            </Col>
            <Col span={6}>
              <FormItem label="LLM 供应商" field="llm_provider" rules={[{ required: true, message: '请选择 LLM 供应商' }]}>
                <Select options={llmOptions} />
              </FormItem>
            </Col>
            <Col span={6}>
              <FormItem label="研究深度" field="research_depth">
                <Select options={depthOptions} />
              </FormItem>
            </Col>
          </Row>

          <Row gutter={[20, 0]}>
            <Col span={12}>
              <FormItem label="分析师团队" field="analysts">
                <Select mode="multiple" options={analystOptions} placeholder="选择分析师" />
              </FormItem>
            </Col>
            <Col span={6}>
              <FormItem label="研究团队辩论" field="thinking_agents" triggerPropName="checked">
                <Switch />
              </FormItem>
            </Col>
          </Row>

          <div style={{ marginTop: 20, display: 'flex', justifyContent: 'center' }}>
            <Button
              type="primary"
              icon={<IconRobot />}
              loading={startMutation.isPending}
              onClick={handleStart}
              size="large"
              style={{ minWidth: 240, height: 48, fontSize: 16, fontWeight: 600 }}
            >
              开始分析
            </Button>
          </div>
        </Form>
      </Card>

      <Card className="animate-fade-in-up stagger-2" title={<span><IconHistory /> 分析记录</span>}>
        {(historyData || []).length === 0 ? (
          <EmptyState
            icon="AI"
            title="暂无分析记录"
            description="选择股票并启动分析后，将进入独立任务详情页查看工作流与报告产物。"
          />
        ) : (
          <DataList
            columns={historyColumns}
            data={historyData || []}
            rowKey="job_id"
            loading={historyLoading}
            pagination={{ pageSize: 10 }}
            scroll={{ y: 420 }}
          />
        )}
      </Card>
    </div>
  )
}
