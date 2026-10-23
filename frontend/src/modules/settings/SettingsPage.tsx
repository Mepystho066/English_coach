import { useState } from 'react'
import { Moon, Sun, Volume2, Globe, Accessibility } from 'lucide-react'
import { Button } from '@/shared/ui/button'
import { Separator } from '@/shared/ui/separator'
import { Switch } from '@/shared/ui/switch'
import { useTheme } from 'next-themes'

export function SettingsPage() {
  const { theme, setTheme } = useTheme()
  const [reduceMotion, setReduceMotion] = useState(false)

  return (
    <div className="max-w-4xl mx-auto p-4 md:p-6 space-y-6">
      <div>
        <h1 className="text-2xl md:text-3xl font-bold mb-2">Ajustes</h1>
        <p className="text-muted-foreground">Personaliza tu experiencia</p>
      </div>

      <div className="space-y-6">
        {/* Apariencia */}
        <section className="space-y-4">
          <div className="flex items-center gap-2">
            <Sun className="h-5 w-5" />
            <h2 className="text-lg font-semibold">Apariencia</h2>
          </div>
          <div className="space-y-3 p-4 rounded-2xl border bg-card">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">Tema</p>
                <p className="text-sm text-muted-foreground">Claro, oscuro o sistema</p>
              </div>
              <div className="flex gap-1 p-1 rounded-full bg-secondary">
                <Button
                  variant={theme === 'light' ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => setTheme('light')}
                  className="rounded-full"
                >
                  <Sun className="h-4 w-4 mr-1" />
                  Claro
                </Button>
                <Button
                  variant={theme === 'dark' ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => setTheme('dark')}
                  className="rounded-full"
                >
                  <Moon className="h-4 w-4 mr-1" />
                  Oscuro
                </Button>
                <Button
                  variant={theme === 'system' ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => setTheme('system')}
                  className="rounded-full"
                >
                  Sistema
                </Button>
              </div>
            </div>
          </div>
        </section>

        <Separator />

        {/* Voz */}
        <section className="space-y-4">
          <div className="flex items-center gap-2">
            <Volume2 className="h-5 w-5" />
            <h2 className="text-lg font-semibold">Voz</h2>
          </div>
          <div className="space-y-3 p-4 rounded-2xl border bg-card">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">Voz del asistente</p>
                <p className="text-sm text-muted-foreground">Selecciona la voz</p>
              </div>
              <Button variant="outline" size="sm" className="rounded-full">
                Predeterminada
              </Button>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">Velocidad</p>
                <p className="text-sm text-muted-foreground">Velocidad de habla</p>
              </div>
              <Button variant="outline" size="sm" className="rounded-full">
                Normal
              </Button>
            </div>
          </div>
        </section>

        <Separator />

        {/* Idioma */}
        <section className="space-y-4">
          <div className="flex items-center gap-2">
            <Globe className="h-5 w-5" />
            <h2 className="text-lg font-semibold">Idioma</h2>
          </div>
          <div className="space-y-3 p-4 rounded-2xl border bg-card">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">Idioma de la interfaz</p>
                <p className="text-sm text-muted-foreground">Idioma de menús y textos</p>
              </div>
              <Button variant="outline" size="sm" className="rounded-full">
                Español
              </Button>
            </div>
          </div>
        </section>

        <Separator />

        {/* Accesibilidad */}
        <section className="space-y-4">
          <div className="flex items-center gap-2">
            <Accessibility className="h-5 w-5" />
            <h2 className="text-lg font-semibold">Accesibilidad</h2>
          </div>
          <div className="space-y-3 p-4 rounded-2xl border bg-card">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">Reducir movimiento</p>
                <p className="text-sm text-muted-foreground">Minimiza animaciones</p>
              </div>
              <Switch checked={reduceMotion} onCheckedChange={setReduceMotion} />
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
