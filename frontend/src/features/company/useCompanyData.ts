import { useEffect, useState } from "react";

import { getJson } from "../../api/client";

type RequestState<T> = {
  data: T | null;
  error: string | null;
  loading: boolean;
};

export function useCompanyData<T>(path: string): RequestState<T> {
  const [state, setState] = useState<RequestState<T>>({
    data: null,
    error: null,
    loading: true,
  });

  useEffect(() => {
    let cancelled = false;
    setState({ data: null, error: null, loading: true });

    void getJson<T>(path)
      .then((data) => {
        if (!cancelled) setState({ data, error: null, loading: false });
      })
      .catch((error: Error) => {
        if (!cancelled) setState({ data: null, error: error.message, loading: false });
      });

    return () => {
      cancelled = true;
    };
  }, [path]);

  return state;
}
