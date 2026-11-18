/**
 * An answer that isn't a success, as the kernel sends it: RFC 9457 problem
 * details with a stable `code` (SPEC.md section 7). Every call through the
 * client that doesn't succeed throws one, so a screen reads `problem.code`,
 * never a status or a message.
 */
export type ProblemBody = {
  type: string;
  title: string;
  status: number;
  detail: string;
  code: string;
  errors?: Record<string, string[]>;
  [member: string]: unknown;
};

const MEMBERS = new Set(["type", "title", "status", "detail", "code", "errors"]);
const TYPE_PREFIX = "urn:mechframe:problem:";

function isProblem(body: unknown): body is Record<string, unknown> & {
  code: string;
  status: number;
  title: string;
} {
  if (typeof body !== "object" || body === null || Array.isArray(body)) return false;
  const found = body as Record<string, unknown>;
  return (
    typeof found.code === "string" &&
    typeof found.status === "number" &&
    typeof found.title === "string"
  );
}

/** Field errors as the types say they are: lists of strings, by path. Any
 * other entry is dropped, so a form can always `.join()` what it shows
 * (CodeRabbit on #78). */
function fieldErrors(given: unknown): Record<string, string[]> {
  if (typeof given !== "object" || given === null || Array.isArray(given)) return {};
  return Object.fromEntries(
    Object.entries(given).filter(
      (entry): entry is [string, string[]] =>
        Array.isArray(entry[1]) && entry[1].every((message) => typeof message === "string"),
    ),
  );
}

export class ApiProblem extends Error {
  readonly type: string;
  readonly title: string;
  readonly status: number;
  readonly detail: string;
  readonly code: string;
  /** Field errors by dotted path, such as `body.email`. */
  readonly errors: Readonly<Record<string, string[]>>;
  /** Members the kernel adds to some problems, such as `retry_after`. */
  readonly extra: Readonly<Record<string, unknown>>;

  constructor(body: ProblemBody) {
    super(body.detail || body.title || body.code);
    this.name = "ApiProblem";
    this.type = body.type;
    this.title = body.title;
    this.status = body.status;
    this.detail = body.detail;
    this.code = body.code;
    this.errors = body.errors ?? {};
    this.extra = Object.fromEntries(Object.entries(body).filter(([key]) => !MEMBERS.has(key)));
  }

  /** The problem a response carries; one that carries none becomes `kernel.unexpected_answer`. */
  static async from(response: Response): Promise<ApiProblem> {
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    if (isProblem(body)) {
      return new ApiProblem({
        ...body,
        type: typeof body.type === "string" ? body.type : TYPE_PREFIX + body.code,
        detail: typeof body.detail === "string" ? body.detail : "",
        errors: fieldErrors(body.errors),
      });
    }
    return ApiProblem.made("kernel.unexpected_answer", response.status, response.statusText);
  }

  /** The site couldn't be reached at all: status 0. */
  static unreachable(): ApiProblem {
    return ApiProblem.made("kernel.unreachable", 0, "The site couldn't be reached");
  }

  private static made(code: string, status: number, title: string): ApiProblem {
    return new ApiProblem({
      type: TYPE_PREFIX + code,
      title: title || "Unexpected answer",
      status,
      detail: "",
      code,
    });
  }
}
