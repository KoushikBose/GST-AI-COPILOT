import { describe, expect, it } from "vitest";
import { getApiErrorMessage, isApiErrorBody } from "@/lib/api-client";

describe("API error helpers", () => {
  it("identifies the backend's standard error envelope", () => {
    expect(
      isApiErrorBody({
        success: false,
        error: {
          code: "DEPENDENCY_UNAVAILABLE",
          message: "The assistant is temporarily unavailable.",
          request_id: "request-123",
        },
      })
    ).toBe(true);
  });

  it("returns the backend error message used by chat", () => {
    const error = {
      isAxiosError: true,
      response: {
        data: {
          success: false,
          error: {
            code: "DEPENDENCY_UNAVAILABLE",
            message: "The assistant is temporarily unavailable.",
            request_id: "request-123",
          },
        },
      },
    };

    expect(getApiErrorMessage(error)).toBe("The assistant is temporarily unavailable.");
  });
});
