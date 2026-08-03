import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Database, RefreshCw } from 'lucide-react'
import { api } from '../api'
import { ProviderStatus } from '../components/Status'
import { formatDataTime } from '@/lib/date'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Spinner } from '@/components/ui/spinner'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

export function ProvidersPage() {
  const queryClient = useQueryClient()
  const providers = useQuery({
    queryKey: ['providers'],
    queryFn: api.providers,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  })
  const check = useMutation({
    mutationFn: api.checkProviders,
    onSuccess: (data) => queryClient.setQueryData(['providers'], data),
  })
  const error = providers.error ?? check.error

  return <div className="flex flex-col gap-4">
    <Card>
      <CardHeader><CardTitle>数据源状态</CardTitle><CardDescription>显示本机保存的上次检查结果；只有手动检查才会连接外部数据源。</CardDescription><CardAction><Button variant="outline" disabled={check.isPending} onClick={() => check.mutate()}>{check.isPending ? <Spinner data-icon="inline-start" /> : <RefreshCw data-icon="inline-start" />}重新检查</Button></CardAction></CardHeader>
      <CardContent>
        {error ? <Alert variant="destructive"><AlertTitle>数据源状态暂时无法更新</AlertTitle><AlertDescription>{error.message}</AlertDescription></Alert> : null}
        {providers.isPending ? <div className="grid min-h-40 place-items-center"><Spinner /></div> : null}
        {providers.isSuccess && providers.data.length === 0 ? <Empty><EmptyHeader><EmptyMedia variant="icon"><Database /></EmptyMedia><EmptyTitle>尚未检查数据源</EmptyTitle><EmptyDescription>点击“重新检查”后，程序才会连接 AkShare 和 BaoStock。</EmptyDescription></EmptyHeader></Empty> : null}
        {providers.data?.length ? <Table className="min-w-[920px]">
          <TableHeader><TableRow><TableHead>提供方</TableHead><TableHead>数据项目</TableHead><TableHead>状态</TableHead><TableHead>测试结果</TableHead><TableHead>上次检查</TableHead></TableRow></TableHeader>
          <TableBody>{providers.data.map((item) => <TableRow key={item.id}>
            <TableCell><Badge variant="outline">{item.provider}</Badge></TableCell>
            <TableCell><div className="flex min-w-0 flex-col"><span className="font-medium">{item.name}</span><span className="text-xs text-muted-foreground">{item.description}</span></div></TableCell>
            <TableCell><ProviderStatus status={item.status} /></TableCell>
            <TableCell className="max-w-[28rem] whitespace-normal break-words text-sm text-muted-foreground">{item.message}</TableCell>
            <TableCell className="whitespace-nowrap text-sm text-muted-foreground tabular-nums">{formatDataTime(item.checked_at, '尚未记录')}</TableCell>
          </TableRow>)}</TableBody>
        </Table> : null}
      </CardContent>
    </Card>
    <Alert><Database /><AlertTitle>数据不完整时会停止研究</AlertTitle><AlertDescription>如果市场或财务数据缺失、接口不可用，程序会说明具体来源和原因，不会自动改用来源不明的数据。</AlertDescription></Alert>
  </div>
}
