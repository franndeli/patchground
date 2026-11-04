import { SlidingWindowRateLimiter } from "./rate-limiter.js";

export type GateResponse = Readonly<{
  status: 200 | 429;
  headers: Readonly<{ "x-quota-remaining": string }>;
}>;

export function gateRequest(
  limiter: SlidingWindowRateLimiter,
  clientId: string,
): GateResponse {
  const decision = limiter.check(clientId);
  return {
    status: decision.allowed ? 200 : 429,
    headers: { "x-quota-remaining": String(decision.remaining) },
  };
}
