import { ReactNode } from 'react'

export function AppShell({ children }: { children: ReactNode }) {
  return <main className="h-screen overflow-hidden">{children}</main>
}
