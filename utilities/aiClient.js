/**
 * Server-side client for POST /ai/search.
 *
 * searchAI(query) does not throw for expected failures. It always resolves
 * to a plain object with this shape:
 *
 * {
 *   ok: boolean,
 *   status: "results" | "empty" | "agent_error" | "invalid_input"
 *         | "invalid_config" | "unavailable",
 *   code: string,          // stable classification, safe to log
 *   detail: string | null, // short token such as "empty" or "500"
 *   query: string | null,  // trimmed query when the input was a string of valid length
 *   summary: string | null,
 *   agentError: string | null,
 *   results: Array<{ _id: string, score: number | null, reason: string | null }>
 * }
 *
 * ok is true only when the AI service completed a search: "results",
 * "empty", or "agent_error". An HTTP 200 body with an error string is
 * agent_error, not a transport failure. "invalid_input", "invalid_config",
 * and "unavailable" are local or transport failures.
 *
 * results contains trusted ids plus an optional score and reason.
 * Titles, prices, images, and other listing fields are omitted. The
 * Express layer re-fetches those documents from MongoDB.
 */

const DEFAULT_AI_API_URL = "http://127.0.0.1:8000";
const DEFAULT_AI_SEARCH_TIMEOUT_MS = 45000;
const MAX_QUERY_LENGTH = 500;
const LISTING_ID = /^[a-fA-F0-9]{24}$/;

function outcome(status, code, detail, extra) {
    return {
        ok: status === "results" || status === "empty" || status === "agent_error",
        status,
        code,
        detail: detail == null ? null : detail,
        query: null,
        summary: null,
        agentError: null,
        results: [],
        ...extra,
    };
}

function validateQuery(query) {
    if (typeof query !== "string") {
        return outcome("invalid_input", "ai_search_invalid_input", "not_a_string");
    }

    const trimmed = query.trim();
    if (!trimmed) {
        return outcome("invalid_input", "ai_search_invalid_input", "empty", {
            query: trimmed,
        });
    }
    if (trimmed.length > MAX_QUERY_LENGTH) {
        return outcome("invalid_input", "ai_search_invalid_input", "too_long");
    }

    return trimmed;
}

function resolveSearchUrl(rawValue) {
    if (rawValue == null) {
        return `${DEFAULT_AI_API_URL}/ai/search`;
    }
    if (typeof rawValue !== "string" || rawValue.trim() === "") {
        return outcome("invalid_config", "ai_search_invalid_config", "empty");
    }

    const trimmed = rawValue.trim().replace(/\/+$/, "");
    let parsed;
    try {
        parsed = new URL(trimmed);
    } catch {
        return outcome("invalid_config", "ai_search_invalid_config", "malformed");
    }

    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
        return outcome("invalid_config", "ai_search_invalid_config", "unsupported_protocol");
    }

    return `${trimmed}/ai/search`;
}

function resolveSearchTimeout(rawValue) {
    if (rawValue == null) {
        return DEFAULT_AI_SEARCH_TIMEOUT_MS;
    }
    const text = typeof rawValue === "string" ? rawValue.trim() : String(rawValue);
    if (!/^[1-9]\d*$/.test(text)) {
        return DEFAULT_AI_SEARCH_TIMEOUT_MS;
    }
    const parsed = Number(text);
    if (!Number.isSafeInteger(parsed) || parsed <= 0) {
        return DEFAULT_AI_SEARCH_TIMEOUT_MS;
    }
    return parsed;
}

function validScore(value) {
    if (typeof value !== "number" || !Number.isFinite(value)) {
        return null;
    }
    if (value < 0 || value > 1) {
        return null;
    }
    return value;
}

function normalizePayload(payload, query) {
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
        return outcome("unavailable", "ai_search_malformed", "results", { query });
    }
    if (!Array.isArray(payload.results)) {
        return outcome("unavailable", "ai_search_malformed", "results", { query });
    }

    const summary = typeof payload.summary === "string" ? payload.summary : null;
    const agentError = typeof payload.error === "string" && payload.error.trim()
        ? payload.error
        : null;

    const seen = new Set();
    const results = [];
    for (const item of payload.results) {
        if (!item || typeof item !== "object" || Array.isArray(item)) {
            continue;
        }
        if (typeof item._id !== "string" || !LISTING_ID.test(item._id)) {
            continue;
        }
        if (seen.has(item._id)) {
            continue;
        }
        seen.add(item._id);
        results.push({
            _id: item._id,
            score: validScore(item.score),
            reason: typeof item.reason === "string" ? item.reason : null,
        });
    }

    if (agentError) {
        return outcome("agent_error", "ai_search_agent_error", null, {
            query,
            summary,
            agentError,
            results,
        });
    }

    if (results.length === 0) {
        return outcome("empty", "ai_search_empty", null, {
            query,
            summary,
            results,
        });
    }

    return outcome("results", "ai_search_ok", null, {
        query,
        summary,
        results,
    });
}

function failureFromThrow(err) {
    const name = err && typeof err.name === "string" ? err.name : "";
    if (name === "TimeoutError" || name === "AbortError") {
        return outcome("unavailable", "ai_search_timeout", "timeout");
    }
    return outcome("unavailable", "ai_search_connection", "connection");
}

async function discardBody(response) {
    try {
        if (response && response.body && typeof response.body.cancel === "function") {
            await response.body.cancel();
        }
    } catch {
        // Dropping the body is best-effort. The caller still returns a safe outcome.
    }
}

async function searchAI(query) {
    const validated = validateQuery(query);
    if (validated && typeof validated === "object") {
        return validated;
    }

    const endpoint = resolveSearchUrl(process.env.AI_API_URL);
    if (typeof endpoint !== "string") {
        return outcome(endpoint.status, endpoint.code, endpoint.detail, {
            query: validated,
        });
    }

    let response;
    try {
        response = await fetch(endpoint, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ query: validated }),
            signal: AbortSignal.timeout(
                resolveSearchTimeout(process.env.AI_SEARCH_TIMEOUT_MS)
            ),
            redirect: "error",
        });
    } catch (err) {
        const failed = failureFromThrow(err);
        failed.query = validated;
        return failed;
    }

    if (!response || typeof response.ok !== "boolean" || !response.ok) {
        await discardBody(response);
        const status = response && Number.isInteger(response.status)
            ? String(response.status)
            : "http";
        return outcome("unavailable", "ai_search_http", status, { query: validated });
    }

    let payload;
    try {
        if (typeof response.json !== "function") {
            throw new TypeError("json");
        }
        payload = await response.json();
    } catch {
        await discardBody(response);
        return outcome("unavailable", "ai_search_malformed", "json", { query: validated });
    }

    return normalizePayload(payload, validated);
}

module.exports = {
    searchAI,
    DEFAULT_AI_API_URL,
    DEFAULT_AI_SEARCH_TIMEOUT_MS,
    resolveSearchTimeout,
    MAX_QUERY_LENGTH,
};
