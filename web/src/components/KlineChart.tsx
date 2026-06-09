import { useMemo, useState } from 'react'
import ReactEChartsCore from 'echarts-for-react/lib/core'
import * as echarts from 'echarts/core'
import { BarChart, CandlestickChart } from 'echarts/charts'
import {
  DataZoomComponent,
  GridComponent,
  TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { Button } from '@arco-design/web-react'

echarts.use([
  BarChart,
  CandlestickChart,
  DataZoomComponent,
  GridComponent,
  TooltipComponent,
  CanvasRenderer,
])

interface KlineRecord {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

interface Props {
  data: KlineRecord[]
  height?: number
}

type Period = '1M' | '3M' | '6M' | '1Y' | '3Y' | 'ALL'

const PERIODS: { label: string; value: Period }[] = [
  { label: '1月', value: '1M' },
  { label: '3月', value: '3M' },
  { label: '6月', value: '6M' },
  { label: '1年', value: '1Y' },
  { label: '3年', value: '3Y' },
  { label: '上市来', value: 'ALL' },
]

function getStartDate(period: Period, lastDate: string): string {
  const d = new Date(lastDate)
  switch (period) {
    case '1M':
      d.setMonth(d.getMonth() - 1)
      break
    case '3M':
      d.setMonth(d.getMonth() - 3)
      break
    case '6M':
      d.setMonth(d.getMonth() - 6)
      break
    case '1Y':
      d.setFullYear(d.getFullYear() - 1)
      break
    case '3Y':
      d.setFullYear(d.getFullYear() - 3)
      break
    case 'ALL':
      return ''
  }
  return d.toISOString().slice(0, 10)
}

export default function KlineChart({ data, height = 400 }: Props) {
  const [period, setPeriod] = useState<Period>('1M')

  const displayData = useMemo(() => {
    if (period === 'ALL' || data.length === 0) return data
    const start = getStartDate(period, data[data.length - 1].date)
    return data.filter((d) => d.date >= start)
  }, [data, period])

  const dates = displayData.map((d) => d.date)
  const klineData = displayData.map((d) => [d.open, d.close, d.low, d.high])
  const volumes = displayData.map((d) => d.volume)

  const textColor = '#9494a0'
  const gridColor = 'rgba(148, 148, 160, 0.08)'
  const splitAreaColor = 'rgba(148, 148, 160, 0.03)'

  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      backgroundColor: 'rgba(15, 15, 22, 0.96)',
      borderColor: 'rgba(225, 29, 72, 0.25)',
      borderWidth: 1,
      textStyle: { color: '#e8e8ec', fontSize: 12 },
      padding: [12, 16],
      formatter: (params: Array<{ seriesName: string; data: number[]; dataIndex: number }>) => {
        if (!params || params.length === 0) return ''
        const date = dates[params[0].dataIndex]
        const d = displayData[params[0].dataIndex]
        const color = d.close >= d.open ? '#ff3b30' : '#34c759'
        const sign = d.close >= d.open ? '+' : ''
        const change = d.close - d.open
        const changePct = (change / d.open) * 100
        return `
          <div style="font-weight:600;margin-bottom:8px;font-size:13px;color:#e8e8ec;">${date}</div>
          <div style="display:grid;grid-template-columns:auto auto;gap:4px 16px;font-size:12px;">
            <span style="color:#9494a0;">开盘价</span> <span style="font-weight:500;">${d.open.toFixed(2)}</span>
            <span style="color:#9494a0;">收盘价</span> <span style="font-weight:500;color:${color};">${d.close.toFixed(2)}</span>
            <span style="color:#9494a0;">最高价</span> <span style="font-weight:500;">${d.high.toFixed(2)}</span>
            <span style="color:#9494a0;">最低价</span> <span style="font-weight:500;">${d.low.toFixed(2)}</span>
            <span style="color:#9494a0;">涨跌额</span> <span style="font-weight:500;color:${color};">${sign}${change.toFixed(2)}</span>
            <span style="color:#9494a0;">涨跌幅</span> <span style="font-weight:500;color:${color};">${sign}${changePct.toFixed(2)}%</span>
            <span style="color:#9494a0;">成交量</span> <span style="font-weight:500;">${d.volume.toLocaleString()}</span>
          </div>
        `
      },
    },
    grid: [
      { left: '10%', right: '8%', height: '55%' },
      { left: '10%', right: '8%', top: '70%', height: '16%' },
    ],
    xAxis: [
      {
        type: 'category',
        data: dates,
        scale: true,
        boundaryGap: false,
        axisLine: { onZero: false, lineStyle: { color: gridColor } },
        axisLabel: { color: textColor, fontSize: 11 },
        splitLine: { show: false },
        splitNumber: 20,
      },
      {
        type: 'category',
        gridIndex: 1,
        data: dates,
        axisLabel: { show: false },
        axisLine: { lineStyle: { color: gridColor } },
      },
    ],
    yAxis: [
      {
        scale: true,
        axisLabel: { color: textColor, fontSize: 11 },
        axisLine: { lineStyle: { color: gridColor } },
        splitLine: { lineStyle: { color: gridColor } },
        splitArea: { show: true, areaStyle: { color: [splitAreaColor, 'transparent'] } },
      },
      {
        scale: true,
        gridIndex: 1,
        splitNumber: 2,
        axisLabel: { show: false },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
      },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: 0, end: 100 },
      {
        show: true,
        xAxisIndex: [0, 1],
        type: 'slider',
        top: '92%',
        start: 0,
        end: 100,
        borderColor: gridColor,
        fillerColor: 'rgba(225, 29, 72, 0.15)',
        handleStyle: { color: '#e11d48' },
        textStyle: { color: textColor },
      },
    ],
    series: [
      {
        name: 'K线',
        type: 'candlestick',
        data: klineData,
        itemStyle: {
          color: '#ff3b30',
          color0: '#34c759',
          borderColor: '#ff3b30',
          borderColor0: '#34c759',
        },
      },
      {
        name: '成交量',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: volumes,
        itemStyle: {
          color: (params: { dataIndex: number }) => {
            const close = displayData[params.dataIndex].close
            const open = displayData[params.dataIndex].open
            return close >= open ? '#ff3b30' : '#34c759'
          },
        },
      },
    ],
  }

  return (
    <div style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 4, marginBottom: 8 }}>
        {PERIODS.map((p) => (
          <Button
            key={p.value}
            size="mini"
            type={period === p.value ? 'primary' : 'secondary'}
            status="danger"
            onClick={() => setPeriod(p.value)}
          >
            {p.label}
          </Button>
        ))}
      </div>
      <ReactEChartsCore
        echarts={echarts}
        option={option}
        style={{ height }}
        opts={{ renderer: 'canvas' }}
      />
    </div>
  )
}
