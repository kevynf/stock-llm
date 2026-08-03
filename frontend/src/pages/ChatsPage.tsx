import { useState } from 'react'
import { MessagesSquare } from 'lucide-react'
import { ChatHistoryList } from '../components/ChatHistoryList'
import { ResearchChat } from '../components/ResearchChat'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

export function ChatsPage() {
  const [selectedChatId, setSelectedChatId] = useState<string | null>(null)

  if (selectedChatId) {
    return <ResearchChat
      key={selectedChatId}
      initialChatId={selectedChatId}
      onBack={() => setSelectedChatId(null)}
      className="h-full!"
    />
  }

  return <Card>
    <CardHeader>
      <CardTitle className="flex items-center gap-2"><MessagesSquare />对话记录</CardTitle>
      <CardDescription>统一管理研究对话，打开后可以继续提问。</CardDescription>
    </CardHeader>
    <CardContent>
      <ChatHistoryList onOpenChat={setSelectedChatId} />
    </CardContent>
  </Card>
}
