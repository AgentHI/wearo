export function normalizeGalleryResponse(result) {
  const items = Array.isArray(result?.items) ? result.items : [];
  const queue = Array.isArray(result?.queue) ? result.queue : [];
  const rawCount = Number(result?.saved_look_count);
  const hasBackendCount = Object.hasOwn(result || {}, "saved_look_count")
    && Number.isInteger(rawCount)
    && rawCount >= 0;
  return {
    items,
    queue,
    savedLookCount: hasBackendCount && !(rawCount === 0 && items.length > 0) ? rawCount : null,
    page: Number.isInteger(Number(result?.page)) ? Number(result.page) : 1,
    hasNext: result?.has_next === true,
  };
}
