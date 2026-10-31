const { describe, it, beforeEach, afterEach } = require("node:test");
const assert = require("node:assert/strict");

const {
    searchAI,
    DEFAULT_AI_API_URL,
    DEFAULT_AI_SEARCH_TIMEOUT_MS,
    resolveSearchTimeout,
} = require("../utilities/aiClient");

const VALID_A = "69485099aaaaaaaaaaaaaaaa";
const VALID_B = "69485099aaaaaaaaaaaaaaab";

function jsonResponse(body, status = 200) {
    return {
        ok: status >= 200 && status < 300,
        status,
        json: async () => body,
        text: async () => JSON.stringify(body),
        body: { cancel: async () => {} },
    };
}

describe("searchAI", { concurrency: 1 }, () => {
    const originalFetch = global.fetch;
    const hadApiUrl = Object.hasOwn(process.env, "AI_API_URL");
    const originalApiUrl = process.env.AI_API_URL;
    const hadTimeout = Object.hasOwn(process.env, "AI_SEARCH_TIMEOUT_MS");
    const originalTimeout = process.env.AI_SEARCH_TIMEOUT_MS;

    beforeEach(() => {
        delete process.env.AI_API_URL;
        delete process.env.AI_SEARCH_TIMEOUT_MS;
        global.fetch = originalFetch;
    });

    afterEach(() => {
        global.fetch = originalFetch;
        if (hadApiUrl) {
            process.env.AI_API_URL = originalApiUrl;
        } else {
            delete process.env.AI_API_URL;
        }
        if (hadTimeout) {
            process.env.AI_SEARCH_TIMEOUT_MS = originalTimeout;
        } else {
            delete process.env.AI_SEARCH_TIMEOUT_MS;
        }
    });

    async function withTimeoutSpy(fn) {
        const seen = [];
        const original = AbortSignal.timeout;
        AbortSignal.timeout = (ms) => {
            seen.push(ms);
            return original.call(AbortSignal, ms);
        };
        try {
            await fn(seen);
        } finally {
            AbortSignal.timeout = original;
        }
    }

    it("returns valid listing ids in order and drops untrusted listing fields", async () => {
        const calls = [];
        global.fetch = async (url, init) => {
            calls.push({ url, init });
            return jsonResponse({
                query: "mountain cabin",
                intent: { category: "Mountains" },
                summary: "Cedar Cabin is in Manali.",
                error: null,
                debug: "gsk_should_not_leak",
                results: [
                    {
                        _id: VALID_A,
                        title: "Cedar Cabin",
                        price: 4200,
                        image: { url: "javascript:alert(1)" },
                        score: 0.86,
                        reason: "Quiet cabin",
                    },
                    {
                        _id: VALID_A,
                        title: "Duplicate",
                        score: 0.2,
                        reason: "duplicate",
                    },
                    {
                        _id: VALID_B,
                        title: "Second",
                        score: 1,
                        reason: "Second reason",
                    },
                ],
            });
        };

        const result = await searchAI("  mountain cabin  ");

        assert.equal(calls.length, 1);
        assert.equal(calls[0].url, `${DEFAULT_AI_API_URL}/ai/search`);
        assert.equal(calls[0].init.method, "POST");
        assert.equal(calls[0].init.headers["Content-Type"], "application/json");
        assert.equal(calls[0].init.body, JSON.stringify({ query: "mountain cabin" }));
        assert.equal(calls[0].init.redirect, "error");
        assert.ok(calls[0].init.signal instanceof AbortSignal);
        assert.equal(DEFAULT_AI_SEARCH_TIMEOUT_MS, 45000);

        assert.deepEqual(result, {
            ok: true,
            status: "results",
            code: "ai_search_ok",
            detail: null,
            query: "mountain cabin",
            summary: "Cedar Cabin is in Manali.",
            agentError: null,
            results: [
                { _id: VALID_A, score: 0.86, reason: "Quiet cabin" },
                { _id: VALID_B, score: 1, reason: "Second reason" },
            ],
        });
        assert.equal(Object.hasOwn(result.results[0], "title"), false);
        assert.equal(Object.hasOwn(result.results[0], "image"), false);
        assert.equal(Object.hasOwn(result.results[0], "price"), false);
        assert.equal(JSON.stringify(result).includes("javascript:"), false);
        assert.equal(JSON.stringify(result).includes("gsk_should_not_leak"), false);
    });

    it("treats an empty results array as a completed search", async () => {
        global.fetch = async () => jsonResponse({
            summary: "No listings matched this search.",
            error: null,
            results: [],
        });

        const result = await searchAI("quiet cabin");

        assert.equal(result.ok, true);
        assert.equal(result.status, "empty");
        assert.equal(result.code, "ai_search_empty");
        assert.equal(result.summary, "No listings matched this search.");
        assert.equal(result.agentError, null);
        assert.deepEqual(result.results, []);
    });

    it("treats HTTP 200 with an agent error as a completed search", async () => {
        global.fetch = async () => jsonResponse({
            summary: "Beach is not a supported category.",
            error: "unsupported_category: Beach",
            results: [],
        });

        const result = await searchAI("find a beach hut");

        assert.equal(result.ok, true);
        assert.equal(result.status, "agent_error");
        assert.equal(result.code, "ai_search_agent_error");
        assert.equal(result.agentError, "unsupported_category: Beach");
        assert.equal(result.summary, "Beach is not a supported category.");
        assert.deepEqual(result.results, []);
        assert.equal(result.stack, undefined);
    });

    it("excludes invalid listing ids and keeps the valid ones", async () => {
        global.fetch = async () => jsonResponse({
            summary: "Some matches",
            error: null,
            results: [
                { _id: "too-short", score: 0.4, reason: "no" },
                { _id: "zzzzzzzzzzzzzzzzzzzzzzzz", score: 0.4, reason: "no" },
                { _id: 123, score: 0.4, reason: "no" },
                null,
                "not-an-object",
                { score: 0.4, reason: "missing id" },
                { _id: VALID_B, score: 0, reason: "kept" },
            ],
        });

        const result = await searchAI("any property");

        assert.equal(result.status, "results");
        assert.deepEqual(result.results, [
            { _id: VALID_B, score: 0, reason: "kept" },
        ]);
    });

    it("drops invalid scores and non-string summary or reason values", async () => {
        global.fetch = async () => jsonResponse({
            summary: { text: "not a string" },
            error: null,
            results: [
                { _id: VALID_A, score: 1.1, reason: 12 },
                { _id: VALID_B, score: Number.NaN, reason: null },
                { _id: "69485099aaaaaaaaaaaaaaac", score: "0.5", reason: "ok" },
            ],
        });

        const result = await searchAI("any property");

        assert.equal(result.status, "results");
        assert.equal(result.summary, null);
        assert.deepEqual(result.results, [
            { _id: VALID_A, score: null, reason: null },
            { _id: VALID_B, score: null, reason: null },
            { _id: "69485099aaaaaaaaaaaaaaac", score: null, reason: "ok" },
        ]);
    });

    it("does not call fetch for a blank query", async () => {
        let called = false;
        global.fetch = async () => {
            called = true;
            throw new Error("fetch should not run");
        };

        const result = await searchAI("   ");

        assert.equal(called, false);
        assert.deepEqual(result, {
            ok: false,
            status: "invalid_input",
            code: "ai_search_invalid_input",
            detail: "empty",
            query: "",
            summary: null,
            agentError: null,
            results: [],
        });
    });

    it("does not call fetch for a query longer than 500 characters", async () => {
        let called = false;
        global.fetch = async () => {
            called = true;
            throw new Error("fetch should not run");
        };

        const result = await searchAI(`  ${"a".repeat(501)}  `);

        assert.equal(called, false);
        assert.equal(result.ok, false);
        assert.equal(result.status, "invalid_input");
        assert.equal(result.detail, "too_long");
        assert.equal(result.query, null);
        assert.equal(result.code, "ai_search_invalid_input");
    });

    it("does not call fetch for a non-string query", async () => {
        for (const value of [null, undefined, 12, { query: "cabin" }, ["cabin"]]) {
            let called = false;
            global.fetch = async () => {
                called = true;
                throw new Error("fetch should not run");
            };

            const result = await searchAI(value);

            assert.equal(called, false);
            assert.equal(result.status, "invalid_input");
            assert.equal(result.detail, "not_a_string");
            assert.equal(result.query, null);
        }
    });

    it("uses the local default when AI_API_URL is missing", async () => {
        let seenUrl = "";
        global.fetch = async (url) => {
            seenUrl = url;
            return jsonResponse({ summary: "ok", error: null, results: [] });
        };

        delete process.env.AI_API_URL;
        const result = await searchAI("cabin");

        assert.equal(seenUrl, "http://127.0.0.1:8000/ai/search");
        assert.equal(result.status, "empty");
    });

    it("rejects an explicitly empty AI_API_URL before fetch", async () => {
        for (const value of ["", "   ", "\n\t"]) {
            let called = false;
            global.fetch = async () => {
                called = true;
                throw new Error("fetch should not run");
            };
            process.env.AI_API_URL = value;

            const result = await searchAI("cabin");

            assert.equal(called, false);
            assert.equal(result.ok, false);
            assert.equal(result.status, "invalid_config");
            assert.equal(result.code, "ai_search_invalid_config");
            assert.equal(result.detail, "empty");
            assert.equal(result.query, "cabin");
        }
    });

    it("rejects a malformed URL and an unsupported protocol before fetch", async () => {
        const cases = [
            ["not a url", "malformed"],
            ["http://", "malformed"],
            ["ftp://127.0.0.1:8000", "unsupported_protocol"],
            ["file:///tmp/listings", "unsupported_protocol"],
            ["javascript:alert(1)", "unsupported_protocol"],
        ];

        for (const [value, detail] of cases) {
            let called = false;
            global.fetch = async () => {
                called = true;
                throw new Error("fetch should not run");
            };
            process.env.AI_API_URL = value;

            const result = await searchAI("cabin");

            assert.equal(called, false, value);
            assert.equal(result.status, "invalid_config");
            assert.equal(result.detail, detail);
            assert.equal(JSON.stringify(result).includes(value), false);
        }
    });

    it("appends /ai/search once when the base URL has trailing slashes", async () => {
        let seenUrl = "";
        global.fetch = async (url) => {
            seenUrl = url;
            return jsonResponse({ summary: null, error: null, results: [] });
        };
        process.env.AI_API_URL = "http://127.0.0.1:8000///";

        await searchAI("cabin");

        assert.equal(seenUrl, "http://127.0.0.1:8000/ai/search");
    });

    it("classifies a non-success HTTP status without returning the body", async () => {
        const secret = "gsk_testsecretvalue mongodb+srv://user:password@cluster";
        global.fetch = async () => ({
            ok: false,
            status: 500,
            json: async () => {
                throw new Error(`should not read json ${secret}`);
            },
            text: async () => secret,
            body: { cancel: async () => {} },
        });

        const result = await searchAI("cabin");

        assert.equal(result.ok, false);
        assert.equal(result.status, "unavailable");
        assert.equal(result.code, "ai_search_http");
        assert.equal(result.detail, "500");
        assert.equal(result.stack, undefined);
        const encoded = JSON.stringify(result);
        assert.equal(encoded.includes("gsk_testsecretvalue"), false);
        assert.equal(encoded.includes("password"), false);
        assert.equal(encoded.includes("mongodb"), false);
        assert.equal(encoded.includes("should not read json"), false);
    });

    it("classifies invalid JSON without returning the body", async () => {
        const secret = "raw-body-password-atlas";
        global.fetch = async () => ({
            ok: true,
            status: 200,
            json: async () => {
                throw new SyntaxError(`Unexpected token ${secret}`);
            },
            text: async () => secret,
            body: { cancel: async () => {} },
        });

        const result = await searchAI("cabin");

        assert.equal(result.status, "unavailable");
        assert.equal(result.code, "ai_search_malformed");
        assert.equal(result.detail, "json");
        assert.equal(JSON.stringify(result).includes(secret), false);
        assert.equal(result.stack, undefined);
    });

    it("classifies a missing or non-array results field as malformed", async () => {
        global.fetch = async () => jsonResponse({
            summary: "ignored",
            error: null,
        });
        const missing = await searchAI("cabin");
        assert.equal(missing.status, "unavailable");
        assert.equal(missing.code, "ai_search_malformed");
        assert.equal(missing.detail, "results");
        assert.equal(missing.summary, null);

        global.fetch = async () => jsonResponse({
            summary: "ignored",
            error: "mcp_search_failed",
            results: {},
        });
        const notArray = await searchAI("cabin");
        assert.equal(notArray.status, "unavailable");
        assert.equal(notArray.code, "ai_search_malformed");
        assert.equal(notArray.agentError, null);
    });

    it("classifies a connection failure without exposing the thrown error", async () => {
        const secret = "user:s3cret-token";
        process.env.AI_API_URL = `http://${secret}@127.0.0.1:9`;
        global.fetch = async () => {
            const err = new TypeError(`connect ECONNREFUSED ${secret}`);
            err.stack = `TypeError: ${secret}\n    at SECRET_STACK`;
            throw err;
        };

        const result = await searchAI("cabin");

        assert.equal(result.ok, false);
        assert.equal(result.status, "unavailable");
        assert.equal(result.code, "ai_search_connection");
        assert.equal(result.detail, "connection");
        assert.equal(result.stack, undefined);
        assert.equal(result.message, undefined);
        const encoded = JSON.stringify(result);
        assert.equal(encoded.includes("s3cret-token"), false);
        assert.equal(encoded.includes("SECRET_STACK"), false);
        assert.equal(encoded.includes("ECONNREFUSED"), false);
    });

    it("uses a 45000ms timeout when AI_SEARCH_TIMEOUT_MS is missing", async () => {
        await withTimeoutSpy(async (seen) => {
            global.fetch = async () => jsonResponse({
                summary: "ok",
                error: null,
                results: [],
            });
            const result = await searchAI("cabin");
            assert.equal(result.status, "empty");
            assert.deepEqual(seen, [45000]);
            assert.equal(resolveSearchTimeout(undefined), 45000);
        });
    });

    it("uses a valid AI_SEARCH_TIMEOUT_MS override", async () => {
        process.env.AI_SEARCH_TIMEOUT_MS = " 12000 ";
        await withTimeoutSpy(async (seen) => {
            global.fetch = async () => jsonResponse({
                summary: "ok",
                error: null,
                results: [],
            });
            const result = await searchAI("cabin");
            assert.equal(result.ok, true);
            assert.deepEqual(seen, [12000]);
        });
    });

    it("uses the default timeout when AI_SEARCH_TIMEOUT_MS is invalid", async () => {
        for (const value of ["", "   ", "0", "-5", "45.5", "abc", "Infinity", "9007199254740993"]) {
            process.env.AI_SEARCH_TIMEOUT_MS = value;
            await withTimeoutSpy(async (seen) => {
                let called = false;
                global.fetch = async () => {
                    called = true;
                    return jsonResponse({ summary: "ok", error: null, results: [] });
                };
                const result = await searchAI("cabin");
                assert.equal(called, true);
                assert.notEqual(result.status, "invalid_config");
                assert.deepEqual(seen, [DEFAULT_AI_SEARCH_TIMEOUT_MS]);
            });
        }
    });

    it("classifies a timeout or abort without exposing the thrown error", async () => {
        const secret = "timeout-secret-body";
        global.fetch = async () => {
            const err = new DOMException(`timed out ${secret}`, "TimeoutError");
            err.stack = `TimeoutError: ${secret}\n    at SECRET_STACK`;
            throw err;
        };

        const timedOut = await searchAI("cabin");

        assert.equal(timedOut.status, "unavailable");
        assert.equal(timedOut.code, "ai_search_timeout");
        assert.equal(timedOut.detail, "timeout");
        assert.equal(timedOut.stack, undefined);
        assert.equal(JSON.stringify(timedOut).includes(secret), false);

        global.fetch = async () => {
            const err = new DOMException(`aborted ${secret}`, "AbortError");
            throw err;
        };
        const aborted = await searchAI("cabin");
        assert.equal(aborted.code, "ai_search_timeout");
        assert.equal(JSON.stringify(aborted).includes(secret), false);
    });
});
