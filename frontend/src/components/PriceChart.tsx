import { useEffect, useRef } from 'react'
import { CandlestickSeries, ColorType, createChart, HistogramSeries, TickMarkType, type CandlestickData, type HistogramData, type Time } from 'lightweight-charts'

interface PricePoint {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

function timeParts(time: Time) {
  if (typeof time === 'string') {
    const [year, month, day] = time.split('-').map(Number)
    return { year, month, day }
  }
  if (typeof time === 'number') {
    const value = new Date(time * 1000)
    return { year: value.getFullYear(), month: value.getMonth() + 1, day: value.getDate() }
  }
  return { year: time.year, month: time.month, day: time.day }
}

export function PriceChart({ data }: { data: PricePoint[] }) {
  const container = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!container.current) return
    const chart = createChart(container.current, {
      autoSize: true,
      height: 330,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#909296', attributionLogo: false },
      localization: {
        locale: 'zh-CN',
        dateFormat: 'yyyy-MM-dd',
        timeFormatter: (time: Time) => {
          const { year, month, day } = timeParts(time)
          return `${year}年${month}月${day}日`
        },
      },
      grid: { vertLines: { color: 'rgba(120,130,140,.10)' }, horzLines: { color: 'rgba(120,130,140,.10)' } },
      rightPriceScale: { borderColor: 'rgba(120,130,140,.22)' },
      timeScale: {
        borderColor: 'rgba(120,130,140,.22)',
        tickMarkFormatter: (time: Time, type: TickMarkType) => {
          const { year, month, day } = timeParts(time)
          if (type === TickMarkType.Year) return `${year}年`
          if (type === TickMarkType.Month) return `${month}月`
          return `${month}月${day}日`
        },
      },
    })
    const styles = getComputedStyle(container.current)
    const upColor = styles.getPropertyValue('--stock-up').trim() || '#fb7185'
    const downColor = styles.getPropertyValue('--stock-down').trim() || '#4ade80'
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor,
      downColor,
      borderVisible: false,
      wickUpColor: upColor,
      wickDownColor: downColor,
    })
    candleSeries.setData(data.map((item) => ({
      time: item.date as Time,
      open: item.open,
      high: item.high,
      low: item.low,
      close: item.close,
    })) as CandlestickData[])

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: '',
      lastValueVisible: false,
      priceLineVisible: false,
    })
    volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })
    volumeSeries.setData(data.map((item) => ({
      time: item.date as Time,
      value: item.volume,
      color: item.close >= item.open ? 'rgba(251, 113, 133, 0.35)' : 'rgba(74, 222, 128, 0.35)',
    })) as HistogramData[])
    chart.timeScale().fitContent()
    return () => chart.remove()
  }, [data])
  return <div className="price-chart" ref={container} />
}
