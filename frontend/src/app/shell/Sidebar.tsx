import { Link, useLocation } from '@tanstack/react-router'
import { modules } from '@/core/modules/registry'
import { cn } from '@/shared/lib/utils'
import { Button } from '@/shared/ui/button'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useState } from 'react'

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false)
  const location = useLocation()

  return (
    <aside
      className={cn(
        'hidden md:flex flex-col border-r bg-card/30 backdrop-blur-xl transition-all duration-300 shadow-sm',
        collapsed ? 'w-16' : 'w-72'
      )}
    >
      <div className="flex items-center justify-between p-6">
        {!collapsed && (
          <div>
            <h2 className="font-bold text-xl bg-gradient-to-r from-primary to-violet-500 bg-clip-text text-transparent">English Coach</h2>
            <p className="text-xs text-muted-foreground mt-1">AI Practice</p>
          </div>
        )}
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setCollapsed(!collapsed)}
          className="rounded-full hover:bg-accent/50"
          aria-label={collapsed ? 'Expandir barra lateral' : 'Colapsar barra lateral'}
        >
          {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </Button>
      </div>

      <nav className="flex-1 px-3 space-y-1">
        {modules.map((module) => {
          const Icon = module.icon
          const isActive = location.pathname === module.path
          return (
            <Link
              key={module.id}
              to={module.path}
              className={cn(
                'flex items-center gap-3 px-3 py-2.5 rounded-2xl transition-all duration-200',
                'hover:bg-accent/60 hover:scale-[1.02] focus:outline-none focus-visible:ring-2 focus-visible:ring-primary',
                isActive && 'bg-gradient-to-r from-primary/10 to-violet-500/10 text-primary font-semibold shadow-sm border border-primary/20',
                collapsed && 'justify-center px-2'
              )}
              aria-label={module.title}
            >
              <Icon className={cn('h-5 w-5 flex-shrink-0', isActive && 'text-primary')} />
              {!collapsed && <span>{module.title}</span>}
            </Link>
          )
        })}
      </nav>
      
      {!collapsed && (
        <div className="p-4 m-3 rounded-2xl bg-gradient-to-br from-primary/10 to-violet-500/10 border border-primary/20">
          <p className="text-xs text-muted-foreground">Práctica con IA</p>
          <p className="text-sm font-medium mt-1">Mejora tu inglés</p>
        </div>
      )}
    </aside>
  )
}
