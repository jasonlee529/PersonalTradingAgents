import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Button, Card, Form, Input, Message } from '@arco-design/web-react'
import { useAuthStore } from '../store/useAuthStore'

interface LoginFormValues {
  username: string
  password: string
}

export default function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const login = useAuthStore((state) => state.login)
  const [loading, setLoading] = useState(false)
  const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname || '/'

  const handleSubmit = async (values: LoginFormValues) => {
    setLoading(true)
    try {
      await login(values.username, values.password)
      Message.success('登录成功')
      navigate(from, { replace: true })
    } catch {
      Message.error('用户名或密码错误')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      style={{
        minHeight: '100dvh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
        background:
          'radial-gradient(circle at 50% 0%, rgba(232, 87, 51, 0.16), transparent 34%), var(--bg-base)',
      }}
    >
      <Card
        style={{
          width: 380,
          maxWidth: '100%',
          background: 'var(--bg-card)',
          border: '1px solid var(--border-subtle)',
          boxShadow: 'var(--shadow-lg)',
        }}
      >
        <div style={{ marginBottom: 28, textAlign: 'center' }}>
          <div
            style={{
              width: 48,
              height: 48,
              margin: '0 auto 16px',
              borderRadius: 14,
              background: 'var(--accent)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 4px 18px rgba(232, 87, 51, 0.35)',
            }}
          >
            <span style={{ color: 'var(--text-primary)', fontWeight: 800 }}>AI</span>
          </div>
          <div style={{ color: 'var(--text-primary)', fontSize: 20, fontWeight: 700 }}>
            个人AI投研助手
          </div>
          <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 8 }}>
            请登录后继续使用
          </div>
        </div>

        <Form<LoginFormValues>
          layout="vertical"
          initialValues={{ username: 'jason' }}
          onSubmit={handleSubmit}
        >
          <Form.Item
            label="用户名"
            field="username"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input placeholder="请输入用户名" autoComplete="username" />
          </Form.Item>
          <Form.Item
            label="密码"
            field="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password placeholder="请输入密码" autoComplete="current-password" />
          </Form.Item>
          <Button
            type="primary"
            htmlType="submit"
            long
            loading={loading}
            style={{ marginTop: 8, background: 'var(--accent)', borderColor: 'var(--accent)' }}
          >
            登录
          </Button>
        </Form>
      </Card>
    </div>
  )
}
