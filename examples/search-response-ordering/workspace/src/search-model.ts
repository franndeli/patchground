export type SearchTransport = (query: string) => Promise<string[]>;

export type SearchState =
  | {
      readonly kind: "idle";
      readonly query: "";
      readonly results: readonly string[];
      readonly error: null;
    }
  | {
      readonly kind: "loading" | "ready";
      readonly query: string;
      readonly results: readonly string[];
      readonly error: null;
    }
  | {
      readonly kind: "error";
      readonly query: string;
      readonly results: readonly string[];
      readonly error: string;
    };

export class SearchModel {
  private state: SearchState = {
    kind: "idle", query: "", results: [], error: null,
  };
  private disposed = false;

  constructor(private readonly transport: SearchTransport) {}

  get_state(): SearchState {
    return this.state;
  }

  async search(input: string): Promise<void> {
    if (this.disposed) return;
    const query = input.trim();
    if (!query) {
      this.state = { kind: "idle", query: "", results: [], error: null };
      return;
    }
    this.state = { kind: "loading", query, results: [], error: null };
    try {
      const results = await this.transport(query);
      this.state = { kind: "ready", query, results: [...results], error: null };
    } catch (error: unknown) {
      this.state = {
        kind: "error",
        query,
        results: [],
        error: error instanceof Error ? error.message : "Search failed",
      };
    }
  }

  dispose(): void {
    this.disposed = true;
  }
}
