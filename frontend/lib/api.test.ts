import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "./api";

afterEach(() => vi.unstubAllGlobals());

function respond(status: number, body: unknown) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })));
}

describe("api", () => {
  it("prefixes /api, sends credentials and returns JSON", async () => {
    respond(200, { status: "ok" });
    await expect(api("/health")).resolves.toEqual({ status: "ok" });
    const [url, init] = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe("/api/health");
    expect(init.credentials).toBe("include");
  });

  it("turns the error envelope into an ApiError", async () => {
    respond(409, { error: { code: "META_NOT_CONNECTED", message: "Connect first", details: { a: 1 } } });
    const error = (await api("/meta/assets").catch((e) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect([error.status, error.code, error.message]).toEqual([409, "META_NOT_CONNECTED", "Connect first"]);
  });

  it("returns undefined for 204", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    await expect(api("/auth/logout", { method: "POST" })).resolves.toBeUndefined();
  });
});
