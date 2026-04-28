import { authApi } from "./api";

export async function loginResponseExposesBackendTokenContract() {
  const result = await authApi.login("local", "alice", "secret");
  const token: string = result.access_token;
  const tokenType: "bearer" = result.token_type;
  return { token, tokenType, expiresAt: result.expires_at };
}
