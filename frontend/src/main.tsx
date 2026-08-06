import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RotateCcwIcon, TriangleAlertIcon } from 'lucide-react'
import { MotionConfig } from 'motion/react'
import { App } from './App'
import { api, HealthContractError, initializeRuntime, restartBackend, validateHealth } from './api'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { TooltipProvider } from '@/components/ui/tooltip'
import './styles.css'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
})

document.documentElement.classList.add('dark')
const root = createRoot(document.getElementById('root')!)
let errorHandlersInstalled = false

function StartupLoading() {
  return (
    <main className="flex min-h-svh items-center justify-center p-6">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Spinner />
        正在连接本地服务…
      </div>
    </main>
  )
}

function StartupFailure({ message, onRetry }: { message: string; onRetry: () => Promise<void> }) {
  const [retrying, setRetrying] = useState(false)
  const retry = async () => {
    setRetrying(true)
    try {
      await onRetry()
    } finally {
      setRetrying(false)
    }
  }
  return (
    <main className="flex min-h-svh items-center justify-center p-6">
      <Alert variant="destructive" className="max-w-md">
        <TriangleAlertIcon />
        <AlertTitle>本地服务不可用</AlertTitle>
        <AlertDescription className="flex flex-col items-start gap-3">
          <p>{message}</p>
          <Button variant="outline" disabled={retrying} onClick={() => void retry()}>
            {retrying ? <Spinner data-icon="inline-start" /> : <RotateCcwIcon data-icon="inline-start" />}
            重新连接
          </Button>
        </AlertDescription>
      </Alert>
    </main>
  )
}

function renderApp() {
  if (!errorHandlersInstalled) {
    const report = (event: string, message: string) => {
      void api.reportClientLog({ level: 'error', event, message: message.slice(0, 1000), location: window.location.href })
    }
    window.addEventListener('error', (event) => report('window_error', event.message || '页面发生未知错误'))
    window.addEventListener('unhandledrejection', (event) => {
      const message = event.reason instanceof Error ? event.reason.message : '页面发生未处理的异步错误'
      report('unhandled_rejection', message)
    })
    errorHandlersInstalled = true
  }
  root.render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <MotionConfig reducedMotion="user">
          <TooltipProvider delay={0} closeDelay={0}>
            <App />
          </TooltipProvider>
        </MotionConfig>
      </QueryClientProvider>
    </StrictMode>,
  )
}

async function waitForBackend() {
  let lastError: unknown
  for (let attempt = 0; attempt < 12; attempt += 1) {
    try {
      validateHealth(await api.health(1_000))
      return
    } catch (error) {
      if (error instanceof HealthContractError) throw error
      lastError = error
      await new Promise((resolve) => window.setTimeout(resolve, 250))
    }
  }
  throw lastError instanceof Error ? lastError : new Error('无法连接到本地服务。')
}

async function start(restart = false) {
  root.render(<StartupLoading />)
  await initializeRuntime()
  if (restart) await restartBackend()
  await waitForBackend()
  renderApp()
}

function showStartupFailure(error: unknown) {
  const message = error instanceof Error ? error.message : '启动本地服务时发生未知错误。'
  root.render(<StartupFailure message={message} onRetry={() => start(true).catch(showStartupFailure)} />)
}

void start().catch(showStartupFailure)
