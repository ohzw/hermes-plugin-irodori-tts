import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react';
import {cn} from '../lib/utils';

type ButtonVariant = 'default' | 'outline' | 'ghost' | 'destructive';

export function Button({
  className,
  variant = 'default',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {variant?: ButtonVariant}) {
  return (
    <button
      className={cn('ui-button', `ui-button-${variant}`, className)}
      {...props}
    />
  );
}

export function Card({className, children}: {className?: string; children: ReactNode}) {
  return <section className={cn('ui-card', className)}>{children}</section>;
}

export function CardHeader({className, children}: {className?: string; children: ReactNode}) {
  return <div className={cn('ui-card-header', className)}>{children}</div>;
}

export function CardContent({className, children}: {className?: string; children: ReactNode}) {
  return <div className={cn('ui-card-content', className)}>{children}</div>;
}

export function Input({className, ...props}: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn('ui-input', className)} {...props} />;
}

export function Textarea({className, ...props}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn('ui-textarea', className)} {...props} />;
}

export function Select({className, ...props}: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn('ui-select', className)} {...props} />;
}

export function Switch({className, ...props}: InputHTMLAttributes<HTMLInputElement>) {
  return <input type="checkbox" className={cn('ui-switch', className)} {...props} />;
}

export function Badge({className, children}: {className?: string; children: ReactNode}) {
  return <span className={cn('ui-badge', className)}>{children}</span>;
}

export function Separator({className}: {className?: string}) {
  return <div className={cn('ui-separator', className)} role="separator" />;
}

export function Tabs({className, children}: {className?: string; children: ReactNode}) {
  return <div className={cn('ui-tabs', className)}>{children}</div>;
}

export function TabsList({className, children}: {className?: string; children: ReactNode}) {
  return (
    <div className={cn('ui-tabs-list', className)} role="tablist">
      {children}
    </div>
  );
}

export function TabsTrigger({
  className,
  active,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {active?: boolean}) {
  return (
    <button
      className={cn('ui-tab', active && 'ui-tab-active', className)}
      role="tab"
      aria-selected={active}
      {...props}
    >
      {children}
    </button>
  );
}
