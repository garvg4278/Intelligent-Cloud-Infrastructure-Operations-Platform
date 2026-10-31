import { createContext, useContext, type ReactNode } from "react";
import { DEFAULT_CONFIG, type RuntimeConfig } from "../config/runtime";

const ConfigContext = createContext<RuntimeConfig>(DEFAULT_CONFIG);

export const ConfigProvider = ({ value, children }: { value: RuntimeConfig; children: ReactNode }) => (
  <ConfigContext.Provider value={value}>{children}</ConfigContext.Provider>
);

export const useConfig = (): RuntimeConfig => useContext(ConfigContext);
