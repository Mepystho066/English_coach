# English Coach - Frontend

Frontend construido con React + TypeScript + Vite para reemplazar los static del backend.

## Stack

- React + TypeScript + Vite
- Tailwind CSS + shadcn/ui (Radix UI)
- motion (framer-motion)
- XState
- Zustand
- TanStack Router + TanStack Query
- cmdk, sonner, vaul

## Desarrollo

```bash
npm install
npm run dev
```

## Build

El build genera los archivos directamente en `../backend/static/` para reemplazar los estáticos del backend.

```bash
npm run build
npm run preview
```

## Arquitectura

- `app/` - Shell, providers, router
- `core/` - Configuración, registro de módulos, tema
- `modules/` - Módulos funcionales (voice, chat, history, settings)
- `shared/` - Componentes UI, hooks, utils, tipos

Los módulos se registran en `core/modules/registry.ts`. Añadir un nuevo módulo no requiere modificar el shell.

## Pantalla de voz y panel

La pantalla principal es solo de voz: el orbe inicia la llamada y el botón de
chat abre un panel (derecha en escritorio, hoja inferior en móvil) con cuatro
pestañas:

- **Conversación** — historial compartido con la voz y envío de mensajes escritos.
- **Correcciones** — error, versión corregida y explicación en español.
- **Vocabulario** — palabra o expresión, significado y ejemplo.
- **Progreso** — turnos, correcciones y vocabulario por categoría.

El panel se actualiza con el evento `STATE_SNAPSHOT` del stream AG-UI y, en voz,
con el mensaje RTVI `learning-state`. Si el análisis tarda más que la respuesta,
`useChatRuntime` consulta `GET /api/v1/threads/{id}/state` hasta que llega.
