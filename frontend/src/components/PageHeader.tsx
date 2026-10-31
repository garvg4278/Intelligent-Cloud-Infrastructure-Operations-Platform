import { useEffect, useRef, type ReactNode } from "react";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

/** Sets the tab title and moves focus to the h1 on navigation, so keyboard and screen-reader users land at the top of the new page. */
export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useDocumentTitle(title);
  useEffect(() => heading.current?.focus({ preventScroll: true }), []);
  return (
    <header className="page-header">
      <div>
        <h1 ref={heading} tabIndex={-1}>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}
