import { revalidatePath, revalidateTag } from 'next/cache';

export const LIBRARY_LANDING_CACHE_TAG = 'library-landing';

/** Invalidate only the Library landing data and rendered page. */
export function revalidateLibraryLanding(): void {
  // Next 16 requires a profile. expire: 0 makes this an immediate purge,
  // rather than stale-while-revalidate, so the next request reads Flask.
  revalidateTag(LIBRARY_LANDING_CACHE_TAG, { expire: 0 });
  revalidatePath('/library', 'page');
}
