import { lazy, Suspense, useCallback, useState } from 'react'
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

const pageContentClass = 'page-content h-full w-full overflow-auto px-4 pb-4'

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
  const [view, setView] = useState<ViewId>('selection')
  const [openViews, setOpenViews] = useState<Set<ViewId>>(() => new Set(['selection']))
  const [selectionKey, setSelectionKey] = useState(0)
  const [selectionRunning, setSelectionRunning] = useState(false)
  const [researchCode, setResearchCode] = useState('600519')
  const [historyRunId, setHistoryRunId] = useState<string | null>(null)
  const currentView = view === 'history-report'
    ? { label: '历史报告', subtitle: '查看当次保存的条件、候选、证据和结论。' }
    : navigation.find((item) => item.id === view) ?? navigation[0]

  const navigate = useCallback((nextView: ViewId) => {
    setOpenViews((current) => current.has(nextView) ? current : new Set(current).add(nextView))
    setView(nextView)
  }, [])

  const openResearch = useCallback((code: string) => {
    setResearchCode(code)
    navigate('research')
  }, [navigate])

  const openHistoryRun = useCallback((runId: string) => {
    setHistoryRunId(runId)
    navigate('history-report')
  }, [navigate])

  const openChats = useCallback(() => navigate('chats'), [navigate])

  const closeCurrentView = useCallback(() => {
    if (view === 'selection' && selectionRunning) return
    if (view === 'selection') {
      setSelectionKey((current) => current + 1)
      return
    }
    setOpenViews((current) => {
      const next = new Set(current)
      next.delete(view)
      if (view === 'history-report') next.add('history')
      return next
    })
    if (view === 'research') setResearchCode('600519')
    if (view === 'history-report') {
      setHistoryRunId(null)
      setView('history')
      return
    }
    setView('selection')
  }, [selectionRunning, view])

  const closeBlocked = view === 'selection' && selectionRunning

  return (
    <SidebarProvider className="h-svh min-h-0 overflow-hidden">
      <Sidebar collapsible="icon">
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
                <span>结论需结合来源与个人判断</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarFooter>
      </Sidebar>

      <SidebarInset className="h-full min-h-0 min-w-0 overflow-hidden">
        <header className="flex h-16 shrink-0 items-center gap-2 px-4">
          <SidebarTrigger className="md:hidden" aria-label="打开侧栏" title="打开侧栏" />
          {view === 'history-report' ? <Button variant="ghost" size="icon" onClick={() => navigate('history')} aria-label="返回历史研究"><ArrowLeft /></Button> : null}
          <div className="flex min-w-0 items-baseline gap-3">
            <h1 className="shrink-0 text-base font-medium">{currentView.label}</h1>
            <p className="truncate text-sm text-muted-foreground">{currentView.subtitle}</p>
          </div>
          <Button className="ml-auto" variant="ghost" size="icon" onClick={closeCurrentView} disabled={closeBlocked} aria-label={closeBlocked ? '研究进行中，无法关闭' : '关闭当前页面'} title={closeBlocked ? '研究完成后才能关闭' : '关闭当前页面'}><X /></Button>
        </header>
        <main className="min-h-0 flex-1 overflow-hidden">
          <Suspense fallback={<div className="grid h-full place-items-center"><Spinner /></div>}>
            {openViews.has('selection') ? <div className={view === 'selection' ? pageContentClass : 'hidden'}><SelectionWorkspace key={selectionKey} onOpenResearch={openResearch} onOpenChats={openChats} onRunningChange={setSelectionRunning} /></div> : null}
            {openViews.has('history') ? <div className={view === 'history' ? pageContentClass : 'hidden'}><HistoryPage onOpenRun={openHistoryRun} /></div> : null}
            {openViews.has('history-report') && historyRunId ? <div className={view === 'history-report' ? pageContentClass : 'hidden'}><SelectionWorkspace key={historyRunId} onOpenResearch={openResearch} onOpenChats={openChats} historicalRunId={historyRunId} /></div> : null}
            {openViews.has('research') ? <div className={view === 'research' ? pageContentClass : 'hidden'}><StockResearchPage initialCode={researchCode} onOpenChats={openChats} /></div> : null}
            {openViews.has('chats') ? <div className={view === 'chats' ? pageContentClass : 'hidden'}><ChatsPage /></div> : null}
            {openViews.has('watchlist') ? <div className={view === 'watchlist' ? pageContentClass : 'hidden'}><WatchlistPage onOpenResearch={openResearch} /></div> : null}
            {openViews.has('providers') ? <div className={view === 'providers' ? pageContentClass : 'hidden'}><ProvidersPage /></div> : null}
            {openViews.has('settings') ? <div className={view === 'settings' ? pageContentClass : 'hidden'}><SettingsPage /></div> : null}
          </Suspense>
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}
