import { useState } from 'react'
import { MessagesSquare } from 'lucide-react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { ChatHistoryList } from '../components/ChatHistoryList'
import { ResearchChat } from '../components/ResearchChat'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { fadeInTransition, fadeOutTransition, pageOffset, reducedFadeTransition, spatialSpring } from '@/lib/motion'

export function ChatsPage() {
  const [selectedChatId, setSelectedChatId] = useState<string | null>(null)
  const reduceMotion = useReducedMotion()
  const direction = selectedChatId ? 1 : -1

  return <AnimatePresence initial={false} mode="wait" custom={direction}>
    {selectedChatId ? <motion.div
      key={`chat-${selectedChatId}`}
      custom={direction}
      initial={{ opacity: 0, x: reduceMotion ? 0 : pageOffset }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: reduceMotion ? 0 : pageOffset }}
      transition={reduceMotion ? reducedFadeTransition : { x: spatialSpring, opacity: fadeInTransition }}
      className="h-full"
    ><ResearchChat
      initialChatId={selectedChatId}
      onBack={() => setSelectedChatId(null)}
      className="h-full!"
    /></motion.div> : <motion.div
      key="chat-list"
      initial={{ opacity: 0, x: reduceMotion ? 0 : -pageOffset }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: reduceMotion ? 0 : -pageOffset }}
      transition={reduceMotion ? reducedFadeTransition : { x: spatialSpring, opacity: fadeOutTransition }}
    ><Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><MessagesSquare />对话记录</CardTitle>
        <CardDescription>统一管理研究对话，打开后可以继续提问。</CardDescription>
      </CardHeader>
      <CardContent>
        <ChatHistoryList onOpenChat={setSelectedChatId} />
      </CardContent>
    </Card></motion.div>}
  </AnimatePresence>
}
