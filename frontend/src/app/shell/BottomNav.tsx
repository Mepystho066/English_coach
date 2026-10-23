import { Link, useLocation } from '@tanstack/react-router'
import { modules } from '@/core/modules/registry'
import { cn } from '@/shared/lib/utils'

export function BottomNav() {
  const location = useLocation()

  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 border-t bg-card/80 backdrop-blur-lg z-50">
      <div className="flex items-center justify-around px-2 py-1">
        {modules.map((module) => {
          const Icon = module.icon
          const isActive = location.pathname === module.path
          return (
            <Link
              key={module.id}
              to={module.path}
              className={cn(
                'flex flex-col items-center gap-1 px-3 py-2 rounded-2xl transition-colors min-w-[64px]',
                'hover:bg-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-primary',
                isActive && 'text-primary'
              )}
              aria-label={module.title}
            >
              <Icon className="h-5 w-5" />
              <span className="text-xs">{module.title}</span>
            </Link>
          )
        })}
      </div>
    </nav>
  )
}
