import React, { createContext, useContext } from 'react'
import { useChat, type UseChatReturn } from '../hooks/useChat'
import { useVoice, type UseVoiceReturn } from '../hooks/useVoice'
import { useCoaching, type UseCoachingReturn } from '../hooks/useCoaching'
import { useAnalysis, type UseAnalysisReturn } from '../hooks/useAnalysis'

export interface ChatContextType {
  chat: UseChatReturn
  voice: UseVoiceReturn
  coaching: UseCoachingReturn
  analysis: UseAnalysisReturn
}

const ChatContext = createContext<ChatContextType | null>(null)

export function ChatProvider({
  roomId,
  trainingSessionId,
  children,
}: {
  roomId: number | null
  trainingSessionId?: string | null
  children: React.ReactNode
}) {
  const voice = useVoice()

  const chat = useChat(roomId, {
    trainingSessionId,
    audioPlayerRef: voice.audioPlayerRef,
    onAudioOutputReceived: voice.markAudioOutputReceived,
    onAudioOutputMissing: voice.markAudioOutputMissing,
  })

  const coaching = useCoaching(roomId)
  const analysis = useAnalysis(roomId)

  return (
    <ChatContext.Provider value={{ chat, voice, coaching, analysis }}>
      {children}
    </ChatContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useChatContext(): ChatContextType {
  const ctx = useContext(ChatContext)
  if (!ctx) {
    throw new Error('useChatContext must be used inside a ChatProvider')
  }
  return ctx
}

export default ChatContext
