/**
 * Passkeys in the browser (decision 0028; docs/contracts/auth-api.md,
 * "Passkeys"). The server's options are WebAuthn's JSON, bytes in base64url;
 * the browser's API takes and gives `ArrayBuffer`s. These turn one into the
 * other, and send back only the fields the server reads.
 *
 * `passkeysWork()` says whether this browser can make or use one at all;
 * a screen hides its passkey buttons when it can't. A person who closes the
 * browser's own prompt gets `PasskeyCancelled`, which a screen meets with
 * nothing said: they chose not to.
 */
import type { components } from "../api/schema";

type Schemas = components["schemas"];
export type RequestOptions = Schemas["RequestOptions"];
export type CreationOptions = Schemas["CreationOptions"];
export type AssertionCredential = Schemas["AssertionCredential"];
export type RegistrationCredential = Schemas["RegistrationCredential"];

/** The person closed the browser's prompt, or it timed out: nothing to tell them. */
export class PasskeyCancelled extends Error {
  constructor() {
    super("The passkey prompt was closed.");
    this.name = "PasskeyCancelled";
  }
}

export function passkeysWork(): boolean {
  return typeof window !== "undefined" && typeof window.PublicKeyCredential === "function" && Boolean(navigator.credentials);
}

export function fromBase64url(text: string): ArrayBuffer {
  const base64 = text.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(text.length / 4) * 4, "=");
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let at = 0; at < binary.length; at += 1) bytes[at] = binary.charCodeAt(at);
  return bytes.buffer;
}

export function toBase64url(buffer: ArrayBuffer | ArrayBufferView): string {
  const bytes = buffer instanceof ArrayBuffer ? new Uint8Array(buffer) : new Uint8Array(buffer.buffer, buffer.byteOffset, buffer.byteLength);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

type Descriptor = Schemas["CredentialDescriptor"];

function descriptor(given: Descriptor): PublicKeyCredentialDescriptor {
  return {
    type: "public-key",
    id: fromBase64url(given.id),
    ...(given.transports ? { transports: given.transports as AuthenticatorTransport[] } : {}),
  };
}

/** A closed prompt or a timeout (NotAllowedError), or one already open (AbortError): the person's call. */
function cancelled(error: unknown): boolean {
  return error instanceof DOMException && (error.name === "NotAllowedError" || error.name === "AbortError");
}

export function requestOptions(given: RequestOptions): PublicKeyCredentialRequestOptions {
  return {
    challenge: fromBase64url(given.challenge),
    ...(given.timeout ? { timeout: given.timeout } : {}),
    ...(given.rpId ? { rpId: given.rpId } : {}),
    ...(given.allowCredentials ? { allowCredentials: given.allowCredentials.map(descriptor) } : {}),
    ...(given.userVerification ? { userVerification: given.userVerification as UserVerificationRequirement } : {}),
  };
}

export function creationOptions(given: CreationOptions): PublicKeyCredentialCreationOptions {
  const selection = given.authenticatorSelection;
  return {
    rp: { name: given.rp.name, ...(given.rp.id ? { id: given.rp.id } : {}) },
    user: { id: fromBase64url(given.user.id), name: given.user.name, displayName: given.user.displayName },
    challenge: fromBase64url(given.challenge),
    pubKeyCredParams: given.pubKeyCredParams.map((param) => ({ type: "public-key", alg: param.alg })),
    ...(given.timeout ? { timeout: given.timeout } : {}),
    ...(given.excludeCredentials ? { excludeCredentials: given.excludeCredentials.map(descriptor) } : {}),
    ...(selection
      ? {
          authenticatorSelection: {
            ...(selection.authenticatorAttachment ? { authenticatorAttachment: selection.authenticatorAttachment as AuthenticatorAttachment } : {}),
            ...(selection.residentKey ? { residentKey: selection.residentKey as ResidentKeyRequirement } : {}),
            ...(selection.requireResidentKey !== undefined && selection.requireResidentKey !== null
              ? { requireResidentKey: selection.requireResidentKey }
              : {}),
            ...(selection.userVerification ? { userVerification: selection.userVerification as UserVerificationRequirement } : {}),
          },
        }
      : {}),
    ...(given.attestation ? { attestation: given.attestation as AttestationConveyancePreference } : {}),
  };
}

/** Asks the browser for a passkey the options allow, and gives it as the server reads it. */
export async function getPasskey(given: RequestOptions): Promise<AssertionCredential> {
  let found: Credential | null;
  try {
    found = await navigator.credentials.get({ publicKey: requestOptions(given) });
  } catch (error) {
    if (cancelled(error)) throw new PasskeyCancelled();
    throw error;
  }
  if (!(found instanceof PublicKeyCredential)) throw new PasskeyCancelled();
  const response = found.response as AuthenticatorAssertionResponse;
  return {
    id: found.id,
    rawId: toBase64url(found.rawId),
    type: "public-key",
    response: {
      clientDataJSON: toBase64url(response.clientDataJSON),
      authenticatorData: toBase64url(response.authenticatorData),
      signature: toBase64url(response.signature),
      userHandle: response.userHandle ? toBase64url(response.userHandle) : null,
    },
  };
}

/** Asks the browser to make a passkey, and gives it as the server reads it. */
export async function makePasskey(given: CreationOptions): Promise<RegistrationCredential> {
  let made: Credential | null;
  try {
    made = await navigator.credentials.create({ publicKey: creationOptions(given) });
  } catch (error) {
    if (cancelled(error)) throw new PasskeyCancelled();
    throw error;
  }
  if (!(made instanceof PublicKeyCredential)) throw new PasskeyCancelled();
  const response = made.response as AuthenticatorAttestationResponse;
  return {
    id: made.id,
    rawId: toBase64url(made.rawId),
    type: "public-key",
    response: {
      clientDataJSON: toBase64url(response.clientDataJSON),
      attestationObject: toBase64url(response.attestationObject),
      transports: typeof response.getTransports === "function" ? response.getTransports() : [],
    },
  };
}
