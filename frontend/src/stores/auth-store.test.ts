import { beforeEach, describe, expect, it, vi } from "vitest";
import { API } from "@/api";
import { useAuthStore } from "@/stores/auth-store";
import { getToken } from "@/utils/auth";

describe("auth store", () => {
  beforeEach(() => {
    useAuthStore.setState(useAuthStore.getInitialState(), true);
    vi.restoreAllMocks();
  });

  it("logs in with credentials and centralizes token persistence", async () => {
    const token = "token-1";
    const loginSpy = vi
      .spyOn(API.auth, "login")
      .mockResolvedValue({ access_token: token, token_type: "bearer" });

    await useAuthStore.getState().login("alice", "secret");

    expect(loginSpy).toHaveBeenCalledWith("alice", "secret");
    expect(getToken()).toBe(token);
    expect(useAuthStore.getState()).toMatchObject({
      token,
      username: "alice",
      isAuthenticated: true,
      isLoading: false,
    });
  });
});
