import { useState } from "react";
import { useLocation } from "wouter";
import { useAuthStore } from "@/stores/auth-store";

export function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [, setLocation] = useLocation();
  const loginWithCredentials = useAuthStore((s) => s.login);

  const handleSubmit = async () => {
    setError("");
    setLoading(true);

    try {
      await loginWithCredentials(username, password);
      setLocation("/app/projects");
    } catch (err) {
      setError(err instanceof Error ? err.message : "登入失敗");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-950">
      <div className="w-full max-w-sm rounded-xl border border-gray-800 bg-gray-900 p-8 shadow-2xl">
        <h1 className="mb-6 flex items-center justify-center gap-2 text-xl font-semibold text-gray-100">
          <img src="/android-chrome-192x192.png" alt="ArcReel" className="h-7 w-7" />
          <span>ArcReel</span>
        </h1>

        <form action={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm text-gray-400">使用者名稱</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-gray-100 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
              autoFocus
              required
            />
          </div>

          <div>
            <label className="mb-1 block text-sm text-gray-400">密碼</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-gray-100 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
              required
            />
          </div>

          {error && (
            <p className="text-sm text-red-400">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-indigo-600 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:opacity-50"
          >
            {loading ? "登入中..." : "登入"}
          </button>
        </form>
      </div>
    </div>
  );
}
