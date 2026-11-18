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

function isProblem(body: unknown): body is ProblemBody {
  if (typeof body !== "object" || body === null) return false;
  const found = body as Record<string, unknown>;
  return (
    typeof found.code === "string" &&
    typeof found.status === "number" &&
    typeof found.title === "string"
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
      return new ApiProblem({ ...body, detail: typeof body.detail === "string" ? body.detail : "" });
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
