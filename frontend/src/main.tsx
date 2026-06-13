// main.tsx — New entry point using wouter + StudioLayout
// Replaces main.js as the application entry point.
// The old main.js is kept as a reference during the migration.

import { createRoot } from "react-dom/client";
import { AppRoutes } from "./router";
import { useAuthStore } from "@/stores/auth-store";

import "./index.css";
import "./css/styles.css";
import "./css/app.css";
import "./css/studio.css";

// 從 localStorage 恢復登入狀態
useAuthStore.getState().initialize();

// ---------------------------------------------------------------------------
// 全域性捲軸 auto-hide：滾動時漸顯、停止 1.2s 後漸隱
// ---------------------------------------------------------------------------
{
  const timers = new WeakMap<Element, ReturnType<typeof setTimeout>>();

  document.addEventListener(
    "scroll",
    (e) => {
      const el = e.target;
      if (!(el instanceof HTMLElement)) return;

      // 顯示捲軸
      el.dataset.scrolling = "";

      // 清除上一次的隱藏定時器
      const prev = timers.get(el);
      if (prev) clearTimeout(prev);

      // 1.2s 無滾動後隱藏
      timers.set(
        el,
        setTimeout(() => {
          delete el.dataset.scrolling;
          timers.delete(el);
        }, 1200),
      );
    },
    true, // capture phase — 捕獲所有子元素的 scroll 事件
  );
}

const root = document.getElementById("app-root");
if (root) {
  createRoot(root).render(<AppRoutes />);
}
