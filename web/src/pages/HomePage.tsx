import { Button } from '@arco-design/web-react'
import {
  IconArrowRight,
  IconBook,
  IconCompass,
  IconRobot,
  IconThunderbolt,
} from '@arco-design/web-react/icon'
import { useNavigate } from 'react-router-dom'

const featureCards = [
  {
    icon: IconRobot,
    title: '多智能体投研',
    text: '把市场、新闻、基本面、风险和交易决策拆给不同角色协作，形成更完整的分析链路。',
  },
  {
    icon: IconCompass,
    title: '今日方向扫描',
    text: '围绕板块热度、政策信号、资金偏好和产业链线索，快速筛出值得继续跟踪的方向。',
  },
  {
    icon: IconBook,
    title: '知识沉淀',
    text: '将新闻、研究材料和分析结论沉入本地知识库，让后续判断能复用上下文。',
  },
]

const pipelineSteps = ['数据采集', '语义检索', '角色辩论', '风险复核', '交易建议']

export default function HomePage() {
  const navigate = useNavigate()

  return (
    <main className="home-page">
      <section className="home-hero">
        <div className="home-hero-copy">
          <span className="home-eyebrow">PERSONAL TRADING AGENTS</span>
          <div className="home-wisdom">
            <span className="home-wisdom-pulse" />
            <span className="home-wisdom-text">
              人与人之间性格的差异很大，战胜不了自己，也成就不了自己
            </span>
          </div>
          <h1>面向个人投资者的 AI 投研控制台</h1>
          <p>
            聚合行情、新闻、知识库和多智能体分析流程，把分散信息整理成可追踪、可复盘的投研判断。
          </p>
          <div className="home-actions">
            <Button type="primary" size="large" icon={<IconThunderbolt />} onClick={() => navigate('/analysis')}>
              开始 AI 分析
            </Button>
            <Button size="large" icon={<IconArrowRight />} onClick={() => navigate('/portfolio')}>
              查看持仓
            </Button>
          </div>
        </div>

        <div className="home-orbit" aria-hidden="true">
          <div className="home-orbit-grid" />
          <div className="home-core">
            <span>AI</span>
          </div>
          <div className="home-ring home-ring-one" />
          <div className="home-ring home-ring-two" />
          <div className="home-node home-node-market">Market</div>
          <div className="home-node home-node-news">News</div>
          <div className="home-node home-node-risk">Risk</div>
          <div className="home-node home-node-memory">Memory</div>
        </div>
      </section>

      <section className="home-feature-grid">
        {featureCards.map((card, index) => {
          const Icon = card.icon
          return (
            <article className="home-feature-card animate-fade-in-up" style={{ animationDelay: `${index * 0.06}s` }} key={card.title}>
              <div className="home-feature-icon">
                <Icon />
              </div>
              <h2>{card.title}</h2>
              <p>{card.text}</p>
            </article>
          )
        })}
      </section>

      <section className="home-pipeline">
        <div>
          <span className="home-section-label">FLOW</span>
          <h2>从原始信号到可复盘结论</h2>
        </div>
        <div className="home-pipeline-track">
          {pipelineSteps.map((step, index) => (
            <div className="home-pipeline-step" key={step}>
              <span>{String(index + 1).padStart(2, '0')}</span>
              <strong>{step}</strong>
            </div>
          ))}
        </div>
      </section>
    </main>
  )
}
