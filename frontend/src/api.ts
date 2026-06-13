/**
 * 向後相容的入口檔。
 *
 * 真正的實作在 `frontend/src/api/` 目錄下；本檔僅 re-export，
 * 讓所有 `import { API } from "@/api"`（以及型別）的呼叫姿勢保持不變。
 */

export * from "./api/index";
