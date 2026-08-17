// core/ui/canvas/src/app/ext/defaults/KernelNav.tsx
//
// Kernel-default sidebar navigation — rendered when no extension fills
// the `nav` slot. Covers the kernel's own surfaces only; an extension
// nav (registered through the ext seam) replaces this wholesale and is
// expected to link back to the room.
import { Link, useLocation } from 'react-router-dom'
import { type LucideIcon } from 'lucide-react'

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

import { ACEMark } from '../../journey/ACEMark'
import { canvasNavItems } from '../registry'
import { ATRIUM_DOWNSTREAM_ICONS, ATRIUM_SURFACE_ICONS } from '../../atrium/atriumIcons'

interface NavItem {
  href: string
  icon: LucideIcon
  label: string
}

const NAV: NavItem[] = [
  { href: '/atrium', icon: ATRIUM_SURFACE_ICONS.overview, label: 'Overview' },
  { href: '/atrium/explore', icon: ATRIUM_SURFACE_ICONS.explore, label: 'Explore' },
  { href: '/atrium/build', icon: ATRIUM_SURFACE_ICONS.build, label: 'Build' },
  { href: '/atrium/operate', icon: ATRIUM_SURFACE_ICONS.operate, label: 'Operate' },
  { href: '/atrium/consumers', icon: ATRIUM_SURFACE_ICONS.consumers, label: 'Consumers' },
]

const DOWNSTREAM_NAV: NavItem[] = [
  { href: '/board', icon: ATRIUM_DOWNSTREAM_ICONS.investigationBoard, label: 'Investigation board' },
]

/** A nav entry is active on its exact href, or on any path nested under it
 *  (`href` followed by `/`) — never on an unrelated path that merely shares
 *  the same string prefix (e.g. a hypothetical `/atrium/foo` must not read
 *  as active for an unrelated `/atrium/foobar` route). */
export function isNavItemActive(pathname: string, href: string): boolean {
  if (href === '/atrium') return pathname === '/atrium'
  return pathname === href || pathname.startsWith(`${href}/`)
}

export function KernelNav({ productName = 'Your Intelligence' }: { readonly productName?: string }) {
  const { pathname } = useLocation()
  const reservedNavHrefs = [...NAV, ...DOWNSTREAM_NAV].map(({ href }) => href)
  const surfaceNav = [
    ...NAV,
    ...canvasNavItems(reservedNavHrefs),
  ]

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <Link
          to="/atrium"
          aria-label="ACE Intelligence OS overview"
          className="flex items-center gap-2.5 pl-2.5 pr-2 py-1.5 overflow-hidden"
        >
          <span aria-hidden="true"><ACEMark size={22} variant="iris" /></span>
            <span className="flex flex-col leading-tight group-data-[collapsible=icon]:hidden">
              <span className="text-base font-semibold tracking-tight">ACE</span>
              <span className="text-[10px] text-muted-foreground">
              Intelligence OS
              </span>
          </span>
        </Link>
      </SidebarHeader>

      <div className="mx-3 mb-2 border-y border-sidebar-border px-3 py-3 group-data-[collapsible=icon]:hidden">
        <div className="font-mono text-[8px] uppercase tracking-[0.16em] text-muted-foreground">Current domain</div>
        <p className="mt-1 truncate text-[11px] font-medium text-sidebar-foreground">{productName}</p>
        <p className="mt-1 text-[9px] leading-4 text-muted-foreground">One maintained intelligence picture.</p>
      </div>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Surfaces</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {surfaceNav.map((item) => {
                const isActive = isNavItemActive(pathname, item.href)
                return (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton
                      asChild
                      isActive={isActive}
                      tooltip={item.label}
                    >
                      <Link to={item.href} aria-current={isActive ? 'page' : undefined}>
                        <item.icon aria-hidden="true" />
                        <span>{item.label}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                )
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel>Interfaces out</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {DOWNSTREAM_NAV.map((item) => {
                const isActive = isNavItemActive(pathname, item.href)
                return (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton
                      asChild
                      isActive={isActive}
                      tooltip={item.label}
                    >
                      <Link to={item.href} aria-current={isActive ? 'page' : undefined}>
                        <item.icon aria-hidden="true" />
                        <span>{item.label}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                )
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  )
}
