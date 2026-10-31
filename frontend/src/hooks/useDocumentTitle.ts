import { useEffect } from "react";
import { APP_NAME } from "../config/constants";

export function useDocumentTitle(title: string): void {
  useEffect(() => {
    document.title = title ? `${title} · ${APP_NAME} Operations Console` : `${APP_NAME} Operations Console`;
  }, [title]);
}
