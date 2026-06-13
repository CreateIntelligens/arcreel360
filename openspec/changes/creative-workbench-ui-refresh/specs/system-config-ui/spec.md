## ADDED Requirements

### Requirement: 设置页必须呈现工作台内设置中心层级

设置页 MUST 将页面摘要、全局警示、分区导航、主要设置内容和辅助说明区分为清晰层级，而不是将所有内容以相同密度的深色卡片连续堆叠。

#### Scenario: 用户进入设置页
- **WHEN** 用户打开系统配置页
- **THEN** 页面 MUST 清晰区分头部摘要区、导航区、警示区和主要配置区，用户应能快速判断当前页面重点与下一步动作

#### Scenario: 页面存在多個设置分区
- **WHEN** 页面同时展示多個配置分区
- **THEN** 每個分区 MUST 通过表面层级、间距和标题层级形成清晰分隔，不能仅依赖同色边框区分

### Requirement: 高密度表单必须改善阅读节奏

设置页中的高密度表单 MUST 区分字段标签、字段说明、当前值提示、状态提示与危险操作，让用户在不逐行细读的情况下完成扫描。

#### Scenario: 表单字段存在说明与当前值
- **WHEN** 一個字段同时展示标签、说明文案和当前已保存值
- **THEN** 这三类信息 MUST 使用不同层级的文字或布局表达，避免合并为同层文字块

#### Scenario: 同一区域存在危险操作
- **WHEN** 页面允许清除已保存值或执行具有破坏性的动作
- **THEN** 危险操作 MUST 与普通编辑行为区分开，并使用危险状态语义表达

## MODIFIED Requirements

### Requirement: 必填配置缺失时设置页内警告

当系统必填配置不完整时，设置页 SHALL 在导航上方显示工作台内警告横幅，逐条列出缺失原因，并提供快捷跳转到对应分区的入口。警告文案 MUST 与当前 assistant provider 语义一致，且不得把 Claude 或 Anthropic 凭证状态单独视为必须提示的全局警告。

#### Scenario: Claude provider 未配置 Anthropc key
- **WHEN** 用户进入设置页，且当前 `assistant_provider = "claude"`，同时 `anthropic_api_key.is_set === false`
- **THEN** 警告横幅 SHALL NOT 仅因缺少 Anthropic key 而新增一条 Claude 凭证警告

#### Scenario: Gemini Lite 所需文本供应商未就绪
- **WHEN** 当前 `assistant_provider = "gemini-lite"`，且没有可用的 Gemini 文本供应商
- **THEN** 警告横幅 SHALL 包含一条“Gemini 智能体未配置可用的 Gemini 文本供应商”，并链接到供应商分区

#### Scenario: OpenAI Lite 所需文本供应商未就绪
- **WHEN** 当前 `assistant_provider = "openai-lite"`，且没有可用的 OpenAI 文本供应商
- **THEN** 警告横幅 SHALL 包含一条“OpenAI / ChatGPT 智能体未配置可用的 OpenAI 文本供应商”，并链接到供应商分区

#### Scenario: 警告横幅采用工作台状态层级
- **WHEN** 设置页展示缺失配置警告
- **THEN** 警告横幅 MUST 通过独立的状态色、边界与文字层级与普通表单内容区分，且不得与页面背景融为一层

#### Scenario: 所有必填配置均已完成
- **WHEN** 系统必填配置均已配置
- **THEN** 设置页 SHALL 不显示警告横幅