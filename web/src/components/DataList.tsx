import { useMemo, useState } from 'react'
import { Spin } from '@arco-design/web-react'

export interface DataListColumn<T> {
  title: string
  dataIndex?: string
  width?: number | string
  flex?: boolean
  render?: (value: any, record: T, index: number) => React.ReactNode
}

interface DataListProps<T> {
  columns: DataListColumn<T>[]
  data: T[]
  rowKey: string | ((record: T) => string)
  loading?: boolean
  pagination?: { pageSize: number } | false
  empty?: React.ReactNode
  className?: string
  onRow?: (record: T) => { onClick?: () => void; style?: React.CSSProperties }
  scroll?: { y?: number | string }
}

function getKey<T>(record: T, rowKey: string | ((record: T) => string)): string {
  if (typeof rowKey === 'function') return rowKey(record)
  const key = (record as Record<string, unknown>)[rowKey]
  return key !== undefined ? String(key) : Math.random().toString(36).slice(2)
}

function getValue<T>(record: T, dataIndex?: string): unknown {
  if (!dataIndex) return undefined
  return (record as Record<string, unknown>)[dataIndex]
}

export default function DataList<T>({
  columns,
  data,
  rowKey,
  loading,
  pagination,
  empty,
  className,
  onRow,
  scroll,
}: DataListProps<T>) {
  const [page, setPage] = useState(1)
  const pageSize = pagination && typeof pagination === 'object' ? pagination.pageSize : data.length

  const pagedData = useMemo(() => {
    if (!pagination) return data
    const start = (page - 1) * pageSize
    return data.slice(start, start + pageSize)
  }, [data, page, pageSize, pagination])

  const totalPages = pagination ? Math.ceil(data.length / pageSize) : 1

  const gridTemplate = useMemo(() => {
    const allHaveWidth = columns.every((c) => c.width)
    return columns
      .map((col) => {
        if (col.width) {
          const w = typeof col.width === 'number' ? `${col.width}px` : col.width
          if (col.flex) {
            return `minmax(${w}, 1fr)`
          }
          if (allHaveWidth) {
            const fr = typeof col.width === 'number' ? col.width : parseFloat(col.width) || 1
            return `minmax(${w}, ${fr}fr)`
          }
          return w
        }
        return 'minmax(0, 1fr)'
      })
      .join(' ')
  }, [columns])

  const listStyle: React.CSSProperties = scroll?.y
    ? { maxHeight: scroll.y, overflow: 'auto' }
    : {}

  return (
    <div className={`data-list-shell ${className || ''}`}>
      <div className="data-list-header" style={{ gridTemplateColumns: gridTemplate }}>
        {columns.map((col, i) => (
          <div key={i} className="data-list-header-cell">
            {col.title}
          </div>
        ))}
      </div>

      {loading ? (
        <div className="data-list-loading">
          <Spin size={28} />
        </div>
      ) : pagedData.length === 0 ? (
        <div className="data-list-empty">{empty}</div>
      ) : (
        <div className="data-list-body" style={listStyle}>
          {pagedData.map((record, idx) => {
            const rowProps = onRow ? onRow(record) : {}
            return (
              <div
                key={getKey(record, rowKey)}
                className="data-list-row"
                style={{
                  gridTemplateColumns: gridTemplate,
                  ...rowProps.style,
                }}
                onClick={rowProps.onClick}
              >
                {columns.map((col, cidx) => (
                  <div key={cidx} className="data-list-cell">
                    {col.render
                      ? col.render(getValue(record, col.dataIndex), record, idx)
                      : String(getValue(record, col.dataIndex) ?? '-')
                    }
                  </div>
                ))}
              </div>
            )
          })}
        </div>
      )}

      {!!pagination && totalPages > 1 && (
        <div className="data-list-pagination">
          <button
            className="data-list-page-btn"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            ←
          </button>
          <span className="data-list-page-info">
            {page} / {totalPages}
          </span>
          <button
            className="data-list-page-btn"
            disabled={page >= totalPages}
            onClick={() => setPage(page + 1)}
          >
            →
          </button>
        </div>
      )}
    </div>
  )
}
