import * as React from 'react'
import { Circle } from 'lucide-react'
import { RadioGroup as RadioGroupPrimitive } from 'radix-ui'

import { cn } from '@/lib/utils'

function RadioGroup({
  className,
  ...props
}: React.ComponentProps<typeof RadioGroupPrimitive.Root>) {
  return (
    <RadioGroupPrimitive.Root
      data-slot="radio-group"
      className={cn('grid gap-2', className)}
      {...props}
    />
  )
}

function RadioGroupItem({
  className,
  children,
  ...props
}: React.ComponentProps<typeof RadioGroupPrimitive.Item>) {
  return (
    <RadioGroupPrimitive.Item
      data-slot="radio-group-item"
      className={cn(
        'group/radio text-left outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    >
      <span className="mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full border border-input bg-background group-data-[state=checked]/radio:border-foreground">
        <RadioGroupPrimitive.Indicator className="flex items-center justify-center">
          <Circle className="size-2 fill-current text-foreground" aria-hidden="true" />
        </RadioGroupPrimitive.Indicator>
      </span>
      {children}
    </RadioGroupPrimitive.Item>
  )
}

export { RadioGroup, RadioGroupItem }
