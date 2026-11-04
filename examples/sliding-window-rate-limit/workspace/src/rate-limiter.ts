export type Clock = () => number;

export type Decision = Readonly<{
  allowed: boolean;
  remaining: number;
}>;

export type LimiterOptions = Readonly<{
  capacity: number;
  windowMs: number;
  clock: Clock;
}>;

export class SlidingWindowRateLimiter {
  private readonly history = new Map<string, number[]>();
  private readonly capacity: number;
  private readonly windowMs: number;
  private readonly clock: Clock;

  constructor({ capacity, windowMs, clock }: LimiterOptions) {
    if (!Number.isInteger(capacity) || capacity <= 0) {
      throw new RangeError("capacity must be a positive integer");
    }
    if (!Number.isInteger(windowMs) || windowMs <= 0) {
      throw new RangeError("windowMs must be a positive integer");
    }
    this.capacity = capacity;
    this.windowMs = windowMs;
    this.clock = clock;
  }

  check(clientId: string): Decision {
    throw new Error("Implement the rolling admission policy");
  }

  cleanup(): number {
    throw new Error("Implement idle-history cleanup");
  }
}
