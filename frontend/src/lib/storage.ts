/**
 * localStorage that never throws. It is unavailable in some private-browsing
 * modes and when storage is blocked; the UI must still render without it.
 */
export function readStorage(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeStorage(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* storage unavailable: the value just won't persist */
  }
}

export function removeStorage(key: string): void {
  try {
    window.localStorage.removeItem(key);
  } catch {
    /* nothing to clean up */
  }
}
