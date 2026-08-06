import ReactMarkdown, { type Components } from 'react-markdown'
import remarkBreaks from 'remark-breaks'
import remarkGfm from 'remark-gfm'

import { Separator } from '@/components/ui/separator'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'

const markdownComponents: Components = {
  h1: ({ children }) => <h1 className="break-words text-base font-semibold">{children}</h1>,
  h2: ({ children }) => <h2 className="break-words text-sm font-semibold">{children}</h2>,
  h3: ({ children }) => <h3 className="break-words text-sm font-medium">{children}</h3>,
  p: ({ children }) => <p className="break-words">{children}</p>,
  ul: ({ children }) => <ul className="list-disc pl-5 [&>li+li]:mt-1">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-5 [&>li+li]:mt-1">{children}</ol>,
  li: ({ children }) => <li className="break-words pl-1">{children}</li>,
  blockquote: ({ children }) => <blockquote className="border-l-2 border-border pl-3 text-muted-foreground">{children}</blockquote>,
  a: ({ children, href }) => <a className="break-all text-primary underline underline-offset-4" href={href} target="_blank" rel="noreferrer">{children}</a>,
  pre: ({ children }) => <ScrollArea scrollbars="horizontal" className="max-w-full rounded-md bg-muted pb-2.5"><pre className="w-max min-w-full p-3 font-mono text-xs leading-5">{children}</pre></ScrollArea>,
  code: ({ children, className }) => <code className={cn('rounded bg-muted px-1 py-0.5 font-mono text-xs', className)}>{children}</code>,
  table: ({ children }) => <Table className="min-w-[32rem]">{children}</Table>,
  thead: ({ children }) => <TableHeader className="bg-muted/50">{children}</TableHeader>,
  tbody: ({ children }) => <TableBody>{children}</TableBody>,
  tr: ({ children }) => <TableRow>{children}</TableRow>,
  th: ({ children }) => <TableHead className="px-3 py-2">{children}</TableHead>,
  td: ({ children }) => <TableCell className="px-3 py-2 align-top">{children}</TableCell>,
  img: ({ src, alt }) => <img className="h-auto max-w-full" src={src} alt={alt ?? ''} />,
  hr: () => <Separator />,
  input: ({ checked }) => <input className="mr-2 align-middle" type="checkbox" checked={checked} disabled readOnly />,
}

export function MarkdownMessage({ content }: { content: string }) {
  return <div className="flex min-w-0 max-w-full flex-col gap-3 overflow-hidden break-words text-sm leading-6">
    <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]} components={markdownComponents}>
      {content}
    </ReactMarkdown>
  </div>
}
