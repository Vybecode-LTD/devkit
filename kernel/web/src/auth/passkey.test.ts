import { afterEach, describe, expect, it, vi } from "vitest";

import {
  PasskeyCancelled,
  creationOptions,
  fromBase64url,
  getPasskey,
  makePasskey,
  passkeysWork,
  requestOptions,
  toBase64url,
  type CreationOptions,
} from "./passkey";

const bytes = (...values: number[]) => new Uint8Array(values).buffer;

class FakeCredential {
  constructor(
    readonly id: string,
    readonly rawId: ArrayBuffer,
    readonly response: object,
  ) {}
}

afterEach(() => {
  vi.unstubAllGlobals();
});

function withCredentials(credentials: Partial<CredentialsContainer>) {
  vi.stubGlobal("PublicKeyCredential", FakeCredential);
  vi.stubGlobal("navigator", { credentials });
}

describe("base64url", () => {
  it("goes both ways, with and without padding, and never writes +, / or =", () => {
    for (const length of [0, 1, 2, 3, 31, 32]) {
      const made = new Uint8Array(length).map((_, at) => (at * 97 + 251) % 256);
      const text = toBase64url(made);
      expect(text).not.toMatch(/[+/=]/);
      expect(new Uint8Array(fromBase64url(text))).toEqual(made);
    }
    expect(toBase64url(bytes(0xfb, 0xff))).toBe("-_8");
  });

  it("reads a view's own bytes, not its whole buffer", () => {
    const whole = new Uint8Array([1, 2, 3, 4]);
    expect(toBase64url(whole.subarray(1, 3))).toBe(toBase64url(bytes(2, 3)));
  });
});

describe("the options", () => {
  it("turn a request's base64url into bytes and leave out what wasn't given", () => {
    const made = requestOptions({ challenge: "AQID", rpId: "site.test", allowCredentials: [{ id: "BAU", type: "public-key", transports: ["usb"] }], userVerification: "required" });
    expect(new Uint8Array(made.challenge as ArrayBuffer)).toEqual(new Uint8Array([1, 2, 3]));
    expect(made.rpId).toBe("site.test");
    expect(made.userVerification).toBe("required");
    const [allowed] = made.allowCredentials ?? [];
    expect(new Uint8Array(allowed?.id as ArrayBuffer)).toEqual(new Uint8Array([4, 5]));
    expect(allowed?.transports).toEqual(["usb"]);
    expect(Object.keys(requestOptions({ challenge: "AQID" }))).toEqual(["challenge"]);
  });

  it("turn a creation's user id, challenge and exclusions into bytes", () => {
    const given: CreationOptions = {
      rp: { name: "Site", id: "site.test" },
      user: { id: "CQo", name: "ann@site.test", displayName: "ann@site.test" },
      challenge: "AQID",
      pubKeyCredParams: [{ type: "public-key", alg: -7 }],
      excludeCredentials: [{ id: "BAU", type: "public-key" }],
      authenticatorSelection: { residentKey: "required", userVerification: "required", requireResidentKey: true },
      attestation: "none",
      timeout: 60_000,
    };
    const made = creationOptions(given);
    expect(made.rp).toEqual({ name: "Site", id: "site.test" });
    expect(new Uint8Array(made.user.id as ArrayBuffer)).toEqual(new Uint8Array([9, 10]));
    expect(made.pubKeyCredParams).toEqual([{ type: "public-key", alg: -7 }]);
    expect(made.excludeCredentials).toHaveLength(1);
    expect(made.authenticatorSelection).toEqual({ residentKey: "required", userVerification: "required", requireResidentKey: true });
    expect(made.attestation).toBe("none");
    expect(made.timeout).toBe(60_000);
  });
});

describe("asking the browser", () => {
  it("can't without WebAuthn", () => {
    vi.stubGlobal("PublicKeyCredential", undefined);
    expect(passkeysWork()).toBe(false);
  });

  it("gives an assertion back as the server reads it", async () => {
    const get = vi.fn(() =>
      Promise.resolve(
        new FakeCredential("id-1", bytes(1), {
          clientDataJSON: bytes(2),
          authenticatorData: bytes(3),
          signature: bytes(4),
          userHandle: bytes(5),
        }),
      ),
    );
    withCredentials({ get } as unknown as CredentialsContainer);
    expect(passkeysWork()).toBe(true);
    const sent = await getPasskey({ challenge: "AQID" });
    expect(sent).toEqual({
      id: "id-1",
      rawId: "AQ",
      type: "public-key",
      response: { clientDataJSON: "Ag", authenticatorData: "Aw", signature: "BA", userHandle: "BQ" },
    });
  });

  it("gives a new passkey back with its transports", async () => {
    const create = vi.fn(() =>
      Promise.resolve(new FakeCredential("id-2", bytes(6), { clientDataJSON: bytes(7), attestationObject: bytes(8), getTransports: () => ["internal"] })),
    );
    withCredentials({ create } as unknown as CredentialsContainer);
    const made = await makePasskey({
      rp: { name: "Site" },
      user: { id: "AQ", name: "a", displayName: "a" },
      challenge: "AQID",
      pubKeyCredParams: [{ type: "public-key", alg: -7 }],
    });
    expect(made.response).toEqual({ clientDataJSON: "Bw", attestationObject: "CA", transports: ["internal"] });
  });

  it("calls a closed prompt or one already open a cancel, and lets anything else through", async () => {
    for (const name of ["NotAllowedError", "AbortError"]) {
      withCredentials({ get: () => Promise.reject(new DOMException("No", name)) });
      await expect(getPasskey({ challenge: "AQID" })).rejects.toBeInstanceOf(PasskeyCancelled);
    }
    withCredentials({ get: () => Promise.reject(new DOMException("Bad", "SecurityError")) });
    await expect(getPasskey({ challenge: "AQID" })).rejects.toMatchObject({ name: "SecurityError" });
    withCredentials({ create: () => Promise.resolve(null) });
    await expect(
      makePasskey({ rp: { name: "S" }, user: { id: "AQ", name: "a", displayName: "a" }, challenge: "AQ", pubKeyCredParams: [] }),
    ).rejects.toBeInstanceOf(PasskeyCancelled);
  });
});
