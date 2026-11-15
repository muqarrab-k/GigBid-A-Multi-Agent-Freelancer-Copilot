import { useQuery } from "@tanstack/react-query";
import { api, must } from "../lib/client";

export function StatusBanner() {
  const status = useQuery({
    queryKey: ["status"],
    queryFn: () => must(api.GET("/status")),
    refetchInterval: 10000,
  });
  if (!status.data?.degraded) return null;
  return (
    <div role="alert" className="bg-amber-500 px-4 py-2 text-center text-sm font-medium text-white">
      Marketplace unavailable. Runs and replies are queued; nothing is lost.
    </div>
  );
}
