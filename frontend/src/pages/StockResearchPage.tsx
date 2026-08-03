import { FormEvent, useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ExternalLink, Search } from 'lucide-react'
import { api } from '../api'
import { EmptyState } from '../components/EmptyState'
import { PriceChart } from '../components/PriceChart'
import { ResearchChat } from '../components/ResearchChat'
import { evidenceSourceDisplayName, FreshnessStatus, ResolutionStatus, sourceDisplayNames } from '../components/Status'
import { formatDataDate, formatDataTime } from '@/lib/date'
import { Alert, AlertAction, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from '@/components/ui/input-group'
import { Spinner } from '@/components/ui/spinner'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'

export function StockResearchPage({ initialCode, onOpenChats }: { initialCode: string; onOpenChats: () => void }) {
  const [input, setInput] = useState(initialCode)
  const [code, setCode] = useState(initialCode)
  useEffect(() => {
    setInput(initialCode)
    setCode(initialCode)
  }, [initialCode])
  const stock = useQuery({ queryKey: ['stock', code], queryFn: () => api.stock(code), enabled: Boolean(code) })
  const submit = (event: FormEvent) => { event.preventDefault(); setCode(input.trim()) }
  const data = stock.data
  const priceSources = data ? [evidenceSourceDisplayName(data.evidence_sources?.price)] : []
  const marketSources = data ? [evidenceSourceDisplayName(data.evidence_sources?.ma)] : []
  const financialSources = data ? [evidenceSourceDisplayName(data.evidence_sources?.fundamentals)] : []
  const priceAsOf = data?.price_as_of ?? data?.source.as_of ?? ''
  const marketAsOf = data?.market_as_of ?? data?.source.as_of ?? ''
  const priceFreshness = data?.evidence_resolution?.price?.freshness
  const priceResolution = data?.evidence_resolution?.price?.resolution
  const overviewRows = data ? [
    { label: 'RSI（近期涨跌强弱）', value: data.rsi.toFixed(0), note: data.rsi >= 72 ? '近期涨幅较快，建议继续观察' : '近期没有明显过热', sources: marketSources, times: [formatDataDate(marketAsOf)] },
    { label: '与 20 日平均价相比', value: data.price >= data.ma20 ? '高于平均价' : '低于平均价', note: '当前价与最近有效日线均值比较，不代表之后一定涨跌', sources: [...new Set([...priceSources, ...marketSources])], times: [`价格 ${formatDataDate(priceAsOf)}`, `均线 ${formatDataDate(marketAsOf)}`] },
    { label: '近 60 日最大跌幅', value: `${(data.max_drawdown_60d * 100).toFixed(1)}%`, note: '表示这段时间内出现过的最大下跌', sources: marketSources, times: [formatDataDate(marketAsOf)] },
  ] : []
  const fundamentalRows = data ? [
    { label: '市盈率（PE）', value: `${data.pe.toFixed(1)} 倍`, asOf: marketAsOf, publishedAt: undefined },
    { label: '净资产收益率（ROE）', value: `${data.roe.toFixed(1)}%`, asOf: data.financial_as_of, publishedAt: data.financial_published_at },
    { label: '利润增长', value: `${data.profit_growth.toFixed(1)}%`, asOf: data.financial_as_of, publishedAt: data.financial_published_at },
    { label: '营收增长', value: `${data.revenue_growth.toFixed(1)}%`, asOf: data.financial_as_of, publishedAt: data.financial_published_at },
    { label: '负债率', value: `${data.debt_ratio.toFixed(1)}%`, asOf: data.financial_as_of, publishedAt: data.financial_published_at },
  ] : []

  return <div className="flex min-w-0 flex-col gap-4">
    <Card className="stock-summary">
      <CardHeader className="stock-summary-main flex items-stretch">
        {data ? <>
          <div className="flex min-w-0 flex-1 items-stretch justify-between gap-6">
            <div className="flex min-w-0 flex-col justify-center gap-2 self-stretch">
              <CardTitle className="text-stock-hero truncate" title={data.name}>{data.name}</CardTitle>
              <CardDescription className="truncate font-mono" title={`${data.code} · ${data.sector}`}>{data.code} · {data.sector}</CardDescription>
            </div>
            <div className={cn('flex shrink-0 flex-col items-center justify-center gap-2 self-stretch', data.change_pct >= 0 ? 'text-stock-up' : 'text-stock-down')}>
              <span className="text-stock-price font-mono font-semibold tabular-nums">{data.price.toFixed(2)}</span>
              <span className="font-mono text-base font-medium tabular-nums">{data.change_pct >= 0 ? '+' : ''}{data.change_pct.toFixed(2)}%</span>
            </div>
          </div>
        </> : <CardTitle className="flex flex-1 items-center justify-center gap-2 text-muted-foreground"><Spinner aria-label="正在读取证券信息" />正在读取证券信息…</CardTitle>}
      </CardHeader>
      <CardContent className="stock-summary-tools">
        <form onSubmit={submit} className="w-full"><InputGroup><InputGroupInput value={input} onChange={(event) => setInput(event.currentTarget.value)} aria-label="输入股票代码" /><InputGroupAddon align="inline-end"><InputGroupButton type="submit" size="icon-xs" variant="default" disabled={stock.isFetching} aria-label="查看股票">{stock.isFetching ? <Spinner /> : <Search />}</InputGroupButton></InputGroupAddon></InputGroup></form>
        {data ? <div className="flex min-w-0 flex-wrap items-center gap-2">
          {priceSources.map((source) => <Badge variant="outline" key={`price-${source}`}>{source}</Badge>)}
          <ResolutionStatus resolution={priceResolution} />
          <FreshnessStatus freshness={priceFreshness} />
          <span className="whitespace-nowrap text-sm text-muted-foreground">数据日期 <span className="tabular-nums text-foreground">{formatDataDate(priceAsOf)}</span></span>
          <span className="whitespace-nowrap text-sm text-muted-foreground">获取于 <span className="tabular-nums text-foreground">{formatDataTime(data.price_fetched_at)}</span></span>
          {data.price_note ? <span className="text-sm text-muted-foreground">{data.price_note}</span> : null}
        </div> : null}
      </CardContent>
    </Card>

    {stock.isError ? <Card><CardContent><EmptyState title="未找到研究数据" description={stock.error.message} /></CardContent></Card> : null}
    {data ? <>
      <Card>
        <CardHeader><CardTitle>价格走势</CardTitle><CardDescription>显示研究日期之前近 120 个交易日的日 K 线与成交量。</CardDescription><CardAction><div className="flex flex-wrap items-center justify-end gap-2">{marketSources.map((source) => <Badge variant="outline" key={source}>{source}</Badge>)}<span className="text-sm text-muted-foreground">截至 {formatDataDate(marketAsOf)}</span><span className="whitespace-nowrap font-mono text-sm text-muted-foreground tabular-nums">MA20 {data.ma20.toFixed(2)} · MA60 {data.ma60.toFixed(2)}</span></div></CardAction></CardHeader>
        <CardContent><PriceChart data={data.history} /></CardContent>
      </Card>

      <Card>
        <CardContent>
          <Tabs defaultValue="overview">
            <TabsList><TabsTrigger value="overview">价格指标</TabsTrigger><TabsTrigger value="fundamentals">经营数据</TabsTrigger><TabsTrigger value="news">新闻</TabsTrigger><TabsTrigger value="risk">风险</TabsTrigger></TabsList>
            <TabsContent value="overview"><Table><TableHeader><TableRow><TableHead>指标</TableHead><TableHead className="text-right">数值</TableHead><TableHead>说明</TableHead><TableHead>来源</TableHead><TableHead>数据时间</TableHead></TableRow></TableHeader><TableBody>{overviewRows.map((item) => <TableRow key={item.label}><TableCell className="font-medium">{item.label}</TableCell><TableCell className="whitespace-nowrap text-right font-mono tabular-nums">{item.value}</TableCell><TableCell className="text-muted-foreground">{item.note}</TableCell><TableCell><div className="flex flex-wrap gap-2">{item.sources.map((source) => <Badge variant="outline" key={source}>{source}</Badge>)}</div></TableCell><TableCell><div className="flex min-w-0 flex-wrap gap-x-2 gap-y-1 text-muted-foreground tabular-nums">{item.times.map((time) => <span className="whitespace-nowrap" key={time}>{time}</span>)}</div></TableCell></TableRow>)}</TableBody></Table></TabsContent>
            <TabsContent value="fundamentals"><Table><TableHeader><TableRow><TableHead>指标</TableHead><TableHead className="text-right">数值</TableHead><TableHead>来源</TableHead><TableHead>数据日期</TableHead><TableHead>发布时间</TableHead></TableRow></TableHeader><TableBody>{fundamentalRows.map((item) => <TableRow key={item.label}><TableCell className="font-medium">{item.label}</TableCell><TableCell className="whitespace-nowrap text-right font-mono tabular-nums">{item.value}</TableCell><TableCell><div className="flex flex-wrap gap-2">{financialSources.map((source) => <Badge variant="outline" key={source}>{source}</Badge>)}</div></TableCell><TableCell className="whitespace-nowrap text-muted-foreground tabular-nums">{formatDataDate(item.asOf)}</TableCell><TableCell className="whitespace-nowrap text-muted-foreground tabular-nums">{formatDataDate(item.publishedAt, '不适用')}</TableCell></TableRow>)}</TableBody></Table></TabsContent>
            <TabsContent value="news" className="flex flex-col gap-4">
              {data.content_errors?.length ? <Alert><AlertTitle>部分资讯未更新</AlertTitle><AlertDescription>{data.content_errors.join('；')}</AlertDescription></Alert> : null}
              <div className="flex min-w-0 flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
                <span className="whitespace-nowrap">获取于 {formatDataTime(data.content_fetched_at)}</span>
                <span className="whitespace-nowrap">新闻 {data.content_scope?.news ?? '最近记录'}</span>
                <span className="whitespace-nowrap">公告 {data.content_scope?.notices ?? '历史记录'}</span>
              </div>
              {data.news.length ? <Table>
                <TableHeader><TableRow><TableHead>类型</TableHead><TableHead>标题</TableHead><TableHead>发布机构</TableHead><TableHead>发布时间</TableHead><TableHead>来源</TableHead><TableHead className="w-12"><span className="sr-only">查看</span></TableHead></TableRow></TableHeader>
                <TableBody>{data.news.map((item) => <TableRow key={`${item.published_at}-${item.url}`}>
                  <TableCell className="whitespace-nowrap"><div className="flex flex-col"><span>{item.kind}</span><span className="text-xs text-muted-foreground">{item.content_level === 'summary' ? '摘要' : '仅标题'}</span></div></TableCell>
                  <TableCell><div className="min-w-64 max-w-3xl"><div className="font-medium">{item.title}</div>{item.summary ? <div className="mt-1 line-clamp-2 text-sm text-muted-foreground">{item.summary}</div> : null}</div></TableCell>
                  <TableCell className="whitespace-nowrap">{item.publisher}</TableCell>
                  <TableCell className="whitespace-nowrap text-muted-foreground tabular-nums">{item.kind === '公告' ? formatDataDate(item.published_at) : formatDataTime(item.published_at)}</TableCell>
                  <TableCell><div className="flex flex-wrap items-center gap-2"><Badge variant="outline">{evidenceSourceDisplayName(item.source)}</Badge><FreshnessStatus freshness={item.freshness} /></div></TableCell>
                  <TableCell><Button render={<a href={item.url} target="_blank" rel="noreferrer" />} variant="ghost" size="icon-sm" aria-label={`查看${item.kind}原文`} title={`查看${item.kind}原文`}><ExternalLink /></Button></TableCell>
                </TableRow>)}</TableBody>
              </Table> : <EmptyState title="暂无可核验资讯" description="当前数据 API 没有返回这只股票的新闻或公告；研究结论不会假设不存在的信息。" />}
            </TabsContent>
            <TabsContent value="risk"><Alert><AlertTitle>哪些情况需要重新判断</AlertTitle><AlertDescription>过去 60 日价格波动约 {(data.volatility_60d * 100).toFixed(1)}%，最大跌幅约 {(data.max_drawdown_60d * 100).toFixed(1)}%。还需要关注行业变化、公司公告、现金流和估值。</AlertDescription><AlertAction><div className="flex flex-wrap items-center gap-2">{marketSources.map((source) => <Badge variant="outline" key={source}>{source}</Badge>)}<span className="text-xs text-muted-foreground">截至 {formatDataDate(marketAsOf)}</span></div></AlertAction></Alert></TabsContent>
          </Tabs>
        </CardContent>
      </Card>
      <ResearchChat stockCode={data.code} onOpenChats={onOpenChats} />
    </> : null}
  </div>
}
