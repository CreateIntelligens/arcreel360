/**
 * API 統一入口。
 *
 * 對外提供與舊版 `frontend/src/api.ts` 完全相同的介面：
 *
 * ```ts
 * import { API, type VersionInfo, ... } from "@/api";
 * ```
 *
 * 內部結構：
 * - `_http.ts` 集中放置 fetch wrapper、Authorization、錯誤處理。
 * - `types.ts` 集中放置 helper type（VersionInfo、TaskStreamOptions...）。
 * - 各 domain module (`projects.ts`、`tasks.ts`...) export mixin 物件，
 *   每個 method 都用 `function (this: ApiThis, ...)` 形式，
 *   並透過 `this.request(...)` 呼叫共用 HTTP layer。
 * - 本檔以 `Object.assign` 將多數 mixin 掛載成 `class API` 的 static method；
 *   auth 這類需要獨立命名空間的 domain 則掛在 `API.auth`。
 *   如此一來：
 *     1. `vi.spyOn(API, "request")` 能影響所有 domain method（測試相容）。
 *     2. 外部 `API.xxx()` 呼叫姿勢完全不變。
 */

import { request, setApi } from "./_http";
import { apiKeysApi } from "./api-keys";
import { assistantApi } from "./assistant";
import { authApi } from "./auth";
import { costApi } from "./cost";
import { credentialsApi } from "./credentials";
import { customProvidersApi } from "./custom-providers";
import { episodesApi } from "./episodes";
import { filesApi } from "./files";
import { projectEventsApi } from "./project-events";
import { projectsApi } from "./projects";
import { providersApi } from "./providers";
import { systemApi } from "./system";
import { tasksApi } from "./tasks";
import { usageApi } from "./usage";
import { versionsApi } from "./versions";

// ==================== Re-export types（外部 `import type { ... } from "@/api"` 沿用） ====================

export type {
  ApiThis,
  DraftInfo,
  EpisodeSplitBreakpoint,
  EpisodeSplitPeekResponse,
  EpisodeSplitResponse,
  ProjectEventStreamOptions,
  SuccessResponse,
  TaskCancelAllPreviewResponse,
  TaskCancelPreviewItem,
  TaskCancelPreviewResponse,
  TaskListFilters,
  TaskStreamOptions,
  TaskStreamSnapshotPayload,
  TaskStreamTaskPayload,
  UsageCallsFilters,
  UsageStatsFilters,
  VersionInfo,
} from "./types";

export type { PreprocessRefs } from "./episodes";

export { ApiError } from "./_http";
export type { ApiErrorCode } from "./_http";

// ==================== Mixin 列表 ====================

const apiMixins = [
  systemApi,
  projectsApi,
  episodesApi,
  filesApi,
  tasksApi,
  projectEventsApi,
  versionsApi,
  assistantApi,
  usageApi,
  costApi,
  apiKeysApi,
  providersApi,
  credentialsApi,
  customProvidersApi,
] as const;

// ==================== `API` class（與舊版相容） ====================

class API {
  /**
   * 通用請求方法。
   * domain mixin 內透過 `this.request(...)` 取得；
   * 測試會 `vi.spyOn(API, "request")` 來攔截。
   */
  static request = request;
  static auth = authApi;
}

// 把所有 mixin 的 method 平鋪掛到 `API` class 上。
for (const mixin of apiMixins) {
  Object.assign(API, mixin);
}

// 將組裝好的 `API` 註冊到 _http，讓 domain 模組的 `getApi().request(...)` 能透過 `API.request`，
// 進而被 `vi.spyOn(API, "request")` 攔截。
setApi(API as unknown as { request: typeof request });

// ==================== 型別合成：讓 `API.xxx` 在 TypeScript 中可見 ====================

type Mixins =
  & typeof systemApi
  & typeof projectsApi
  & typeof episodesApi
  & typeof filesApi
  & typeof tasksApi
  & typeof projectEventsApi
  & typeof versionsApi
  & typeof assistantApi
  & typeof usageApi
  & typeof costApi
  & typeof apiKeysApi
  & typeof providersApi
  & typeof credentialsApi
  & typeof customProvidersApi;

// 強制將合成型別套到 API class 自身：
// 1. 對外仍以 `class API` 暴露（保留 named export 行為）。
// 2. 透過交叉型別，使所有 domain method 都成為 `API.xxx` 可呼叫的 static method。
const TypedAPI = API as typeof API & Mixins;

export { TypedAPI as API };
