/** Case-insensitive "does any of these fields contain the query" over already-loaded rows. */
export function matchesQuery(query: string, ...fields: Array<string | null | undefined>): boolean {
  const q = query.trim().toLowerCase();
  return q === "" || fields.some((field) => field?.toLowerCase().includes(q));
}
