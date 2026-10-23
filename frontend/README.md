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
