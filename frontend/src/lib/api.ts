import { clearTokens, getAccessToken } from "@/lib/auth";

const baseURL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export type ApiEnvelope<T> = {
  code: number;
  data: T;
  message?: string;
  detail?: unknown;
};

type ApiOptions = {
  method?: string;
  body?: BodyInit | null;
  headers?: Record<string, string>;
  auth?: boolean;
};

type ApiErrorPayload = {
  message?: unknown;
  detail?: unknown;
};

function normalizeApiError(payload: ApiErrorPayload | string): string {
  if (typeof payload === "string") {
    return payload.trim() || "请求失败";
  }

  const candidate = payload.message ?? payload.detail;
  if (typeof candidate === "string" && candidate.trim()) {
    return candidate;
  }

  if (Array.isArray(candidate) && candidate.length > 0) {
    const first = candidate[0];
    if (typeof first === "string" && first.trim()) {
      return first;
    }
    if (first && typeof first === "object") {
      const record = first as Record<string, unknown>;
      const msg = typeof record.msg === "string" ? record.msg : "输入不合法";
      if (Array.isArray(record.loc) && record.loc.length > 0) {
        const field = String(record.loc[record.loc.length - 1]);
        return `${field}: ${msg}`;
      }
      return msg;
    }
  }

  if (candidate && typeof candidate === "object") {
    const record = candidate as Record<string, unknown>;
    if (typeof record.msg === "string" && record.msg.trim()) {
      return record.msg;
    }
  }

  return "请求失败";
}

function isExpiredAuthError(response: Response, message: string): boolean {
  if (response.status !== 401) {
    return false;
  }
  return /signature has expired|token.*expired|expired token|unauthorized|认证|登录|过期/i.test(message);
}

function normalizeFailure(response: Response, payload: ApiErrorPayload | string): Error {
  const message = normalizeApiError(payload);
  if (isExpiredAuthError(response, message)) {
    clearTokens();
    return new Error("登录已过期，请重新登录");
  }
  return new Error(message);
}

function normalizeNetworkError(error: unknown): Error {
  if (error instanceof Error && /network|failed to fetch|fetch failed/i.test(error.message)) {
    return new Error("网络连接失败，请确认后端服务已启动");
  }
  return error instanceof Error ? error : new Error("网络连接失败，请确认后端服务已启动");
}

async function parseResponseBody(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";
  const text = await response.text();

  if (!text) {
    return {};
  }

  if (contentType.includes("application/json")) {
    return JSON.parse(text);
  }

  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export async function apiRequest<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const headers = new Headers(options.headers ?? {});
  if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  if (options.auth) {
    const token = getAccessToken();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }

  let response: Response;
  try {
    response = await fetch(`${baseURL}${path}`, {
      method: options.method ?? "GET",
      body: options.body ?? null,
      headers,
      cache: "no-store",
    });
  } catch (error) {
    throw normalizeNetworkError(error);
  }

  const payload = await parseResponseBody(response);
  if (!response.ok) {
    throw normalizeFailure(response, payload as ApiErrorPayload | string);
  }

  return payload as T;
}

export async function apiJson<T>(path: string, body: unknown, auth = false): Promise<T> {
  return apiRequest<T>(path, {
    method: "POST",
    body: JSON.stringify(body),
    auth,
  });
}

export function uploadWithProgress<T>(
  path: string,
  file: File,
  onProgress: (progress: number) => void,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${baseURL}${path}`);

    const token = getAccessToken();
    if (token) {
      xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    }

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };

    xhr.onload = () => {
      try {
        const payload = xhr.responseText ? JSON.parse(xhr.responseText) : {};
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(payload as T);
          return;
        }
        reject(new Error(normalizeApiError(payload as ApiErrorPayload)));
      } catch {
        reject(new Error(xhr.responseText || "上传失败"));
      }
    };

    xhr.onerror = () => reject(new Error("网络错误"));

    const formData = new FormData();
    formData.append("file", file);
    xhr.send(formData);
  });
}

export async function postSseStream(
  path: string,
  body: unknown,
  onEvent: (event: Record<string, unknown>) => void,
  options: { signal?: AbortSignal } = {},
): Promise<void> {
  const headers = new Headers({ "Content-Type": "application/json" });
  const token = getAccessToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  let response: Response;
  try {
    response = await fetch(`${baseURL}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      cache: "no-store",
      signal: options.signal,
    });
  } catch (error) {
    if (options.signal?.aborted) {
      throw error;
    }
    throw normalizeNetworkError(error);
  }

  if (!response.ok || !response.body) {
    const payload = await parseResponseBody(response);
    if (!response.ok) {
      throw normalizeFailure(response, payload as ApiErrorPayload | string);
    }
    throw new Error("SSE 请求失败");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";

    for (const part of parts) {
      const eventLines = part
        .split("\n")
        .filter((line) => line.startsWith("event: "))
        .map((line) => line.slice(7).trim());
      const dataLines = part
        .split("\n")
        .filter((line) => line.startsWith("data: "))
        .map((line) => line.slice(6));
      if (!dataLines.length) {
        continue;
      }
      const payload = JSON.parse(dataLines.join("")) as Record<string, unknown>;
      if (eventLines.length && !payload.type) {
        payload.type = eventLines[eventLines.length - 1];
      }
      onEvent(payload);
    }
  }
}

