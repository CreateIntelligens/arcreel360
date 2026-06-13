## Why

当前前端已经存在深色工作台基础，但视觉语言分裂为三套来源：全局 token、遗留 CSS 主题、组件内写死的灰阶与 indigo 颜色。结果是页面虽然可用，却长期处于“管理后台风格 + 半成品暗色皮肤”的状态，无法传达小说转视频工作台应有的创作感、专注感与信息层级。

现在正适合统一这件事，因为系统配置页、项目大厅、工作区外壳都已经具备相对稳定的信息架构。与其继续逐页补颜色，不如一次建立产品级视觉基线，把界面收敛到“石板蓝黑底 + 冷白文字 + 雾蓝灰层级 + 节制的蓝青高亮 + 橙红状态色”的创作型工作台表达。

## What Changes

- 建立统一的创作型工作台视觉语言，收敛現有分裂的颜色、边框、阴影、排版与交互状态定义
- 以 TokyoNight Storm 为参考，提炼而非照搬编辑器主题，形成适用于产品界面的背景层级、文字层级、强调色与状态色规则
- 重构全局壳层的视觉层级，包括项目大厅、工作区头部、三栏工作台外壳与系统配置页，让主要信息、操作入口与状态反馈更清晰
- 调整设置页与高密度表单页的阅读节奏，减少“整页一层灰卡片堆叠”的后台感，改为更明确的摘要区、控制区、警示区与进阶区
- 将颜色与表面规则沉淀到可复用 token / utility 层，减少组件内部继续写死 `gray-*` / `indigo-*` 造成的风格漂移

## Capabilities

### New Capabilities
- `creative-workbench-theme`: 定义 ArcReel 创作型工作台的统一视觉 token、颜色语义、字体策略、表面层级与交互状态规则
- `studio-shell-visual-refresh`: 定义项目大厅、全局头部、工作区三栏外壳与关键入口页的视觉层级、信息聚焦与高质感暗色工作台表达

### Modified Capabilities
- `system-config-ui`: 将系统配置页从普通 CRUD 后台样式升级为工作台内设置中心，强化警告、导航、分区与表单密度的可读性

## Impact

- **前端主题入口**：`frontend/src/index.css`、`frontend/src/css/app.css`、`frontend/src/css/styles.css`
- **工作区外壳**：`frontend/src/components/layout/StudioLayout.tsx`、`frontend/src/components/layout/GlobalHeader.tsx`、`frontend/src/components/layout/AssetSidebar.tsx`
- **项目大厅**：`frontend/src/components/pages/ProjectsPage.tsx`、相关卡片与模态组件
- **设置中心**：`frontend/src/components/pages/SystemConfigPage.tsx`、`frontend/src/components/pages/AgentConfigTab.tsx`、`frontend/src/components/pages/ProviderSection.tsx` 及其子组件
- **设计一致性影响**：后续新增页面与组件将以统一 token / surface 规则为基础，减少局部写死样式的维护成本
- **非目标**：本次变更不改动后端 API 语义，不以新增业务功能为目标，而是聚焦视觉语言、信息清晰度与工作台体验升级