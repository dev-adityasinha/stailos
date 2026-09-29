/** Live-refreshing data fetching for dashboards: polls every 30s and
 *  revalidates whenever the tab regains focus, on top of the existing
 *  `api()` client (auth headers, 401 refresh) — no new backend infra. */
import useSWR, { type SWRConfiguration } from "swr";
import { api } from "@/lib/api";

export function useApiSWR<T>(path: string | null, config?: SWRConfiguration) {
  return useSWR<T>(path, (p: string) => api<T>(p), {
    refreshInterval: 30_000,
    revalidateOnFocus: true,
    dedupingInterval: 5_000,
    ...config,
  });
}
