import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach } from "vitest";

beforeEach(() => {
  window.localStorage.clear();
  window.history.replaceState(null, "", "/");
  document.documentElement.removeAttribute("data-theme");
  window.scrollTo = () => undefined;
});
afterEach(() => cleanup());
