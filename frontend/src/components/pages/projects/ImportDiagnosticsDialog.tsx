import { ArchiveDiagnosticsDialog } from "@/components/shared/ArchiveDiagnosticsDialog";
import type { ImportFailureDiagnostics } from "@/types";

export function fallbackDiagnostics(error: {
  errors?: string[];
  warnings?: string[];
  diagnostics?: ImportFailureDiagnostics;
}): ImportFailureDiagnostics {
  if (error.diagnostics) {
    return error.diagnostics;
  }
  return {
    blocking: (error.errors ?? []).map((message) => ({
      code: "legacy_error",
      message,
    })),
    auto_fixable: [],
    warnings: (error.warnings ?? []).map((message) => ({
      code: "legacy_warning",
      message,
    })),
  };
}

export function ImportDiagnosticsDialogWrapper({
  diagnostics,
  onClose,
}: {
  diagnostics: ImportFailureDiagnostics;
  onClose: () => void;
}) {
  return (
    <ArchiveDiagnosticsDialog
      title="匯入診斷"
      description="匯入已完成預先檢查。以下問題會依嚴重程度分組顯示，在阻斷問題排除前不會繼續匯入。"
      sections={[
        { key: "blocking", title: "阻斷問題", tone: "border-red-400/25 bg-red-500/10 text-red-100", items: diagnostics.blocking },
        { key: "auto_fixable", title: "可自動修復", tone: "border-indigo-400/25 bg-indigo-500/10 text-indigo-100", items: diagnostics.auto_fixable },
        { key: "warnings", title: "警告", tone: "border-amber-400/25 bg-amber-500/10 text-amber-100", items: diagnostics.warnings },
      ]}
      onClose={onClose}
    />
  );
}
