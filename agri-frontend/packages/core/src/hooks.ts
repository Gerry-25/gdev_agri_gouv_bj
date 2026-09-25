import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api/client";
import { authStore, useSession } from "./auth/store";

export function useUnreadCount() {
  const { user } = useSession();
  return useQuery({
    queryKey: ["notifications", "unread"],
    enabled: !!user,
    refetchInterval: 120_000,
    queryFn: async () => {
      const { data } = await api.GET("/api/v1/notifications/me/unread-count");
      return (data as { unread?: number } | undefined)?.unread ?? 0;
    },
  });
}

export function useSignOut() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (allDevices: boolean) => {
      const refresh = authStore.get().refreshToken;
      try {
        if (allDevices) await api.POST("/api/v1/auth/logout-all");
        else if (refresh) await api.POST("/api/v1/auth/logout", { body: { refresh_token: refresh } });
      } catch {
        // hors ligne : la session locale est tout de même effacée
      }
    },
    onSettled: () => {
      authStore.clear();
      qc.clear();
    },
  });
}
