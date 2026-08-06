import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import {
  ArrowLeft,
  Database,
  History,
  Info,
  MessagesSquare,
  PanelLeft,
  Search,
  Settings,
  Sparkles,
  Star,
  X,
} from 'lucide-react'
import { AnimatePresence, motion, useAnimationControls, useReducedMotion } from 'motion/react'
import { Button } from '@/components/ui/button'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
  useSidebar,
} from '@/components/ui/sidebar'
import { Spinner } from '@/components/ui/spinner'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  contentOffset,
  departingPageOffset,
  fadeInTransition,
  fadeOutTransition,
  pageOffset,
  reducedFadeTransition,
  spatialSpring,
  type NavigationIntent,
} from '@/lib/motion'
import type { ViewId } from './types'

const SelectionWorkspace = lazy(() => import('./pages/SelectionWorkspace').then((module) => ({ default: module.SelectionWorkspace })))
const HistoryPage = lazy(() => import('./pages/HistoryPage').then((module) => ({ default: module.HistoryPage })))
const StockResearchPage = lazy(() => import('./pages/StockResearchPage').then((module) => ({ default: module.StockResearchPage })))
const ChatsPage = lazy(() => import('./pages/ChatsPage').then((module) => ({ default: module.ChatsPage })))
const WatchlistPage = lazy(() => import('./pages/WatchlistPage').then((module) => ({ default: module.WatchlistPage })))
const ProvidersPage = lazy(() => import('./pages/ProvidersPage').then((module) => ({ default: module.ProvidersPage })))
const SettingsPage = lazy(() => import('./pages/SettingsPage').then((module) => ({ default: module.SettingsPage })))

const navigation = [
  { id: 'selection' as const, label: '开始选股', subtitle: '设置条件，查看候选股票和入选理由。', icon: Sparkles },
  { id: 'history' as const, label: '历史研究', subtitle: '查看以前保存的研究结果。', icon: History },
  { id: 'research' as const, label: '个股研究', subtitle: '一起查看股价、经营数据和相关新闻。', icon: Search },
  { id: 'chats' as const, label: '对话记录', subtitle: '统一管理并继续以前的研究对话。', icon: MessagesSquare },
  { id: 'watchlist' as const, label: '自选股', subtitle: '保存想继续关注的股票。', icon: Star },
  { id: 'providers' as const, label: '数据源', subtitle: '查看数据来自哪里，以及最后更新时间。', icon: Database },
  { id: 'settings' as const, label: '设置', subtitle: '设置 DeepSeek 模型和 API 密钥。', icon: Settings },
]

function PageView({ active, departing, intent, revision, children }: {
  active: boolean
  departing: boolean
  intent: NavigationIntent
  revision: number
  children: React.ReactNode
}) {
  const controls = useAnimationControls()
  const reduceMotion = useReducedMotion()
  const activeRef = useRef(active)
  const hiddenRef = useRef(!active)

  useEffect(() => {
    activeRef.current = active
  }, [active])

  useEffect(() => {
    const entryX = reduceMotion || intent === 'replace' ? 0 : intent === 'push' ? pageOffset : -pageOffset
    const entryY = reduceMotion || intent !== 'replace' ? 0 : contentOffset
    const exitX = reduceMotion || intent === 'replace' ? 0 : intent === 'push' ? -departingPageOffset : departingPageOffset
    const exitScale = reduceMotion || intent === 'replace' ? 1 : 0.985
    const visibleTransition = reduceMotion
      ? reducedFadeTransition
      : { x: spatialSpring, y: spatialSpring, scale: spatialSpring, opacity: fadeInTransition }

    if (active) {
      if (hiddenRef.current) {
        controls.set({ opacity: 0, x: entryX, y: entryY, scale: 1, visibility: 'visible' })
      }
      hiddenRef.current = false
      void controls.start({ opacity: 1, x: 0, y: 0, scale: 1, visibility: 'visible', transition: visibleTransition })
      return
    }

    if (departing) {
      void controls.start({
        opacity: 0,
        x: exitX,
        scale: exitScale,
        transition: reduceMotion ? reducedFadeTransition : { x: spatialSpring, scale: spatialSpring, opacity: fadeOutTransition },
      }).then(() => {
        if (!activeRef.current) {
          hiddenRef.current = true
          controls.set({ visibility: 'hidden' })
        }
      })
      return
    }

    if (hiddenRef.current) controls.set({ opacity: 0, x: 0, y: 0, scale: 1, visibility: 'hidden' })
  }, [active, controls, departing, intent, reduceMotion, revision])

  return (
    <motion.div
      animate={controls}
      initial={{
        opacity: 0,
        x: active && !reduceMotion && intent !== 'replace' ? intent === 'push' ? pageOffset : -pageOffset : 0,
        y: active && !reduceMotion && intent === 'replace' ? contentOffset : 0,
        scale: 1,
        visibility: active ? 'visible' : 'hidden',
      }}
      inert={!active}
      aria-hidden={!active}
      className="absolute inset-0 min-h-0 min-w-0 overflow-hidden"
      style={{ pointerEvents: active ? 'auto' : 'none' }}
    >
      <ScrollArea className="h-full w-full">
        <div className="page-content min-h-full w-full px-4 pb-4">{children}</div>
      </ScrollArea>
    </motion.div>
  )
}

function SidebarToggleButton() {
  const { state, toggleSidebar } = useSidebar()
  const tooltip = state === 'expanded' ? '收起侧栏' : '展开侧栏'

  return (
    <SidebarMenuButton
      tooltip={{ children: tooltip, className: 'data-closed:hidden' }}
      aria-label={tooltip}
      onClick={toggleSidebar}
    >
      <PanelLeft />
      <span>收起侧栏</span>
    </SidebarMenuButton>
  )
}

export function App() {
  const [{ view, previousView, intent, revision }, setNavigation] = useState<{
    view: ViewId
    previousView: ViewId | null
    intent: NavigationIntent
    revision: number
  }>({ view: 'selection', previousView: null, intent: 'replace', revision: 0 })
  const [openViews, setOpenViews] = useState<Set<ViewId>>(() => new Set(['selection']))
  const [selectionKey, setSelectionKey] = useState(0)
  const [selectionRunning, setSelectionRunning] = useState(false)
  const [researchCode, setResearchCode] = useState('600519')
  const [historyRunId, setHistoryRunId] = useState<string | null>(null)
  const closeTimersRef = useRef(new Map<ViewId, number>())
  const reduceMotion = useReducedMotion()
  const currentView = view === 'history-report'
    ? { label: '历史报告', subtitle: '查看当次保存的条件、候选、证据和结论。' }
    : navigation.find((item) => item.id === view) ?? navigation[0]

  useEffect(() => () => {
    closeTimersRef.current.forEach((timer) => window.clearTimeout(timer))
  }, [])

  const navigate = useCallback((nextView: ViewId, nextIntent: NavigationIntent = 'replace') => {
    const pendingClose = closeTimersRef.current.get(nextView)
    if (pendingClose !== undefined) {
      window.clearTimeout(pendingClose)
      closeTimersRef.current.delete(nextView)
    }
    setOpenViews((current) => current.has(nextView) ? current : new Set(current).add(nextView))
    setNavigation((current) => current.view === nextView
      ? current
      : {
          view: nextView,
          previousView: current.view,
          intent: nextIntent,
          revision: current.revision + 1,
        })
  }, [])

  const openResearch = useCallback((code: string) => {
    setResearchCode(code)
    navigate('research', 'push')
  }, [navigate])

  const openHistoryRun = useCallback((runId: string) => {
    setHistoryRunId(runId)
    navigate('history-report', 'push')
  }, [navigate])

  const openChats = useCallback(() => navigate('chats'), [navigate])

  const closeCurrentView = useCallback(() => {
    if (view === 'selection' && selectionRunning) return
    if (view === 'selection') {
      setSelectionKey((current) => current + 1)
      return
    }
    const closingView = view
    const targetView: ViewId = view === 'history-report' ? 'history' : 'selection'
    navigate(targetView, view === 'history-report' ? 'pop' : 'replace')
    if (view === 'research') setResearchCode('600519')
    const timer = window.setTimeout(() => {
      setOpenViews((current) => {
        const next = new Set(current)
        next.delete(closingView)
        return next
      })
      if (closingView === 'history-report') setHistoryRunId(null)
      closeTimersRef.current.delete(closingView)
    }, reduceMotion ? 140 : 360)
    closeTimersRef.current.set(closingView, timer)
  }, [navigate, reduceMotion, selectionRunning, view])

  const closeBlocked = view === 'selection' && selectionRunning

  return (
    <SidebarProvider className="h-svh min-h-0 overflow-hidden">
      <Sidebar collapsible="icon" className="sidebar-motion">
        <SidebarHeader className="h-20 px-2 py-4">
          <SidebarMenu className="gap-2">
            <SidebarMenuItem>
              <SidebarMenuButton
                size="lg"
                tooltip="StockLLM"
                className="group-data-[collapsible=icon]:h-12! group-data-[collapsible=icon]:w-8! group-data-[collapsible=icon]:p-2!"
                onClick={() => navigate('selection')}
              >
                <img src="/brand-mark.svg" alt="" className="size-4 shrink-0" />
                <span className="flex min-w-0 flex-col group-data-[collapsible=icon]:hidden">
                  <span className="truncate font-medium">StockLLM</span>
                  <span className="truncate text-xs text-muted-foreground">个人投资研究助手</span>
                </span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarHeader>
        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupContent>
              <SidebarMenu className="gap-2">
                {navigation.map(({ id, label, icon: Icon }) => (
                  <SidebarMenuItem key={id}>
                    <SidebarMenuButton
                      isActive={view === id || (view === 'history-report' && id === 'history')}
                      tooltip={label}
                      onClick={() => navigate(id)}
                    >
                      <Icon />
                      <span>{label}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
        <SidebarFooter>
          <SidebarMenu className="gap-2">
            <SidebarMenuItem>
              <SidebarToggleButton />
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton tooltip="研究结论不构成投资建议">
                <Info />
                <span>时刻注意投资风险</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarFooter>
      </Sidebar>

      <SidebarInset className="h-full min-h-0 min-w-0 overflow-hidden">
        <header className="flex h-16 shrink-0 items-center gap-2 px-4">
          <SidebarTrigger className="md:hidden" aria-label="打开侧栏" title="打开侧栏" />
          <AnimatePresence initial={false}>
            {view === 'history-report' ? <motion.div key="history-back" initial={{ opacity: 0, x: reduceMotion ? 0 : 8 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: reduceMotion ? 0 : 8 }} transition={reduceMotion ? reducedFadeTransition : spatialSpring}><Button variant="ghost" size="icon" onClick={() => navigate('history', 'pop')} aria-label="返回历史研究"><ArrowLeft /></Button></motion.div> : null}
          </AnimatePresence>
          <div className="relative min-w-0 flex-1 overflow-hidden">
            <AnimatePresence initial={false} mode="popLayout">
              <motion.div
                key={view}
                initial={{ opacity: 0, x: reduceMotion || intent === 'replace' ? 0 : intent === 'push' ? 8 : -8 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0 }}
                transition={reduceMotion ? reducedFadeTransition : { x: spatialSpring, opacity: fadeInTransition }}
                className="flex min-w-0 items-baseline gap-3"
              >
                <h1 className="shrink-0 text-base font-medium">{currentView.label}</h1>
                <p className="truncate text-sm text-muted-foreground">{currentView.subtitle}</p>
              </motion.div>
            </AnimatePresence>
          </div>
          <Button className="ml-auto" variant="ghost" size="icon" onClick={closeCurrentView} disabled={closeBlocked} aria-label={closeBlocked ? '研究进行中，无法关闭' : '关闭当前页面'} title={closeBlocked ? '研究完成后才能关闭' : '关闭当前页面'}><X /></Button>
        </header>
        <main className="relative min-h-0 flex-1 overflow-hidden">
          <Suspense fallback={<div className="grid h-full place-items-center"><Spinner /></div>}>
            {openViews.has('selection') ? <PageView active={view === 'selection'} departing={previousView === 'selection'} intent={intent} revision={revision}><SelectionWorkspace key={selectionKey} onOpenResearch={openResearch} onOpenChats={openChats} onRunningChange={setSelectionRunning} /></PageView> : null}
            {openViews.has('history') ? <PageView active={view === 'history'} departing={previousView === 'history'} intent={intent} revision={revision}><HistoryPage onOpenRun={openHistoryRun} /></PageView> : null}
            {openViews.has('history-report') && historyRunId ? <PageView active={view === 'history-report'} departing={previousView === 'history-report'} intent={intent} revision={revision}><SelectionWorkspace key={historyRunId} onOpenResearch={openResearch} onOpenChats={openChats} historicalRunId={historyRunId} /></PageView> : null}
            {openViews.has('research') ? <PageView active={view === 'research'} departing={previousView === 'research'} intent={intent} revision={revision}><StockResearchPage initialCode={researchCode} onOpenChats={openChats} /></PageView> : null}
            {openViews.has('chats') ? <PageView active={view === 'chats'} departing={previousView === 'chats'} intent={intent} revision={revision}><ChatsPage /></PageView> : null}
            {openViews.has('watchlist') ? <PageView active={view === 'watchlist'} departing={previousView === 'watchlist'} intent={intent} revision={revision}><WatchlistPage onOpenResearch={openResearch} /></PageView> : null}
            {openViews.has('providers') ? <PageView active={view === 'providers'} departing={previousView === 'providers'} intent={intent} revision={revision}><ProvidersPage /></PageView> : null}
            {openViews.has('settings') ? <PageView active={view === 'settings'} departing={previousView === 'settings'} intent={intent} revision={revision}><SettingsPage /></PageView> : null}
          </Suspense>
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}
