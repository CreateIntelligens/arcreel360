## ADDED Requirements

### Requirement: 分镜时长可交互切换

SegmentCard 头部的时长展示元素 SHALL 支持用户点击后弹出選择器，在 4s、6s、8s 三個選項之间切换，選中后通过 `onUpdatePrompt` 回调将新值写入后端，并在保存完成后刷新剧集总时长。

#### Scenario: 点击时长徽章弹出選择器

- **WHEN** 用户点击 SegmentCard 头部的时长徽章（如"4s"）
- **THEN** 弹出 Popover，列出"4s"、"6s"、"8s"三個按钮，当前值高亮显示

#### Scenario: 選择新时长并保存

- **WHEN** 用户在弹出的選择器中点击某個时长選項（如"6s"）
- **THEN** Popover 关闭，时长徽章立即显示新值"6s"，并通过 `onUpdatePrompt(segmentId, "duration_seconds", 6)` 触发后端保存

#### Scenario: 取消選择

- **WHEN** 用户点击 Popover 以外区域
- **THEN** Popover 关闭，时长徽章保持原值不变

#### Scenario: 无 onUpdatePrompt 时只读

- **WHEN** SegmentCard 未提供 `onUpdatePrompt` prop（只读模式）
- **THEN** 时长徽章不可点击，外观与只读状态一致（无 hover 效果）

### Requirement: 剧集总时长联动更新

TimelineCanvas 头部显示的总时长 SHALL 在任意分镜时长变更并刷新项目数据后自动更新，无需额外操作。

#### Scenario: 修改分镜时长后总时长更新

- **WHEN** 用户修改某分镜时长，后端保存成功，`refreshProject()` 完成
- **THEN** TimelineCanvas 头部显示的总时长重新从所有分镜的 `duration_seconds` 求和，反映最新值
