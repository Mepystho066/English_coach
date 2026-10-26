import {
  createRouter,
  createRoute,
  createRootRoute,
  Navigate,
  Outlet,
} from '@tanstack/react-router'
import { AppShell } from '../shell/AppShell'
import { modules } from '@/core/modules/registry'

const rootRoute = createRootRoute({
  component: () => (
    <AppShell>
      <Outlet />
    </AppShell>
  ),
})

const routeTree = rootRoute.addChildren(
  modules.map((module) =>
    createRoute({
      getParentRoute: () => rootRoute,
      path: module.path,
      component: module.component as any,
    })
  )
)

export const router = createRouter({
  routeTree,
  // Old links such as /chat or /history land on the voice screen.
  defaultNotFoundComponent: () => <Navigate to="/" />,
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
