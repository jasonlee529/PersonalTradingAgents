import { useState } from 'react'
import { Tabs, Card, Typography, Tag } from '@arco-design/web-react'

const TabPane = Tabs.TabPane
const { Text } = Typography

interface NewsItem {
  title: string
  content?: string
  source?: string
  published_at?: string
  url?: string
  relevance_score?: number
  institution?: string
  rating?: string
  target_price?: string
  predict_this_year_eps?: string
  predict_next_year_eps?: string
}

interface Props {
  news: NewsItem[]
  announcements: NewsItem[]
  researchReports: NewsItem[]
}

function NewsCard({ item }: { item: NewsItem }) {
  const titleEl = (
    <Text style={{ fontWeight: 500, flex: 1, color: 'var(--text-primary)', fontSize: 14, lineHeight: 1.5 }}>
      {item.title}
    </Text>
  )
  return (
    <Card
      style={{ marginBottom: 12, transition: 'all 0.2s ease' }}
      size="small"
      onMouseEnter={(e) => {
        e.currentTarget.style.transform = 'translateY(-2px)'
        e.currentTarget.style.boxShadow = 'var(--shadow-md)'
        e.currentTarget.style.borderColor = 'var(--border-accent)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = 'translateY(0)'
        e.currentTarget.style.boxShadow = 'var(--shadow-sm)'
        e.currentTarget.style.borderColor = 'var(--border-subtle)'
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
        {item.url ? (
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            style={{ textDecoration: 'none', flex: 1 }}
            onClick={(e) => e.stopPropagation()}
          >
            {titleEl}
          </a>
        ) : (
          titleEl
        )}
        {item.relevance_score !== undefined && item.relevance_score > 0 && (
          <Tag color="arcoblue" size="small">相关度: {(item.relevance_score * 100).toFixed(0)}%</Tag>
        )}
        {item.rating && <Tag color="orange" size="small">{item.rating}</Tag>}
      </div>
      <div style={{ marginTop: 8, color: 'var(--text-muted)', fontSize: 12, display: 'flex', gap: 8 }}>
        {(item.source || item.institution) && <span>{item.source || item.institution}</span>}
        {(item.source || item.institution) && item.published_at && <span style={{ color: 'var(--border-medium)' }}>|</span>}
        {item.published_at && <span>{item.published_at}</span>}
        {item.target_price && <span>目标价 {item.target_price}</span>}
      </div>
    </Card>
  )
}

function sortByTime(items: NewsItem[]) {
  return [...items].sort((a, b) => {
    const ta = a.published_at || ''
    const tb = b.published_at || ''
    return tb.localeCompare(ta)
  })
}

export default function NewsList({ news, announcements, researchReports }: Props) {
  const [activeTab, setActiveTab] = useState('news')

  const sortedNews = sortByTime(news)
  const sortedAnnouncements = sortByTime(announcements)
  const sortedReports = sortByTime(researchReports)

  return (
    <Tabs activeTab={activeTab} onChange={setActiveTab}>
      <TabPane key="news" title={`新闻 (${sortedNews.length})`}>
        {sortedNews.length === 0 ? <Text type="secondary">暂无新闻</Text> : sortedNews.map((item, i) => <NewsCard key={i} item={item} />)}
      </TabPane>
      <TabPane key="announcements" title={`公告 (${sortedAnnouncements.length})`}>
        {sortedAnnouncements.length === 0 ? <Text type="secondary">暂无公告</Text> : sortedAnnouncements.map((item, i) => <NewsCard key={i} item={item} />)}
      </TabPane>
      <TabPane key="reports" title={`研报 (${sortedReports.length})`}>
        {sortedReports.length === 0 ? <Text type="secondary">暂无研报</Text> : sortedReports.map((item, i) => <NewsCard key={i} item={item} />)}
      </TabPane>
    </Tabs>
  )
}
