---
name: release
description: 项目发版流程：询问版本步进类型，更新前后端版本号，锁定依赖，提交、打 tag 并推送。当用户提到"发版"、"release"、"bump version"、"升版本"、"打 tag"、"发布新版本"时使用此 skill。
---

# Release — 项目发版

## 流程

### 1. 确认版本步进

读取当前版本号（`pyproject.toml` 第 3 行），然后询问用户想要哪种步进：

- **patch** (x.y.Z) — bug 修复、小调整
- **minor** (x.Y.0) — 新功能
- **major** (X.0.0) — 重大变更

展示当前版本和各步进后的结果，让用户确认。

### 2. 更新版本号

同时修改两個文件（版本号始终保持一致）：

| 文件 | 位置 | 格式 |
|------|------|------|
| `pyproject.toml` | 第 3 行 | `version = "X.Y.Z"` |
| `frontend/package.json` | 第 3 行 | `"version": "X.Y.Z",` |

### 3. 锁定依赖

```bash
uv lock
```

这会自动同步 `uv.lock` 中 arcreel 包的版本号。

### 4. 提交

将三個文件（`pyproject.toml`、`frontend/package.json`、`uv.lock`）加入暂存区并提交：

```
chore: bump version to X.Y.Z
```

注意：commit message 中版本号不带 `v` 前缀。

### 5. 打 Tag

```bash
git tag vX.Y.Z
```

Tag 名称带 `v` 前缀。

### 6. 推送

推送 commit 和 tag：

```bash
git push origin main && git push origin vX.Y.Z
```

推送前需确认用户同意。
