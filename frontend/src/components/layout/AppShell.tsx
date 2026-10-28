import type { ReactNode } from 'react'
import { Sidebar } from './Sidebar'
import { Header } from './Header'
import { StatusBar } from './StatusBar'

interface AppShellProps {
  children: ReactNode
}

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="fixed inset-0 flex flex-col overflow-hidden bg-background">
      {/* 顶部：Header */}
      <Header />

      {/* 中部：Sidebar + Content */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-auto">
          <div className="mx-auto max-w-[1200px] p-6">
            {children}
          </div>
        </main>
      </div>

      {/* 底部：StatusBar */}
      <StatusBar />
    </div>
  )
}
