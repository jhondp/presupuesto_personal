// HTTP client boundary: every call injects the caller's current Supabase
// access token as a Bearer header and maps FastAPI's stable error envelope
// ({code, message, field_errors, request_id}, see design.md's Interfaces
// section) into a typed ApiError instead of a bare fetch Response.

const env = window.__ENV__ || {};
const API_BASE_URL = env.API_BASE_URL || "";

export class ApiError extends Error {
  constructor(status, code, message, fieldErrors) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fieldErrors = fieldErrors || {};
  }
}

async function request(method, path, { token, body, headers } = {}) {
  const finalHeaders = { "Content-Type": "application/json", ...(headers || {}) };
  if (token) finalHeaders.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: finalHeaders,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (response.status === 204) return null;

  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    throw new ApiError(
      response.status,
      data && data.code ? data.code : "unknown_error",
      data && data.message ? data.message : "Request failed",
      data ? data.field_errors : undefined
    );
  }
  return data;
}

export const api = {
  get: (path, opts) => request("GET", path, opts),
  post: (path, opts) => request("POST", path, opts),
  put: (path, opts) => request("PUT", path, opts),
  delete: (path, opts) => request("DELETE", path, opts),
};
