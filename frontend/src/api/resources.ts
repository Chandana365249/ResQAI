import { requestJson } from "./http";
import type { ResourceCatalogResponse, ResourceFilters } from "./types";

export function getResources(filters: ResourceFilters = {}, signal?: AbortSignal): Promise<ResourceCatalogResponse> {
  return requestJson<ResourceCatalogResponse>("/resources", { query: { ...filters }, signal });
}
