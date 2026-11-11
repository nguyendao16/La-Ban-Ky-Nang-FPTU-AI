import { config } from "./config";
import type {
  Catalog,
  CourseDetail,
  CreatedProfile,
  CreatedSession,
  ProfilePayload,
  Profile,
  SessionPayload,
  Session,
  ChatReply,
  History,
  Health,
} from "./types";

export class ApiError extends Error {
  constructor(
    public code: string,
    public status = 0,
    public details?: unknown,
  ) {
    super(code);
  }
}
export class ApiClient {
  constructor(
    public baseUrl = config.baseUrl,
    public requestTimeout = config.requestTimeout,
    public chatTimeout = config.chatTimeout,
  ) {}
  private async request<T>(
    path: string,
    options: {
      payload?: unknown;
      token?: string;
      key?: string;
      signal?: AbortSignal;
      timeout?: number;
      health?: boolean;
    } = {},
  ): Promise<T> {
    const controller = new AbortController();
    let timedOut = false;
    const abort = () => controller.abort();
    options.signal?.addEventListener("abort", abort, { once: true });
    if (options.signal?.aborted) controller.abort();
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, options.timeout ?? this.requestTimeout);
    try {
      const response = await fetch(`${this.baseUrl}/api/v1${path}`, {
        method: options.payload === undefined ? "GET" : "POST",
        headers: {
          Accept: "application/json",
          ...(options.payload === undefined
            ? {}
            : { "Content-Type": "application/json" }),
          ...(options.token
            ? { Authorization: `Bearer ${options.token}` }
            : {}),
          ...(options.key ? { "Idempotency-Key": options.key } : {}),
        },
        body:
          options.payload === undefined
            ? undefined
            : JSON.stringify(options.payload),
        signal: controller.signal,
        cache: "no-store",
        credentials: "omit",
      });
      let body: unknown;
      try {
        body = await response.json();
      } catch {
        throw new ApiError("invalid_response", response.status);
      }
      if (!response.ok && !(options.health && response.status === 503)) {
        const error = (body as { error?: { code?: string; details?: unknown } })
          .error;
        throw new ApiError(
          error?.code || "http_error",
          response.status,
          error?.details,
        );
      }
      return body as T;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (options.signal?.aborted) throw new ApiError("cancelled");
      throw new ApiError(timedOut ? "transport_timeout" : "network_error");
    } finally {
      clearTimeout(timer);
      options.signal?.removeEventListener("abort", abort);
    }
  }
  listCourses = (signal?: AbortSignal) =>
    this.request<Catalog>("/courses", { signal });
  getCourse = (code: string, curriculum: string, signal?: AbortSignal) =>
    this.request<CourseDetail>(
      `/courses/${encodeURIComponent(code)}?curriculum_code=${encodeURIComponent(curriculum)}`,
      { signal },
    );
  createProfile = (payload: ProfilePayload) =>
    this.request<CreatedProfile>("/profiles", { payload });
  getProfile = (id: string, token: string, signal?: AbortSignal) =>
    this.request<Profile>(`/profiles/${encodeURIComponent(id)}`, {
      token,
      signal,
    });
  createAdvisorSession = (
    payload: SessionPayload,
    token: string,
    key: string,
  ) =>
    this.request<CreatedSession>("/advisor/sessions", { payload, token, key });
  getAdvisorSession = (id: string, token: string, signal?: AbortSignal) =>
    this.request<Session>(`/advisor/sessions/${encodeURIComponent(id)}`, {
      token,
      signal,
    });
  sendChatMessage = (
    id: string,
    message: string,
    token: string,
    key: string,
    signal?: AbortSignal,
  ) =>
    this.request<ChatReply>(
      `/advisor/sessions/${encodeURIComponent(id)}/messages`,
      { payload: { message }, token, key, signal, timeout: this.chatTimeout },
    );
  getChatHistory = (id: string, token: string, signal?: AbortSignal) =>
    this.request<History>(
      `/advisor/sessions/${encodeURIComponent(id)}/messages`,
      { token, signal },
    );
  getHealth = (signal?: AbortSignal) =>
    this.request<Health>("/health", { signal, health: true });
}
export const api = new ApiClient();
