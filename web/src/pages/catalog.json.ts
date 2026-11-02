import { catalogJson, loadCatalog } from "../lib/catalog.mjs";

export async function GET() {
  return new Response(catalogJson(await loadCatalog()), { headers: { "Content-Type": "application/json" } });
}
