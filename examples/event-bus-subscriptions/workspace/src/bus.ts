/** A small synchronous in-process event bus used by a command-line tool. */

export type Handler = (payload: unknown) => void;
export type Unsubscribe = () => void;

export class EventBus {
  private readonly handlers = new Map<string, Handler[]>();

  /** Register `handler` for exactly `topic`. Handlers run in registration order. */
  on(topic: string, handler: Handler): Unsubscribe {
    const list = this.handlers.get(topic) ?? [];
    list.push(handler);
    this.handlers.set(topic, list);
    // Not implemented yet: there is no way to take a subscription back.
    return () => {};
  }

  /** Not implemented yet. */
  once(_topic: string, _handler: Handler): Unsubscribe {
    throw new Error("EventBus.once is not implemented");
  }

  /** Call every handler registered for `topic` and return how many were called. */
  emit(topic: string, payload?: unknown): number {
    let called = 0;
    for (const handler of this.handlers.get(topic) ?? []) {
      handler(payload);
      called += 1;
    }
    return called;
  }
}
