import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

export function useResource<T>(
  key: readonly unknown[],
  path: string,
  enabled = true,
  refetchInterval?: number,
) {
  return useQuery({
    queryKey: key,
    queryFn: () => api<T>(path),
    enabled,
    refetchInterval,
  });
}

export function Feedback({
  error,
  success,
}: {
  error?: string | null;
  success?: string | null;
}) {
  return (
    <>
      {error && (
        <p role="alert" className="notice error">
          {error}
        </p>
      )}
      {success && (
        <p role="status" className="notice success">
          {success}
        </p>
      )}
    </>
  );
}

export function QueryState({
  loading,
  error,
}: {
  loading: boolean;
  error: Error | null;
}) {
  if (loading)
    return (
      <p role="status" className="muted">
        Carregando dados…
      </p>
    );
  if (error)
    return (
      <p role="alert" className="notice error">
        {error.message}
      </p>
    );
  return null;
}
