export const SOURCE_UPLOAD_ACCEPT = ".txt,.md,.doc,.docx";
export const SOURCE_UPLOAD_FORMAT_LABEL = ".txt / .md / .doc / .docx";

const SOURCE_UPLOAD_SUFFIXES = [".txt", ".md", ".doc", ".docx"] as const;
const PREPROCESS_SOURCE_SUFFIXES = [".txt", ".md", ".text", ".docx"] as const;

export function isSupportedSourceUploadFileName(fileName: string): boolean {
  const lower = fileName.toLowerCase();
  return SOURCE_UPLOAD_SUFFIXES.some((suffix) => lower.endsWith(suffix));
}

export function isPreprocessSourceFileName(fileName: string): boolean {
  const lower = fileName.toLowerCase();
  return fileName !== "_remaining.txt" && PREPROCESS_SOURCE_SUFFIXES.some((suffix) => lower.endsWith(suffix));
}
