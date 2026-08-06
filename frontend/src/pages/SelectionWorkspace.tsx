import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { AlertTriangle, Check, ChevronDown, Database, History, Play, ShieldCheck, Sparkles } from 'lucide-react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { api, eventUrl } from '../api'
import type { Candidate, SelectionRun, StrategyId } from '../types'
import { CandidateTable } from '../components/CandidateTable'
import { EmptyState } from '../components/EmptyState'
import { ResearchChat } from '../components/ResearchChat'
import { evidenceSourceDisplayName, FreshnessStatus, recommendationClassName, recommendationLabel, recommendationVariant, ResolutionStatus, semanticBadgeClassName, sourceDisplayNames, SourceStatus } from '../components/Status'
import { formatDataDate, formatDataTime, formatEvidenceTime } from '@/lib/date'
import { contentOffset, reducedFadeTransition, resultStagger, spatialSpring } from '@/lib/motion'
import { cn } from '@/lib/utils'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldSeparator, FieldSet, FieldLegend } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Progress, ProgressLabel, ProgressValue } from '@/components/ui/progress'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'

const riskOptions = [
  { value: 'conservative', label: '稳健' }, { value: 'balanced', label: '平衡' }, { value: 'active', label: '积极' },
]
const horizonOptions = [
  { value: 'short', label: '短期 1–4 周' }, { value: 'medium', label: '中期 1–6 月' }, { value: 'long', label: '长期 6 月以上' },
]
const dataModeOptions = [{ value: 'latest', label: '最新数据' }, { value: 'historical', label: '历史数据' }]
const riskLabels = { conservative: '稳健', balanced: '平衡', active: '积极' } as const
const horizonLabels = { short: '短期 1–4 周', medium: '中期 1–6 月', long: '长期 6 月以上' } as const
const strategyLabels = { trend: '趋势', quality: '质量', stability: '平稳' } as const
function HistoricalConditions({ run }: { run: SelectionRun }) {
  const [open, setOpen] = useState(false)
  const summary = `${riskLabels[run.request.risk_profile]} · ${horizonLabels[run.request.horizon]} · ${strategyLabels[run.request.strategy]} · ${formatDataDate(run.request.as_of)}`
  return <Collapsible open={open} onOpenChange={setOpen} className="min-w-0 self-start">
    <Card className="selection-controls">
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><History />本次研究</CardTitle>
        <CardDescription className="break-words">{summary}</CardDescription>
        <CardAction><CollapsibleTrigger render={<Button variant="outline" size="sm" />}><ChevronDown data-icon="inline-start" className="transition-transform group-aria-expanded/button:rotate-180" />{open ? '收起' : '查看条件'}</CollapsibleTrigger></CardAction>
      </CardHeader>
      <CollapsibleContent className="h-(--collapsible-panel-height) overflow-hidden opacity-100 transition-[height,opacity,transform] duration-[260ms] ease-[cubic-bezier(0.16,1,0.3,1)] data-starting-style:h-0 data-starting-style:-translate-y-2 data-starting-style:opacity-0 data-ending-style:h-0 data-ending-style:-translate-y-2 data-ending-style:opacity-0 motion-reduce:transform-none motion-reduce:duration-120">
        <CardContent><Table><TableHeader><TableRow><TableHead>研究条件</TableHead><TableHead className="text-right">本次选择</TableHead></TableRow></TableHeader><TableBody>
          <TableRow><TableCell className="text-muted-foreground">风险承受</TableCell><TableCell className="text-right font-medium">{riskLabels[run.request.risk_profile]}</TableCell></TableRow>
          <TableRow><TableCell className="text-muted-foreground">投资周期</TableCell><TableCell className="text-right font-medium">{horizonLabels[run.request.horizon]}</TableCell></TableRow>
          <TableRow><TableCell className="text-muted-foreground">研究视角</TableCell><TableCell className="text-right font-medium">{strategyLabels[run.request.strategy]}</TableCell></TableRow>
          <TableRow><TableCell className="text-muted-foreground">研究日期</TableCell><TableCell className="whitespace-nowrap text-right font-medium tabular-nums">{formatDataDate(run.request.as_of)}</TableCell></TableRow>
          <TableRow><TableCell className="text-muted-foreground">保存时间</TableCell><TableCell className="whitespace-nowrap text-right font-medium tabular-nums">{formatDataTime(run.created_at)}</TableCell></TableRow>
        </TableBody></Table></CardContent>
        <CardFooter className="flex min-w-0 flex-wrap items-center gap-2"><SourceStatus status={run.provider.status} />{sourceDisplayNames(run.provider.source).map((source) => <Badge variant="outline" key={source}>{source}</Badge>)}<span className="text-sm text-muted-foreground">{run.provider.status === 'historical' ? `行情日期 ${formatDataDate(run.provider.as_of)}` : `价格获取于 ${formatEvidenceTime(run.provider.as_of, run.provider.fetched_at)}`}</span></CardFooter>
      </CollapsibleContent>
    </Card>
  </Collapsible>
}

export function SelectionWorkspace({ onOpenResearch, onOpenChats, onRunningChange, historicalRunId }: { onOpenResearch: (code: string) => void; onOpenChats: () => void; onRunningChange?: (running: boolean) => void; historicalRunId?: string }) {
  const reduceMotion = useReducedMotion()
  const [risk, setRisk] = useState<SelectionRun['request']['risk_profile']>('balanced')
  const [horizon, setHorizon] = useState<SelectionRun['request']['horizon']>('medium')
  const [strategy, setStrategy] = useState<StrategyId>('trend')
  const [asOf, setAsOf] = useState(new Date(Date.now() - 86_400_000).toISOString().slice(0, 10))
  const [dataMode, setDataMode] = useState<'latest' | 'historical'>('latest')
  const [selected, setSelected] = useState<Candidate | null>(null)
  const [runId, setRunId] = useState<string | null>(() => historicalRunId ?? null)
  const [stage, setStage] = useState({ value: 0, label: '等待开始', count: '0 / 4' })
  const strategies = useQuery({ queryKey: ['strategies'], queryFn: api.strategies, enabled: !historicalRunId })
  const createRun = useMutation({
    mutationFn: () => api.createRun({
      risk_profile: risk,
      horizon,
      strategy,
      as_of: dataMode === 'latest' ? new Date().toISOString().slice(0, 10) : asOf,
      data_mode: 'live',
    }),
    onMutate: () => {
      setRunId(null)
      setSelected(null)
      setStage({ value: 0, label: '正在创建任务', count: '0 / 4' })
    },
    onSuccess: (created) => setRunId(created.id),
  })
  const runQuery = useQuery({
    queryKey: ['selection-run', runId],
    queryFn: () => api.run(runId!),
    enabled: Boolean(runId),
  })
  const run = runQuery.data ?? createRun.data
  const runStatus = run?.status
  useEffect(() => {
    if (!runId || !runStatus || !['pending', 'running'].includes(runStatus)) return
    const events = new EventSource(eventUrl(`/api/v1/selection-runs/${runId}/events`))
    const stages: Record<string, { value: number; label: string; count: string }> = {
      queued: { value: 0, label: '任务已创建', count: '0 / 4' },
      preparing: { value: 25, label: '准备真实数据', count: '1 / 4' },
      filtering: { value: 50, label: '排除不合适的股票', count: '2 / 4' },
      comparing: { value: 75, label: '比较候选股票', count: '3 / 4' },
      complete: { value: 100, label: '研究完成', count: '4 / 4' },
    }
    const handleStage = (event: MessageEvent) => {
      const payload = JSON.parse(event.data) as { stage?: string; label?: string }
      const next = payload.stage ? stages[payload.stage] : undefined
      if (next) setStage({ ...next, label: payload.label || next.label })
    }
    const handleFailure = (event: MessageEvent) => {
      const payload = JSON.parse(event.data) as { message?: string }
      setStage((current) => ({ ...current, label: payload.message || '研究未完成' }))
    }
    const handleEnd = () => {
      events.close()
      void runQuery.refetch()
    }
    events.addEventListener('stage', handleStage)
    events.addEventListener('error', handleFailure as EventListener)
    events.addEventListener('end', handleEnd)
    return () => events.close()
  }, [runId, runStatus, runQuery.refetch])
  useEffect(() => {
    if (runStatus === 'complete') setSelected(run?.candidates[0] ?? null)
  }, [run, runStatus])
  const preferred = useMemo(() => run?.ai_selection.top_three.find((item) => item.code === run.ai_selection.preferred_code) ?? run?.ai_selection.top_three[0], [run])
  const selectedStrategy = strategies.data?.find((item) => item.id === strategy)
  const progress = runStatus === 'complete'
    ? { value: 100, label: '研究完成', count: '4 / 4' }
    : runStatus === 'failed'
      ? { ...stage, label: '研究未完成' }
      : stage
  const isRunning = createRun.isPending || runStatus === 'pending' || runStatus === 'running'
  useEffect(() => {
    onRunningChange?.(isRunning)
  }, [isRunning, onRunningChange])
  useEffect(() => () => onRunningChange?.(false), [onRunningChange])

  const readonly = Boolean(run || historicalRunId)

  return <motion.div layout={!reduceMotion} transition={spatialSpring} className={cn('selection-layout', readonly && 'selection-layout-readonly')}>
    <motion.div layout={!reduceMotion} transition={spatialSpring} className="selection-controls-stage">
      <AnimatePresence initial={false} mode="popLayout">
        {run ? <motion.div key="historical-conditions" initial={{ opacity: 0, y: reduceMotion ? 0 : -contentOffset }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={reduceMotion ? reducedFadeTransition : { y: spatialSpring, opacity: reducedFadeTransition }}><HistoricalConditions run={run} /></motion.div> : historicalRunId
          ? <motion.div key="historical-loading" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={reducedFadeTransition}><Card className="selection-controls"><CardContent className="grid h-full place-items-center">{runQuery.isError ? <EmptyState title="无法打开历史报告" description={runQuery.error.message} /> : <Spinner />}</CardContent></Card></motion.div>
          : <motion.div key="selection-form" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={reducedFadeTransition}><Card className="selection-controls">
      <CardHeader><CardTitle className="flex items-center gap-2"><ShieldCheck />研究条件</CardTitle><CardDescription>选择风险承受能力、投资周期和关注方向。</CardDescription></CardHeader>
      <CardContent className="min-h-0 flex-1 overflow-hidden"><ScrollArea className="h-full pr-3"><FieldGroup>
        <FieldSet><FieldLegend variant="label">风险承受</FieldLegend><ToggleGroup value={[risk]} onValueChange={(values) => values[0] && setRisk(values[0] as typeof risk)} className="w-full"><ToggleGroupItem value="conservative" className="flex-1">稳健</ToggleGroupItem><ToggleGroupItem value="balanced" className="flex-1">平衡</ToggleGroupItem><ToggleGroupItem value="active" className="flex-1">积极</ToggleGroupItem></ToggleGroup></FieldSet>
        <Field><FieldLabel>投资周期</FieldLabel><Select items={horizonOptions} value={horizon} onValueChange={(value) => value && setHorizon(value as typeof horizon)}><SelectTrigger className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectGroup>{horizonOptions.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}</SelectGroup></SelectContent></Select></Field>
        <FieldSeparator />
        <FieldSet><FieldLegend variant="label">研究视角</FieldLegend><ToggleGroup value={[strategy]} onValueChange={(values) => values[0] && setStrategy(values[0] as StrategyId)} className="w-full"><ToggleGroupItem value="trend" className="flex-1">趋势</ToggleGroupItem><ToggleGroupItem value="quality" className="flex-1">质量</ToggleGroupItem><ToggleGroupItem value="stability" className="flex-1">平稳</ToggleGroupItem></ToggleGroup><FieldDescription>{selectedStrategy?.summary}</FieldDescription></FieldSet>
        <FieldSeparator />
        <Field><FieldLabel>数据模式</FieldLabel><Select items={dataModeOptions} value={dataMode} onValueChange={(value) => value && setDataMode(value as 'latest' | 'historical')}><SelectTrigger className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectGroup>{dataModeOptions.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}</SelectGroup></SelectContent></Select><FieldDescription>{dataMode === 'latest' ? '使用最新可核验的市场与财务数据，不保证盘中实时。' : '所有行情和已发布财报都会截断到所选研究日期。'}</FieldDescription></Field>
        <AnimatePresence initial={false} mode="popLayout">
          {dataMode === 'historical'
            ? <motion.div key="historical-date" layout={!reduceMotion} initial={{ opacity: 0, y: reduceMotion ? 0 : contentOffset }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: reduceMotion ? 0 : -contentOffset }} transition={reduceMotion ? reducedFadeTransition : { y: spatialSpring, opacity: reducedFadeTransition }}><Field><FieldLabel htmlFor="research-date">研究日期</FieldLabel><Input id="research-date" type="date" value={asOf} max={new Date(Date.now() - 86_400_000).toISOString().slice(0, 10)} onChange={(event) => setAsOf(event.currentTarget.value)} /></Field></motion.div>
            : <motion.div key="latest-date" layout={!reduceMotion} initial={{ opacity: 0, y: reduceMotion ? 0 : -contentOffset }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: reduceMotion ? 0 : contentOffset }} transition={reduceMotion ? reducedFadeTransition : { y: spatialSpring, opacity: reducedFadeTransition }}><Field><FieldLabel htmlFor="latest-research-date">研究日期</FieldLabel><Input id="latest-research-date" type="date" value={new Date().toISOString().slice(0, 10)} disabled readOnly /><FieldDescription>日期由数据源确认，研究完成后显示实际有效交易日。</FieldDescription></Field></motion.div>}
        </AnimatePresence>
      </FieldGroup></ScrollArea></CardContent>
      <CardFooter><Button className="w-full" disabled={isRunning} onClick={() => createRun.mutate()}>{isRunning ? <Spinner data-icon="inline-start" /> : <Play data-icon="inline-start" />}开始研究</Button></CardFooter>
          </Card></motion.div>}
      </AnimatePresence>
    </motion.div>

    <motion.div layout={!reduceMotion} transition={spatialSpring} className="selection-results-stage">
    <ScrollArea className="selection-results h-full">
      <div className="selection-results-content">
      <Card>
        <CardContent className="flex flex-col gap-3">
          <Progress value={progress.value} getAriaValueText={() => progress.count}>
            <ProgressLabel className="flex items-center gap-2">{isRunning ? <Spinner aria-label="研究进行中" /> : null}<AnimatePresence initial={false} mode="popLayout"><motion.span key={progress.label} initial={{ opacity: 0, y: reduceMotion ? 0 : 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={reducedFadeTransition}>{progress.label}</motion.span></AnimatePresence></ProgressLabel>
            <ProgressValue>{() => <AnimatePresence initial={false} mode="popLayout"><motion.span key={progress.count} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={reducedFadeTransition}>{progress.count}</motion.span></AnimatePresence>}</ProgressValue>
          </Progress>
          <AnimatePresence initial={false} mode="popLayout">
            {createRun.isPending ? <motion.div key="creating" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={reducedFadeTransition} className="flex min-w-0 flex-wrap items-center gap-2"><SourceStatus status="pending" /><span className="text-sm text-muted-foreground">正在建立新的研究任务</span></motion.div> : run ? <motion.div key={`${run.id}-${run.provider.status}`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={reducedFadeTransition} className="flex min-w-0 flex-wrap items-center gap-2"><SourceStatus status={run.provider.status} />{run.provider.status === 'pending' ? <span className="text-sm text-muted-foreground">正在获取研究数据</span> : <>{sourceDisplayNames(run.provider.source).map((source) => <Badge variant="outline" key={source}>{source}</Badge>)}<span className="text-sm text-muted-foreground">{run.provider.status === 'historical' ? `行情日期 ${formatDataDate(run.provider.as_of)}` : `价格获取于 ${formatEvidenceTime(run.provider.as_of, run.provider.fetched_at)}`}</span></>}</motion.div> : null}
          </AnimatePresence>
        </CardContent>
      </Card>

      <AnimatePresence initial={false} mode="popLayout">
        {createRun.error ? <motion.div key="create-error" initial={{ opacity: 0, y: reduceMotion ? 0 : contentOffset }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={reduceMotion ? reducedFadeTransition : { y: spatialSpring, opacity: reducedFadeTransition }}><Alert variant="destructive"><AlertTriangle /><AlertTitle>研究未完成</AlertTitle><AlertDescription>{createRun.error.message}</AlertDescription></Alert></motion.div> : null}
      </AnimatePresence>
      <AnimatePresence initial={false} mode="popLayout">
        {!run ? <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={reducedFadeTransition}><Card className="selection-empty"><CardContent><Empty><EmptyHeader><EmptyMedia variant="icon"><Sparkles /></EmptyMedia><EmptyTitle>还没有研究结果</EmptyTitle><EmptyDescription>完成左侧设置并开始研究后，候选股票和入选理由会显示在这里。</EmptyDescription></EmptyHeader></Empty></CardContent></Card></motion.div> : run.status === 'failed' ? <motion.div key="failed" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={reducedFadeTransition}><Card><CardContent><EmptyState title="本次研究未能完成" description={run.error ?? '请检查数据源状态后重试。'} /></CardContent></Card></motion.div> : null}
      </AnimatePresence>

      {run?.status === 'complete' ? <>
        <motion.div initial={{ opacity: 0, y: reduceMotion ? 0 : contentOffset }} animate={{ opacity: 1, y: 0 }} transition={reduceMotion ? reducedFadeTransition : { ...spatialSpring, delay: 0 }} className="summary-grid">
          <Card><CardHeader><CardDescription>候选股票</CardDescription><CardTitle>{run.candidate_count}</CardTitle></CardHeader><CardContent className="text-sm text-muted-foreground">符合基础条件</CardContent></Card>
          <Card><CardHeader><CardDescription>已排除</CardDescription><CardTitle>{run.excluded_count}</CardTitle></CardHeader><CardContent className="text-sm text-muted-foreground">不符合基础条件</CardContent></Card>
          <Card><CardHeader><CardDescription>AI 状态</CardDescription><CardTitle>{run.ai_selection.status === 'complete' ? '已完成' : '未完成'}</CardTitle></CardHeader><CardContent className="text-sm text-muted-foreground">参考程度：{run.ai_selection.confidence === 'high' ? '高' : run.ai_selection.confidence === 'medium' ? '中' : '低'}</CardContent></Card>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: reduceMotion ? 0 : contentOffset }} animate={{ opacity: 1, y: 0 }} transition={reduceMotion ? reducedFadeTransition : { ...spatialSpring, delay: resultStagger }}><Card><CardHeader><CardTitle>候选股票</CardTitle><CardDescription>选择一行查看入选理由和风险；展开后可查看每项检查结果。</CardDescription><CardAction><span className="whitespace-nowrap text-sm text-muted-foreground">{run.request.strategy === 'trend' ? '趋势' : run.request.strategy === 'quality' ? '质量' : '平稳'}</span></CardAction></CardHeader><CardContent><CandidateTable candidates={run.candidates} selectedCode={selected?.code} onSelect={setSelected} onResearch={onOpenResearch} /></CardContent></Card></motion.div>

        <motion.div initial={{ opacity: 0, y: reduceMotion ? 0 : contentOffset }} animate={{ opacity: 1, y: 0 }} transition={reduceMotion ? reducedFadeTransition : { ...spatialSpring, delay: resultStagger * 2 }}><Tabs defaultValue="decision">
          <TabsList><TabsTrigger value="decision">AI 结果</TabsTrigger><TabsTrigger value="evidence">数据来源</TabsTrigger><TabsTrigger value="risk">风险与缺失信息</TabsTrigger></TabsList>
          <TabsContent value="decision"><div className="decision-layout">
            <Card><CardHeader><CardDescription>{run.ai_selection.status === 'complete' ? 'AI 推荐' : '当前第一名'}</CardDescription><CardTitle>{preferred?.name ?? '暂无推荐'}</CardTitle><CardAction><Badge variant="outline" className={run.ai_selection.status === 'complete' ? semanticBadgeClassName.info : semanticBadgeClassName.muted}>{run.ai_selection.status === 'complete' ? 'AI 生成' : '仅规则'}</Badge></CardAction></CardHeader><CardContent className="flex flex-col gap-4">{preferred ? <><div className="flex min-w-0 items-center justify-between gap-3"><span className="font-mono text-sm text-muted-foreground">{preferred.code}</span><Badge variant={recommendationVariant[preferred.recommendation]} className={recommendationClassName[preferred.recommendation]}>{recommendationLabel[preferred.recommendation]}</Badge></div><p className="break-words text-sm text-muted-foreground">{preferred.reason}</p></> : <p className="break-words text-sm">{run.ai_selection.summary}</p>}<Table className="min-w-[640px]"><TableHeader><TableRow><TableHead className="w-16 text-center">排名</TableHead><TableHead>候选</TableHead><TableHead>建议</TableHead><TableHead>依据</TableHead></TableRow></TableHeader><TableBody>{run.ai_selection.top_three.map((item, index) => <TableRow key={item.code} onClick={() => setSelected(run.candidates.find((candidate) => candidate.code === item.code) ?? null)} className="cursor-pointer"><TableCell className="text-center tabular-nums">{index + 1}</TableCell><TableCell><div className="flex min-w-0 flex-col"><span className="font-medium">{item.name}</span><span className="font-mono text-xs text-muted-foreground">{item.code}</span></div></TableCell><TableCell><Badge variant={recommendationVariant[item.recommendation]} className={recommendationClassName[item.recommendation]}>{recommendationLabel[item.recommendation]}</Badge></TableCell><TableCell className="max-w-[28rem] whitespace-normal break-words text-muted-foreground">{item.reason}</TableCell></TableRow>)}</TableBody></Table></CardContent></Card>
            <ResearchChat runId={run.id} onOpenChats={onOpenChats} />
          </div></TabsContent>
          <TabsContent value="evidence">{selected ? <Card><CardContent><Table className="min-w-[760px]"><TableHeader><TableRow><TableHead>数据项目</TableHead><TableHead className="text-right">数值</TableHead><TableHead>来源</TableHead><TableHead>数据时间</TableHead></TableRow></TableHeader><TableBody>{selected.evidence.map((item) => <TableRow key={item.id}><TableCell className="font-medium">{item.title}</TableCell><TableCell className="whitespace-nowrap text-right font-mono font-medium tabular-nums">{item.value}</TableCell><TableCell><div className="flex flex-wrap gap-2"><Badge variant="outline">{evidenceSourceDisplayName(item.source)}</Badge><ResolutionStatus resolution={item.resolution} /><FreshnessStatus freshness={item.freshness} /></div></TableCell><TableCell className="whitespace-nowrap text-muted-foreground tabular-nums">{formatEvidenceTime(item.as_of, item.fetched_at)}</TableCell></TableRow>)}</TableBody></Table></CardContent></Card> : <Card><CardContent><EmptyState title="先选择一只股票" description="选择候选股票后，这里会显示数据来源和日期。" /></CardContent></Card>}</TabsContent>
          <TabsContent value="risk"><div className="risk-grid">{[
            { title: '关注项', items: run.ai_selection.watch_conditions, icon: Check },
            { title: '重判条件', items: run.ai_selection.invalidation_signals, icon: AlertTriangle },
            { title: '数据缺口', items: run.ai_selection.data_gaps, icon: Database },
          ].map(({ title, items, icon: Icon }) => <Alert key={title} className="content-start items-start"><Icon /><AlertTitle className="flex min-w-0 items-center gap-2 whitespace-nowrap">{title}<Badge variant="outline" className={cn('shrink-0', run.ai_selection.status === 'complete' && semanticBadgeClassName.info)}>{run.ai_selection.status === 'complete' ? 'AI 生成' : '规则生成'}</Badge></AlertTitle><AlertDescription><ul className="flex min-w-0 list-disc flex-col gap-2 pl-4">{items.map((item) => <li className="break-words" key={item}>{item}</li>)}</ul></AlertDescription></Alert>)}</div></TabsContent>
        </Tabs></motion.div>
      </> : null}
      </div>
    </ScrollArea>
    </motion.div>
  </motion.div>
}
