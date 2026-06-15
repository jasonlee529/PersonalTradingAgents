import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Button, Card, Form, Input, InputNumber, Message, Select, Switch } from '@arco-design/web-react'
import { IconClockCircle, IconNotification, IconRobot } from '@arco-design/web-react/icon'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { schedulerApi, settingsApi, type LLMProviderInfo, type ScheduledTask } from '../api/client'

const FormItem = Form.Item

const providerField = (providerId: string, field: 'quick_model' | 'deep_model' | 'api_key') =>
  `provider_${providerId.replace(/[^a-zA-Z0-9]/g, '_')}_${field}`

const notificationChannelOptions = [
  { label: '企业微信', value: 'wechat' },
  { label: '飞书', value: 'feishu' },
  { label: '邮件', value: 'email' },
]

const tabs = [
  { key: 'llm', title: 'LLM 配置', icon: <IconRobot /> },
  { key: 'scheduler', title: '调度配置', icon: <IconClockCircle /> },
  { key: 'notification', title: '今日通知', icon: <IconNotification /> },
  { key: 'knowledge', title: '知识库', icon: <IconRobot /> },
  { key: 'other', title: '其他设置', icon: <IconRobot /> },
]

function parseChannels(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => String(item)).filter(Boolean)
  if (typeof value !== 'string') return []
  return value.split(',').map((item) => item.trim()).filter(Boolean)
}

function SettingsFoldout({
  title,
  expanded,
  onToggle,
  children,
}: {
  title: string
  expanded: boolean
  onToggle: () => void
  children: ReactNode
}) {
  return (
    <div
      style={{
        border: `1px solid ${expanded ? 'var(--accent)' : 'var(--border-medium)'}`,
        borderRadius: 8,
        overflow: 'hidden',
        background: expanded ? 'var(--bg-elevated)' : 'var(--bg-card)',
      }}
    >
      <button
        type="button"
        onClick={onToggle}
        style={{
          width: '100%',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 12,
          padding: '12px 14px',
          border: 0,
          background: expanded ? 'var(--bg-active)' : 'transparent',
          cursor: 'pointer',
          textAlign: 'left',
        }}
      >
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{title}</span>
        <span style={{ fontSize: 12, color: expanded ? 'var(--accent-hover)' : 'var(--text-secondary)' }}>
          {expanded ? '收起' : '展开配置'}
        </span>
      </button>
      {expanded && <div style={{ padding: '0 14px 14px', background: 'var(--bg-elevated)' }}>{children}</div>}
    </div>
  )
}

function SchedulerTasks() {
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['scheduler-tasks'],
    queryFn: async () => {
      const resp = await schedulerApi.tasks()
      return resp.data as ScheduledTask[]
    },
  })

  const updateMutation = useMutation({
    mutationFn: async ({ taskId, values }: { taskId: string; values: { enabled?: boolean; cron?: string } }) => {
      const resp = await schedulerApi.updateTask(taskId, values)
      return resp.data
    },
    onSuccess: () => {
      Message.success('任务已更新')
      queryClient.invalidateQueries({ queryKey: ['scheduler-tasks'] })
    },
    onError: () => Message.error('更新任务失败'),
  })

  const runMutation = useMutation({
    mutationFn: async (taskId: string) => {
      const resp = await schedulerApi.runTask(taskId)
      return resp.data
    },
    onSuccess: () => Message.success('任务已触发'),
    onError: () => Message.error('触发失败'),
  })

  if (isLoading) return <div style={{ color: 'var(--text-secondary)' }}>加载中...</div>

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      {(data || []).map((task) => (
        <div key={task.id} style={{ border: '1px solid var(--border-medium)', borderRadius: 8, padding: 14 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
            <div>
              <div style={{ fontWeight: 600 }}>{task.name}</div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{task.description}</div>
            </div>
            <Switch
              checked={task.enabled}
              onChange={(enabled) => updateMutation.mutate({ taskId: task.id, values: { enabled } })}
            />
          </div>
          <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
            <Input
              value={task.cron}
              onBlur={(event) => updateMutation.mutate({ taskId: task.id, values: { cron: event.target.value } })}
              placeholder="例如: 0 9 * * 1-5"
            />
            <Button onClick={() => runMutation.mutate(task.id)} loading={runMutation.isPending}>
              立即运行
            </Button>
          </div>
        </div>
      ))}
    </div>
  )
}

export default function SettingsPage() {
  const [form] = Form.useForm()
  const [activeTab, setActiveTab] = useState('llm')
  const [expandedProviderId, setExpandedProviderId] = useState('')
  const [expandedNotificationChannel, setExpandedNotificationChannel] = useState('wechat')
  const [expandedOtherSetting, setExpandedOtherSetting] = useState('xueqiu')
  const changedProviderIdsRef = useRef<Set<string>>(new Set())
  const changedProviderValuesRef = useRef<Record<string, unknown>>({})
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: async () => {
      const resp = await settingsApi.get()
      return resp.data as Record<string, unknown>
    },
  })

  const { data: llmProvidersData } = useQuery({
    queryKey: ['llm-providers'],
    queryFn: async () => {
      const resp = await settingsApi.llmProviders()
      return resp.data as { providers: LLMProviderInfo[] }
    },
  })

  const providers = llmProvidersData?.providers || []
  const providerOptions = providers.map((provider) => ({ label: provider.label, value: provider.id }))

  useEffect(() => {
    if (!data) return
    const providerValues: Record<string, unknown> = {}
    const configs = (data.llm_provider_configs || {}) as Record<
      string,
      { quick_model?: string; deep_model?: string; api_key?: string }
    >
    providers.forEach((provider) => {
      const config = configs[provider.id] || {}
      providerValues[providerField(provider.id, 'quick_model')] = config.quick_model || provider.default_quick_model
      providerValues[providerField(provider.id, 'deep_model')] = config.deep_model || provider.default_deep_model
      providerValues[providerField(provider.id, 'api_key')] = config.api_key || ''
    })
    form.setFieldsValue({
      ...data,
      ...providerValues,
      notification_report_channels: parseChannels(data.notification_report_channels),
    })
    changedProviderIdsRef.current.clear()
    changedProviderValuesRef.current = {}
    setExpandedProviderId((current) => current || 'deepseek')
  }, [data, form, providers])

  const updateMutation = useMutation({
    mutationFn: async (values: Record<string, unknown>) => {
      const resp = await settingsApi.update(values)
      return resp.data
    },
    onSuccess: () => {
      Message.success('保存成功')
      queryClient.invalidateQueries({ queryKey: ['settings'] })
    },
    onError: () => Message.error('Failed to save settings'),
  })

  const handleSubmit = (values: Record<string, unknown>) => {
    const providerConfigs: Record<string, { quick_model?: string; deep_model?: string; api_key?: string }> = {}
    const payload: Record<string, unknown> = { ...values }
    delete payload.llm_provider_configs
    providers.forEach((provider) => {
      const quickField = providerField(provider.id, 'quick_model')
      const deepField = providerField(provider.id, 'deep_model')
      const keyField = providerField(provider.id, 'api_key')
      delete payload[quickField]
      delete payload[deepField]
      delete payload[keyField]
      delete payload[provider.api_key_field]
      if (!changedProviderIdsRef.current.has(provider.id)) {
        return
      }
      const currentConfig = ((data?.llm_provider_configs || {}) as Record<
        string,
        { quick_model?: string; deep_model?: string; api_key?: string }
      >)[provider.id] || {}
      providerConfigs[provider.id] = {
        quick_model: String(
          values[quickField] ??
            changedProviderValuesRef.current[quickField] ??
            currentConfig.quick_model ??
            provider.default_quick_model ??
            '',
        ),
        deep_model: String(
          values[deepField] ??
            changedProviderValuesRef.current[deepField] ??
            currentConfig.deep_model ??
            provider.default_deep_model ??
            '',
        ),
        api_key: String(values[keyField] ?? changedProviderValuesRef.current[keyField] ?? currentConfig.api_key ?? ''),
      }
    })
    const updatePayload: Record<string, unknown> = {
      ...payload,
      notification_report_channels: parseChannels(values.notification_report_channels).join(','),
    }
    if (Object.keys(providerConfigs).length > 0) {
      updatePayload.llm_provider_configs = providerConfigs
    }
    updateMutation.mutate(updatePayload)
  }

  const handleValuesChange = (changedValues: Record<string, unknown>) => {
    Object.keys(changedValues).forEach((fieldName) => {
      providers.forEach((provider) => {
        if (
          fieldName === providerField(provider.id, 'quick_model') ||
          fieldName === providerField(provider.id, 'deep_model') ||
          fieldName === providerField(provider.id, 'api_key')
        ) {
          changedProviderIdsRef.current.add(provider.id)
          changedProviderValuesRef.current[fieldName] = changedValues[fieldName]
        }
      })
    })
  }

  return (
    <div>
      <div className="page-header">
        <h2 className="page-header-title">设置</h2>
      </div>

      <Form form={form} layout="vertical" onSubmit={handleSubmit} onValuesChange={handleValuesChange}>
        <div className="segmented-tabs">
          <div className="segmented-tabs-nav">
            {tabs.map((tab) => (
              <div
                key={tab.key}
                className={`segmented-tabs-item ${activeTab === tab.key ? 'segmented-tabs-item-active' : ''}`}
                onClick={() => setActiveTab(tab.key)}
              >
                {tab.icon}
                <span>{tab.title}</span>
              </div>
            ))}
          </div>

          <Card loading={isLoading} className="animate-fade-in-up stagger-1 card-glow-hover">
            <div style={{ display: activeTab === 'llm' ? 'block' : 'none' }}>
                <div style={{ marginBottom: 12, fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
                LLM 供应商
              </div>

              <div style={{ display: 'grid', gap: 10, marginBottom: 20 }}>
                {providers.map((provider) => {
                  const isExpanded = expandedProviderId === provider.id
                  return (
                    <SettingsFoldout
                      key={provider.id}
                      title={provider.label}
                      expanded={isExpanded}
                      onToggle={() => setExpandedProviderId((current) => (current === provider.id ? '' : provider.id))}
                    >
                      <FormItem label="Base URL">
                        <Input value={provider.default_base_url || '-'} disabled />
                      </FormItem>
                      <FormItem
                        label="快速思考模型"
                        field={providerField(provider.id, 'quick_model')}
                        rules={[{ required: true, message: '请输入快速思考模型' }]}
                      >
                        <Input placeholder={`例如: ${provider.default_quick_model || 'model-id'}`} />
                      </FormItem>
                      <FormItem
                        label="深度思考模型"
                        field={providerField(provider.id, 'deep_model')}
                        rules={[{ required: true, message: '请输入深度思考模型' }]}
                      >
                        <Input placeholder={`例如: ${provider.default_deep_model || 'model-id'}`} />
                      </FormItem>
                      {provider.requires_api_key && (
                        <FormItem label={`${provider.label} API Key`} field={providerField(provider.id, 'api_key')}>
                          <Input.Password
                            className="settings-api-key-input"
                            autoComplete="off"
                            defaultVisibility={false}
                            placeholder={`请输入 ${provider.label} API Key`}
                            visibilityToggle
                          />
                        </FormItem>
                      )}
                    </SettingsFoldout>
                  )
                })}
              </div>

              <FormItem label="测试模式" field="test_mode" triggerPropName="checked">
                <Switch />
              </FormItem>
            </div>

            <div style={{ display: activeTab === 'scheduler' ? 'block' : 'none' }}>
              <FormItem label="启用定时调度" field="scheduler_enabled" triggerPropName="checked">
                <Switch />
              </FormItem>
              <FormItem label="分析任务计划" field="analysis_schedule">
                <Input placeholder="0 9 * * 1-5" />
              </FormItem>
              <SchedulerTasks />
            </div>

            <div style={{ display: activeTab === 'notification' ? 'block' : 'none' }}>
              <FormItem label="今日方向 LLM 供应商" field="daily_direction_llm_provider">
                <Select placeholder="默认使用 LLM 配置中的供应商" options={providerOptions} allowClear />
              </FormItem>
              <FormItem
                label="今日方向完成后通知"
                field="daily_direction_notification_enabled"
                triggerPropName="checked"
              >
                <Switch />
              </FormItem>
              <FormItem label="通知渠道" field="notification_report_channels">
                <Select mode="multiple" options={notificationChannelOptions} allowClear />
              </FormItem>
              <FormItem label="Webhook 校验证书" field="webhook_verify_ssl" triggerPropName="checked">
                <Switch />
              </FormItem>

              <div style={{ display: 'grid', gap: 10 }}>
                <SettingsFoldout
                  title="企业微信"
                  expanded={expandedNotificationChannel === 'wechat'}
                  onToggle={() => setExpandedNotificationChannel((current) => (current === 'wechat' ? '' : 'wechat'))}
                >
                  <FormItem label="Webhook URL" field="wechat_webhook_url">
                    <Input.Password
                      autoComplete="off"
                      defaultVisibility={false}
                      placeholder="企业微信机器人 Webhook URL"
                      visibilityToggle
                    />
                  </FormItem>
                  <FormItem label="消息类型" field="wechat_msg_type">
                    <Select placeholder="请选择">
                      <Select.Option value="markdown">Markdown</Select.Option>
                      <Select.Option value="text">Text</Select.Option>
                    </Select>
                  </FormItem>
                  <FormItem label="单条最大字节" field="wechat_max_bytes">
                    <InputNumber className="settings-number-input" hideControl min={40} max={4000} step={100} style={{ width: '100%' }} />
                  </FormItem>
                </SettingsFoldout>

                <SettingsFoldout
                  title="飞书"
                  expanded={expandedNotificationChannel === 'feishu'}
                  onToggle={() => setExpandedNotificationChannel((current) => (current === 'feishu' ? '' : 'feishu'))}
                >
                  <FormItem label="Webhook URL" field="feishu_webhook_url">
                    <Input.Password
                      autoComplete="off"
                      defaultVisibility={false}
                      placeholder="飞书机器人 Webhook URL"
                      visibilityToggle
                    />
                  </FormItem>
                  <FormItem label="签名密钥" field="feishu_webhook_secret">
                    <Input.Password
                      autoComplete="off"
                      defaultVisibility={false}
                      placeholder="可选，飞书加签密钥"
                      visibilityToggle
                    />
                  </FormItem>
                  <FormItem label="安全关键词" field="feishu_webhook_keyword">
                    <Input placeholder="可选，飞书关键词校验" />
                  </FormItem>
                  <FormItem label="单条最大字节" field="feishu_max_bytes">
                    <InputNumber className="settings-number-input" hideControl min={40} max={20000} step={500} style={{ width: '100%' }} />
                  </FormItem>
                </SettingsFoldout>

                <SettingsFoldout
                  title="邮箱"
                  expanded={expandedNotificationChannel === 'email'}
                  onToggle={() => setExpandedNotificationChannel((current) => (current === 'email' ? '' : 'email'))}
                >
                  <FormItem label="发件邮箱" field="email_sender">
                    <Input placeholder="例如: sender@qq.com" />
                  </FormItem>
                  <FormItem label="邮箱授权码" field="email_password">
                    <Input.Password
                      autoComplete="off"
                      defaultVisibility={false}
                      placeholder="SMTP 授权码或密码"
                      visibilityToggle
                    />
                  </FormItem>
                  <FormItem label="收件邮箱" field="email_receivers">
                    <Input placeholder="多个邮箱用英文逗号分隔" />
                  </FormItem>
                  <FormItem label="发件人名称" field="email_sender_name">
                    <Input placeholder="TradingAgents" />
                  </FormItem>
                </SettingsFoldout>
              </div>
            </div>

            <div style={{ display: activeTab === 'knowledge' ? 'block' : 'none' }}>
              <FormItem label="知识库 LLM 供应商" field="wiki_llm_provider">
                <Select placeholder="默认使用 LLM 配置中的供应商" options={providerOptions} allowClear />
              </FormItem>
            </div>

            <div style={{ display: activeTab === 'other' ? 'block' : 'none' }}>
              <div style={{ display: 'grid', gap: 10 }}>
                <SettingsFoldout
                  title="雪球"
                  expanded={expandedOtherSetting === 'xueqiu'}
                  onToggle={() => setExpandedOtherSetting((current) => (current === 'xueqiu' ? '' : 'xueqiu'))}
                >
                  <FormItem label="雪球 cookie" field="xueqiu_cookie">
                    <Input.Password autoComplete="off" defaultVisibility={false} visibilityToggle />
                  </FormItem>
                  <FormItem label="自动刷新雪球 cookie" field="xueqiu_auto_cookie" triggerPropName="checked">
                    <Switch />
                  </FormItem>
                  <FormItem label="雪球超时时间" field="xueqiu_timeout">
                    <InputNumber className="settings-number-input" hideControl min={1} max={60} style={{ width: '100%' }} />
                  </FormItem>
                </SettingsFoldout>
              </div>
            </div>

            <div style={{ marginTop: 24, display: 'flex', justifyContent: 'flex-end' }}>
              <Button type="primary" htmlType="submit" loading={updateMutation.isPending}>
                保存设置
              </Button>
            </div>
          </Card>
        </div>
      </Form>
    </div>
  )
}
