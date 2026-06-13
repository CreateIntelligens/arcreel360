import type { StateCreator } from "zustand";
import type { AppState, WorkspaceCacheSlice } from "./app-store-types";

const ALL_ENTITIES_REVISION_KEY = "__all__";

export const createWorkspaceCacheSlice: StateCreator<
  AppState,
  [],
  [],
  WorkspaceCacheSlice
> = (set, get) => ({
  sourceFilesVersion: 0,
  invalidateSourceFiles: () =>
    set((state) => ({ sourceFilesVersion: state.sourceFilesVersion + 1 })),

  entityRevisions: {},
  invalidateEntities: (keys) =>
    set((state) => {
      const normalizedKeys = [...new Set(keys.filter(Boolean))];
      if (normalizedKeys.length === 0) {
        return state;
      }

      const entityRevisions = { ...state.entityRevisions };
      for (const key of normalizedKeys) {
        entityRevisions[key] = (entityRevisions[key] ?? 0) + 1;
      }
      return { entityRevisions };
    }),
  invalidateAllEntities: () =>
    set((state) => ({
      entityRevisions: {
        ...state.entityRevisions,
        [ALL_ENTITIES_REVISION_KEY]:
          (state.entityRevisions[ALL_ENTITIES_REVISION_KEY] ?? 0) + 1,
      },
    })),
  getEntityRevision: (key) => {
    const entityRevisions = get().entityRevisions;
    return (
      (entityRevisions[key] ?? 0) +
      (entityRevisions[ALL_ENTITIES_REVISION_KEY] ?? 0)
    );
  },
});
