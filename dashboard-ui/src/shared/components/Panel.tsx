import type { ReactNode } from 'react';
export function Panel({title, eyebrow, children}: {title: string; eyebrow?: string; children: ReactNode}) { return <section className="panel">{eyebrow && <div className="eyebrow">{eyebrow}</div>}<h2>{title}</h2>{children}</section>; }
