import type { ReactNode } from "react";

export interface Column<T> {
  header: string;
  cell: (row: T) => ReactNode;
  /** Hidden at narrow widths when it is secondary information. */
  secondary?: boolean;
}

/**
 * A real <table> for screen readers that collapses into labelled cards on
 * phones (each cell shows its header via data-label), so nothing scrolls sideways.
 */
export function DataTable<T>({ columns, rows, rowKey, caption }: { columns: Column<T>[]; rows: T[]; rowKey: (row: T) => string; caption: string }) {
  return (
    <table className="table">
      <caption className="sr-only">{caption}</caption>
      <thead>
        <tr>
          {columns.map((c) => (
            <th key={c.header} scope="col" className={c.secondary ? "secondary" : undefined}>
              {c.header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={rowKey(row)}>
            {columns.map((c) => (
              <td key={c.header} data-label={c.header} className={c.secondary ? "secondary" : undefined}>
                {c.cell(row)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
