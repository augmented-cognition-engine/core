// core/ui/canvas/src/app/ext/defaults/KernelNav.tsx
//
// Kernel-default sidebar navigation — rendered when no extension fills
// the `nav` slot. Covers the kernel's own surfaces only; an extension
// nav (registered through the ext seam) replaces this wholesale and is
// expected to link back to the room.
import { Link, useLocation } from 'react-router-dom'
import {
  Crosshair,
  FileSearch2,
  Orbit,
  Radar,
  Route,
  type LucideIcon,
  Waypoints,
} from 'lucide-react'

import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@/design/shadcn/ui/sidebar'

interface NavItem {
  href: string
  icon: LucideIcon
  label: string
}

const NAV: NavItem[] = [
  { href: '/atrium', icon: Radar, label: 'Intelligence' },
  { href: '/atrium/opportunities', icon: Crosshair, label: 'Opportunities' },
  { href: '/atrium/agents', icon: Orbit, label: 'Agents' },
  { href: '/atrium/connections', icon: Waypoints, label: 'Connections' },
  { href: '/atrium/strategy', icon: Route, label: 'Strategy' },
]

const DOWNSTREAM_NAV: NavItem[] = [
  { href: '/board', icon: FileSearch2, label: 'Investigation board' },
]

export function KernelNav() {
  const { pathname } = useLocation()

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="px-3 py-3">
        <Link
          to="/atrium"
          className="flex items-center gap-2.5 overflow-hidden px-1 py-1"
        >
          <span
            className="relative flex size-7 shrink-0 items-center justify-center overflow-hidden"
            aria-hidden="true"
          >
            <img
              src="/brand/ace_logo_fixed_128.png"
              alt=""
              className="size-14 max-w-none"
            />
          </span>
          <span className="flex flex-col leading-tight group-data-[collapsible=icon]:hidden">
            <span className="text-base font-semibold tracking-tight">ACE</span>
            <span className="text-[10px] text-muted-foreground">
              Intelligence OS
            </span>
          </span>
        </Link>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel className="font-mono text-[8px] uppercase tracking-[0.14em] text-sidebar-foreground/45">Surfaces</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {NAV.map((item) => (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton
                    asChild
                    className="rounded-md px-2.5 focus-visible:ring-2 [&_svg]:size-3.5"
                    isActive={
                      item.href === '/atrium'
                        ? pathname === '/atrium'
                        : pathname.startsWith(item.href)
                    }
                    tooltip={item.label}
                  >
                    <Link to={item.href}>
                      <item.icon strokeWidth={1.65} />
                      <span>{item.label}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel className="font-mono text-[8px] uppercase tracking-[0.14em] text-sidebar-foreground/45">Downstream work</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {DOWNSTREAM_NAV.map((item) => (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton
                    asChild
                    className="rounded-md px-2.5 focus-visible:ring-2 [&_svg]:size-3.5"
                    isActive={pathname === item.href}
                    tooltip={item.label}
                  >
                    <Link to={item.href}>
                      <item.icon strokeWidth={1.65} />
                      <span>{item.label}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  )
}
