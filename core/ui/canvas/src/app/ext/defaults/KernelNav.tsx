// core/ui/canvas/src/app/ext/defaults/KernelNav.tsx
//
// Kernel-default sidebar navigation — rendered when no extension fills
// the `nav` slot. Covers the kernel's own surfaces only; an extension
// nav (registered through the ext seam) replaces this wholesale and is
// expected to link back to the room.
import { type ComponentType } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { LayoutGrid, Map, StickyNote, Users } from 'lucide-react'

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

interface NavItem {
  href: string
  icon: ComponentType<{ className?: string }>
  label: string
}

const NAV: NavItem[] = [
  { href: '/atrium', icon: Users, label: 'Atrium' },
  { href: '/landscape', icon: Map, label: 'Product map' },
  { href: '/board', icon: StickyNote, label: 'The Board' },
  { href: '/showcase', icon: LayoutGrid, label: 'Showcase' },
]

export function KernelNav() {
  const { pathname } = useLocation()

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <Link
          to="/atrium"
          className="flex items-center gap-2.5 pl-2.5 pr-2 py-1.5 overflow-hidden"
        >
          <ACEMark size={22} variant="iris" />
          <span className="flex flex-col leading-tight group-data-[collapsible=icon]:hidden">
            <span className="text-base font-semibold tracking-tight">ACE</span>
            <span className="text-[10px] text-muted-foreground">
              the partnership canvas
            </span>
          </span>
        </Link>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Surfaces</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {NAV.map((item) => (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton
                    asChild
                    isActive={pathname === item.href}
                    tooltip={item.label}
                  >
                    <Link to={item.href}>
                      <item.icon />
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
