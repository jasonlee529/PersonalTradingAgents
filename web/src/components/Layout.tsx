import { useState, useEffect, useCallback } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Layout as ArcoLayout } from '@arco-design/web-react'
import { useAuthStore } from '../store/useAuthStore'
import {
  IconDashboard,
  IconHome,
  IconArrowRise,
  IconFire,
  IconRobot,
  IconCompass,
  IconSettings,
  IconMenuFold,
  IconMenuUnfold,
  IconBook,
  IconList,
  IconStar,
} from '@arco-design/web-react/icon'

const { Sider, Header, Content } = ArcoLayout

const menuItems = [
  { key: '/', icon: IconHome, label: '首页' },
  { key: '/portfolio', icon: IconDashboard, label: '我的持仓' },
  { key: '/stock', icon: IconArrowRise, label: '股票详情' },
  { key: '/stocks', icon: IconList, label: '股票列表' },
  { key: '/limit-up', icon: IconFire, label: '涨停池' },
  { key: '/chanlun', icon: IconStar, label: '缠论信号' },
  { key: '/sectors', icon: IconCompass, label: '今日方向' },
  { key: '/analysis', icon: IconRobot, label: 'AI分析' },
  { key: '/wiki', icon: IconBook, label: '知识库' },
  { key: '/settings', icon: IconSettings, label: '设置' },
]

export default function Layout({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate()
  const location = useLocation()
  const username = useAuthStore((state) => state.username)
  const logout = useAuthStore((state) => state.logout)
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(false)

  const checkMobile = useCallback(() => {
    const mobile = window.innerWidth <= 768
    setIsMobile(mobile)
    if (!mobile) setMobileOpen(false)
  }, [])

  useEffect(() => {
    checkMobile()
    window.addEventListener('resize', checkMobile)
    return () => window.removeEventListener('resize', checkMobile)
  }, [checkMobile])

  // 路由变化时关闭移动端侧边栏
  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  const isMenuActive = (key: string) => {
    if (location.pathname === key) return true
    if (key !== '/' && location.pathname.startsWith(`${key}/`)) return true
    if (key === '/wiki' && location.pathname.startsWith('/knowledge/')) return true
    return false
  }
  const activeItem = menuItems.find((item) => isMenuActive(item.key))
  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  const siderContent = (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', padding: '28px 16px 20px', overflow: 'hidden' }}>
      {/* Brand */}
      <div className="sider-brand" style={{ flexShrink: 0 }}>
        <div className="sider-brand-mark">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" style={{ color: 'var(--text-primary)' }}>
            <circle cx="12" cy="4.5" r="2.5" fill="currentColor" />
            <circle cx="5" cy="11" r="2.5" fill="currentColor" />
            <circle cx="19" cy="11" r="2.5" fill="currentColor" />
            <circle cx="8.5" cy="18.5" r="2.5" fill="currentColor" />
            <circle cx="15.5" cy="18.5" r="2.5" fill="currentColor" />
            <path d="M12 7v3M5 13.5l3 2.5M19 13.5l-3 2.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        </div>
        {(!collapsed || isMobile) && (
          <div className="sider-brand-text">
            <div className="sider-brand-title">个人AI投研助手</div>
            <div className="sider-brand-sub">PersonalTradingAgents</div>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="nav-menu" style={{ flex: 1, overflowY: 'auto', minHeight: 0, marginTop: 8, marginBottom: 8 }}>
        {menuItems.map((item) => {
          const Icon = item.icon
          const isActive = isMenuActive(item.key)
          return (
            <div
              key={item.key}
              className={`nav-item ${isActive ? 'nav-item-active' : ''} ${collapsed && !isMobile ? 'nav-item-collapsed' : ''}`}
              onClick={() => navigate(item.key)}
            >
              <Icon />
              <span className="nav-label">{item.label}</span>
            </div>
          )
        })}
      </nav>

      {/* Footer status */}
      {(!collapsed || isMobile) && (
        <div className="sider-footer" style={{ flexShrink: 0 }}>
          <div className="sider-footer-inner">
            <div className="sider-footer-row">
              <div className="sider-footer-status" />
              <span className="sider-footer-label">系统运行中</span>
            </div>
            <div className="sider-footer-version">v0.1.0</div>
          </div>
        </div>
      )}
    </div>
  )

  return (
    <ArcoLayout style={{ minHeight: '100dvh', background: 'var(--bg-base)' }}>
      {/* 移动端遮罩层 */}
      {isMobile && mobileOpen && (
        <div className="mobile-backdrop" onClick={() => setMobileOpen(false)} />
      )}

      {/* 桌面端侧边栏 */}
      {!isMobile && (
        <Sider
          trigger={null}
          collapsible
          collapsed={collapsed}
          onCollapse={setCollapsed}
          width={244}
          collapsedWidth={72}
          style={{
            background: 'var(--bg-sider)',
            borderRight: '1px solid var(--border-subtle)',
            boxShadow: 'none',
          }}
        >
          {siderContent}
        </Sider>
      )}

      {/* 移动端抽屉侧边栏 */}
      {isMobile && (
        <div className={`mobile-sider ${mobileOpen ? 'mobile-sider-open' : ''}`}>
          {siderContent}
        </div>
      )}

      <ArcoLayout style={{ background: 'var(--bg-base)' }}>
        <Header
          style={{
            background: 'var(--bg-sider)',
            padding: isMobile ? '0 16px' : '0 32px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid var(--border-subtle)',
            boxShadow: 'none',
            zIndex: 1,
            height: 60,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: isMobile ? 12 : 16 }}>
            <button
              onClick={() => isMobile ? setMobileOpen(!mobileOpen) : setCollapsed(!collapsed)}
              className="header-menu-btn"
              style={{
                background: 'transparent',
                border: '1px solid var(--border-medium)',
                borderRadius: 'var(--radius-md)',
                color: 'var(--text-secondary)',
                cursor: 'pointer',
                padding: '6px 8px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'all 0.2s ease',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = 'var(--border-accent)'
                e.currentTarget.style.color = 'var(--text-primary)'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = 'var(--border-medium)'
                e.currentTarget.style.color = 'var(--text-secondary)'
              }}
            >
              {isMobile ? (
                <IconMenuFold style={{ fontSize: 16 }} />
              ) : collapsed ? (
                <IconMenuUnfold style={{ fontSize: 16 }} />
              ) : (
                <IconMenuFold style={{ fontSize: 16 }} />
              )}
            </button>
            <span
              className="header-title"
              style={{
                color: 'var(--text-primary)',
                fontSize: isMobile ? 14 : 15,
                fontWeight: 600,
                letterSpacing: '-0.01em',
              }}
            >
              {activeItem?.label || '投研助手'}
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: isMobile ? 10 : 14 }}>
            {!isMobile && (
              <span
                style={{
                  fontSize: 12,
                  color: 'var(--text-muted)',
                  fontWeight: 600,
                  letterSpacing: '0.02em',
                }}
              >
                {username || 'jason'}
              </span>
            )}
            {!isMobile && (
              <span
                style={{
                  fontSize: 12,
                  color: 'var(--text-dim)',
                  fontWeight: 500,
                  letterSpacing: '0.02em',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                {new Date().toLocaleDateString('zh-CN', {
                  year: 'numeric',
                  month: '2-digit',
                  day: '2-digit',
                })}
              </span>
            )}
            <button
              onClick={handleLogout}
              style={{
                background: 'transparent',
                border: '1px solid var(--border-medium)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--text-secondary)',
                cursor: 'pointer',
                padding: '5px 10px',
                fontSize: 12,
                fontWeight: 600,
                transition: 'all 0.2s ease',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = 'var(--border-accent)'
                e.currentTarget.style.color = 'var(--text-primary)'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = 'var(--border-medium)'
                e.currentTarget.style.color = 'var(--text-secondary)'
              }}
            >
              退出
            </button>
          </div>
        </Header>

        <Content
          style={{
            padding: isMobile ? '16px' : '28px',
            background: 'var(--bg-base)',
          }}
        >
          <div
            style={{
              minHeight: isMobile ? 'calc(100dvh - 76px)' : 'calc(100dvh - 116px)',
            }}
            className="animate-fade-in"
          >
            {children}
          </div>
        </Content>
      </ArcoLayout>
    </ArcoLayout>
  )
}
