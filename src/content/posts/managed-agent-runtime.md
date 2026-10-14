---
title: 'Managed Agent Runtime：Session、Harness 与执行环境怎样托管？'
description: '以 OpenAI Agents API 为例，理解托管 Harness 怎样组织长期 Session、上下文和子任务，区分执行环境与会话状态，并分析 Agents SDK 与托管 API 的职责边界。'
pubDate: 2026-10-14T19:45:10+08:00
category: notes
tags: [Agent, OpenAI, Runtime, Infrastructure, 学习笔记]
draft: false
postType: metaOnly
---

[上一篇](/zh-cn/posts/agent-infrastructure-sdk/)讨论了应用怎样通过 SDK 组合 Harness、Sandbox 与 Workspace。组件可以复用以后，应用仍要运行 Harness，处理会话接续、执行恢复和环境生命周期。另一种组织方式，是把 Harness 本身也交给平台运行。

OpenAI 在[《Introducing the Agents API》](https://openai.com/index/introducing-the-agents-api/)中介绍的正是这层托管能力。本文先分清应用、托管 Harness 与执行环境的职责，再看 Session 怎样持续工作、平台怎样处理上下文和子任务，最后比较环境选择、产物保存，以及 SDK 与 API 的区别。

继续使用假设的 CSV 修复任务：Agent 需要读取源码和样本、修改解析器、运行测试，并交出补丁。用户还可能在完成一轮后补充“再检查一下旧格式的兼容性”。这要求系统不仅能完成一次执行，还要保存足够的工作背景，让后续任务接得上。

## 一、托管 API 怎样组织 Agent 运行

### 1. Managed Harness：由平台运行模型与工具循环

使用模型 API 时，应用拿到一次输出后，通常还需要判断是否执行工具、怎样回传结果，以及什么时候继续调用模型。SDK 可以提供这些运行机制，但 Harness 仍在开发者自己的应用中运行。

Agents API 将这层运行职责放到 OpenAI：平台运行 Codex Harness，组织模型调用、工具使用与会话管理。应用通过 API 提交工作、接收进展，并提供任务所需的工具和环境。[来源：Agents API Overview](https://developers.openai.com/api/docs/guides/agents-api/overview)

对 CSV 任务来说，应用不必亲自推动每一次“读文件 → 看结果 → 改代码 → 再测试”的循环，但仍需告诉 Agent 修什么、允许改哪里，以及什么结果才算完成。

因此，这里的托管不是把业务需求变成平台的责任，而是把通用执行机制交给平台。**运行一套 Harness，与定义一个值得执行的任务，是两种不同的工作。**

### 2. Agent、Environment 与 Session：配置和运行实例

看创建请求时，可以先区分三个对象：

| 对象 | 描述什么 | CSV 修复中的例子 |
| --- | --- | --- |
| Agent | 模型、指令和可用工具 | 修复目标、代码检查能力与协作配置 |
| Environment | 命令和文件操作的执行位置 | 放着源码、样本和测试依赖的工作区 |
| Session | 持续接收输入、保留工作的运行实例 | 从定位错误到补充兼容性检查的同一项工作 |

Agent 描述能力与规则，Environment 承载实际操作，Session 将配置、交互和工作过程组织起来。只有 Agent 配置，不等于已有源码；准备了一个容器，也不等于已经开始任务。

环境还是可选的。任务如果只通过远程工具查询资料，就可以不配独立 Sandbox；CSV 修复需要读写文件和启动测试，才需要相应环境。**托管 Agent 不意味着每次都必须先创建一台工作机。** [来源：Architecture](https://developers.openai.com/api/docs/guides/agents-api/architecture)

## 二、Session 怎样接续长期任务

### 3. Turn 与 Events：提交工作、观察进展和继续输入

Session 可以包含多轮工作。一次 Turn 内部又可以有多次模型推理、工具调用和结果回传，不能把它理解成一次 LLM 请求。

在这个例子中，应用创建 Session 并提交 CSV 修复任务；Agent 检查实现、修改代码、运行测试，最后返回补丁说明。这是一轮工作。用户再补充旧格式样本时，应用向同一个 Session 发送消息，沿用已有背景继续检查，而不是重新拼接整段历史。

输入发生的时机也有区别：Session 空闲时，新消息启动下一轮；正在工作时，新消息可以引导当前轮的执行。应用需要把产品中的会话与对应的 Session ID 关联起来，不能每次收到一句补充就重新创建实例。

运行过程是异步的，应用可以通过流式事件展示进展，或通过 Webhook 接收状态变化。这里要分清**进展事件与最终结果**：看到测试开始，不等于测试通过；Session 回到空闲，也不等于这一轮成功。需要检查 Turn 的完成、失败或取消状态，再结合实际输出判断。[来源：Run and continue sessions](https://developers.openai.com/api/docs/guides/agents-api/sessions)

### 4. Context 与 Tool Use：平台管理运行中的信息

长期任务积累的不只是用户消息，还有源码片段、测试输出、工具定义与分析记录。平台接管 Harness 后，也就接管了这些信息怎样进入下一轮推理的部分机制。

原文介绍了三种相互配合的能力：接近上下文限制时自动压缩早期内容；按需发现相关工具定义；通过代码组织工具调用、过滤和汇总结果。这些机制分别处理历史增长、工具发现和中间数据量，不是同一种“压缩”。

对 CSV 修复，可以这样理解它们的作用：早期已解决的排查记录整理为继续工作需要的背景；需要查询某项外部资料时再取得相关工具定义；大批样本的统计与筛选在代码中完成，只让有用结果回到模型。

这里整理的是运行分工，而不是声称平台会自动挑出所有重要信息。应用仍要提供清楚的任务约束和可核对的资料。测试标准只存在于某个没有接入的内部文档里，Harness 再完善也无法凭空知道。

### 5. Subagents：由 Harness 协调子任务

任务复杂以后，主 Agent 可以将独立工作交给子 Agent。例如，一个检查解析器改动是否覆盖错误输入，另一个检查旧格式样本的兼容性，主 Agent 再结合两份结果决定是否补充修改。

Agents API 的多 Agent 配置将创建、消息传递、等待和中断等协调工具交给 Harness 提供。每个子 Agent 有自己的上下文，主 Agent 负责组织和汇总。开发者不需要重新实现一套同样的基础调度机制。[来源：Multi-agent](https://developers.openai.com/api/docs/guides/agents-api/multi-agent)

但平台能够协调，不意味着任务天然适合并行。必须先修改解析器才能验证新行为的步骤，仍有依赖；多个 Agent 同时编辑同一个文件，也仍需要约定修改范围和集成顺序。

在这个场景里，两个只读检查任务更容易独立进行，再由主 Agent 统一落实改动。**独立 Context 解决信息组织问题，不自动解决共享工作区的写入冲突。** 托管改变的是协调机制由谁运行，不是取消任务分解本身的工程判断。

## 三、执行环境与文件怎样管理

### 6. Hosted 与 Self-hosted：选择计算环境

Harness 托管在 OpenAI，并不要求文件和命令执行也必须使用 OpenAI 的环境。原文同时提供了 OpenAI-hosted、自有基础设施和合作 Sandbox Provider 的接入方向。

下面的图将这条边界画出来：应用与平台交换任务和事件，托管 Harness 再连接所选执行环境。三种环境是选择关系，不代表每个 Session 同时创建三个 Sandbox。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 1 · Harness 托管与 Compute 选择：应用提交任务，平台组织执行，环境承载文件和命令</figcaption>
<div tabindex="0" role="region" aria-label="应用、OpenAI 托管 Harness 与三种可选执行环境的关系" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="managed-runtime-title managed-runtime-desc" viewBox="0 0 640 420" style="display:block; width:100%; min-width:560px; height:auto; font-family:var(--font-sans); --node:light-dark(#e8f3fc,#142b3e); --condition:light-dark(#f4f9fe,#102333); --ink:light-dark(#235e89,#c0def4); --border:light-dark(#d0e0ed,#355167); --line:light-dark(#8e959d,#8295a6); --success:light-dark(#e5f6eb,#152f26); --success-ink:light-dark(#286447,#a9debf); --success-border:light-dark(#afd3bc,#426c57);">
<title id="managed-runtime-title">托管 Harness 与可选择的执行环境</title>
<desc id="managed-runtime-desc">开发者应用定义任务、工具和业务规则，向 Agents API 提交工作，并接收事件和结果。OpenAI 托管的 Harness 管理 Session、上下文与子任务，向所选执行环境发送请求并取回结果。执行环境可以由 OpenAI 托管、由开发者自管，或接入第三方 Provider；自有环境仍需应用管理生命周期。</desc>
<defs><marker id="managed-runtime-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<rect x="150" y="16" width="340" height="80" rx="20" fill="var(--condition)" stroke="var(--border)"/>
<text x="320" y="49" text-anchor="middle" fill="var(--ink)" font-size="19" font-weight="500">开发者应用</text><text x="320" y="77" text-anchor="middle" fill="var(--ink)" font-size="14">任务、领域工具、业务规则与结果验收</text>
<g fill="none" stroke="var(--line)" stroke-width="1.2" marker-end="url(#managed-runtime-arrow)"><path d="M246 96 V162"/><path d="M394 164 V98"/></g>
<text x="235" y="133" text-anchor="end" fill="var(--ink)" font-size="12">提交 / 继续</text><text x="405" y="133" fill="var(--ink)" font-size="12">事件 / 结果</text>
<rect x="130" y="164" width="380" height="96" rx="20" fill="var(--node)" stroke="var(--border)"/>
<text x="320" y="198" text-anchor="middle" fill="var(--ink)" font-size="19" font-weight="500">OpenAI Managed Harness</text><text x="320" y="228" text-anchor="middle" fill="var(--ink)" font-size="14">Session · Context · Tool Loop · Subagents</text>
<g fill="none" stroke="var(--line)" stroke-width="1.2" marker-end="url(#managed-runtime-arrow)"><path d="M320 260 V292 H110 Q100 292 100 302 V336"/><path d="M320 292 V336"/><path d="M320 292 H530 Q540 292 540 302 V336"/></g>
<text x="428" y="319" text-anchor="middle" fill="var(--ink)" font-size="12">执行请求 / 结果</text>
<g fill="var(--success)" stroke="var(--success-border)"><rect x="10" y="338" width="180" height="64" rx="18"/><rect x="230" y="338" width="180" height="64" rx="18"/><rect x="450" y="338" width="180" height="64" rx="18"/></g>
<text x="100" y="365" text-anchor="middle" fill="var(--success-ink)" font-size="16" font-weight="500">OpenAI-hosted</text><text x="100" y="389" text-anchor="middle" fill="var(--success-ink)" font-size="13">平台准备和管理 Sandbox</text>
<text x="320" y="365" text-anchor="middle" fill="var(--success-ink)" font-size="16" font-weight="500">自有基础设施</text><text x="320" y="389" text-anchor="middle" fill="var(--success-ink)" font-size="13">应用准备和管理环境</text>
<text x="540" y="365" text-anchor="middle" fill="var(--success-ink)" font-size="16" font-weight="500">第三方 Provider</text><text x="540" y="389" text-anchor="middle" fill="var(--success-ink)" font-size="13">接入相应执行环境</text>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">环境是可选项；仅使用远程工具的任务也可以不配 Sandbox。窄屏可在图内左右滑动查看。</div>
</figure>

选择 OpenAI-hosted 时，平台准备并连接工作区，应用提供文件、依赖和所需配置。选择自有环境时，应用负责准备计算资源，并在环境中运行 Executor，让托管 Harness 能发送命令、读取文件和取得结果。

官方自有环境文档使用 `codex exec-server` 承担这层执行。它主动连接平台，接收请求并返回结果；应用仍需处理环境启动、连接和关闭，而不是把容器创建以后就放着不管。[来源：Self-hosted sandboxes](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted)

CSV 修复如果只依赖普通源码和公开依赖，可以考虑托管环境；如果依赖私有网络或特殊软件，就需要围绕这些条件选择环境。判断标准是任务所需资源与约束，不是简单认定自管或托管哪种一定更高级。

### 7. Session State 与 Artifacts：保存工作背景和交付文件

继续同一个 Session，能够沿用已有工作背景；但会话记录、活着的执行环境和已经发布的文件，是不同的资源。

在 OpenAI-hosted 环境中，官方文档约定将输出放到 `/workspace/outputs`，轮次完成时发布为不可变 Artifact。已经发布的副本可以在环境到期后下载。自有环境的文件则由应用通过自己的基础设施取回，不会因为用了相同目录名，就自动进入平台的 Artifacts API。[来源：Files and artifacts](https://developers.openai.com/api/docs/guides/agents-api/environments/files)

因此，CSV 任务的结果应当具体到补丁、测试报告及对应轮次。后续检查产生新版报告时，需要分清版本，不能把旧报告当成新工作区的验证结果。需要长期保存的文件，还要进入应用自己的交付与存储流程。

长期运行也不代表环境永不到期，或任何失败都能原地恢复。连接中断时，可以先查询已有 Session、Turn 和保存的工作；如果 Session 已经失败，则需处理原因，并用仍需要的输入创建新实例。**保留工作状态提供了恢复依据，不是对每一种故障作出无损续跑的保证。** [来源：Errors and recovery](https://developers.openai.com/api/docs/guides/agents-api/errors)

## 四、托管之后开发者仍负责什么

### 8. Application Integration：工具执行、权限与结果验收

平台管理 Agent Loop，并不意味着所有工具都由平台实现。远程 MCP 可以由 Harness 连接；应用自定义的 Function Tool 则仍需要应用接收调用、执行函数并返回结果。处理器不可用时，工作可能停在等待工具结果的位置。

对 CSV 任务，假设补丁生成后还要提交内部审阅，应用就应提供相应接口，并验证用户身份、目标仓库与提交范围。Agent 的一句“请提交”不能代替业务授权；平台能运行循环，也不能替应用决定这份补丁是否可以合入。

失败处理同样需要应用参与。收到连接错误后，应先查询工作是否已经完成、文件或外部操作是否已经发生，再决定继续或重试。模型答复、工具结果、Turn 状态与交付文件需要一起核对，不能用重新发送整个任务代替恢复判断。

自有环境也不能被直接理解为数据完全留在本地。工具结果仍可能进入托管会话。写作时的官方 Overview 明确说明，选择 Self-hosted Sandbox 不会让 Agents API 获得 Zero Data Retention 资格。**计算资源在哪里，与数据经过哪里、保存多久，是两组需要分别检查的问题。**

### 9. Agents SDK 与 Agents API：运行控制和运维职责

这两种方式的主要区别，不在于是否都能调用工具，也不在于是否使用一个名为 SDK 的客户端包。API 本身也可以通过语言 SDK 调用；要比较的是 **Harness 由谁运行与维护**。

| 比较项 | Agents SDK 的应用运行方式 | Agents API 的托管运行方式 |
| --- | --- | --- |
| Harness | 在开发者应用中运行 | OpenAI 运行和维护 |
| 会话与接续 | 应用组织所需存储和恢复流程 | 通过托管 Session 继续工作 |
| 上下文与编排 | 应用组合 SDK 能力并控制执行 | 使用平台提供的运行能力 |
| 执行环境 | 应用接入所需 Provider | 可选托管、自有或合作 Provider |
| 自有环境生命周期 | 应用负责 | 仍然由应用负责 |
| 业务工具、授权与验收 | 应用负责 | 仍然由应用负责 |

SDK 更接近把运行机制作为可组合的库交给应用；托管 API 则把这些机制作为服务接口提供。前者保留更多内部控制，后者减少通用 Runtime 的运行负担，但也需要接受平台接口、支持范围与升级方式。

原文说明 Agents API 基于开源 Codex Harness，并随模型能力持续演进。源码可见有助于理解核心执行逻辑，但不等于托管服务的每一项基础设施都能在本地等价复制。模型或 Harness 版本变化后，也仍需用应用自己的任务集检查行为。

我的理解是，Managed Runtime 抽象的并不是“让模型回答一句话”，而是让应用通过稳定入口消费一段持续执行的工作。应用仍要知道任务由谁授权、工具作用在哪里、结果怎样验收；只是不用再亲自维护每一步通用运行机制。

## 几个关键问题，串起托管、执行与应用责任

**为什么使用了托管 Sandbox，不等于已经使用了托管 Harness？**

Sandbox 提供文件和计算环境，Harness 组织模型与工具循环。上一篇的 SDK 可以在应用侧运行 Harness，再连接托管 Sandbox；本篇的 Agents API 则由平台运行 Harness。需要分别看控制循环和计算环境的责任方。

**Session、Turn 和一次模型推理有什么关系？**

Session 承载持续工作，一次 Turn 是其中一轮执行，一轮内部可以包含多次推理和工具调用。修复完成后追加兼容性检查，可以在同一 Session 开启新 Turn，不需要重建全部背景。

**Context 自动压缩，是否意味着长期任务不需要外部文件？**

不是。压缩处理模型继续推理需要的背景，源码、补丁和报告承载实际工作与交付。把“已修复解析错误”保留在上下文里，不能代替保存那份真实补丁。

**平台提供多 Agent 协调，为什么仍要限制并行修改？**

创建、等待和消息传递解决执行协调，独立上下文解决信息隔离；共享文件的冲突需要另外处理。两个 Agent 可以分别检查不同样本，却不应未经约定同时覆盖同一份解析器。

**工具调用已经交给 Harness，应用还需要接收工具请求吗？**

取决于工具的执行方式。Harness 可以连接远程 MCP，Sandbox 的 Executor 可以执行环境内操作；应用自定义函数仍需要对应处理器。托管循环不等于平台自动拥有业务系统的实现和授权。

**流式连接断开，是否应该立即重发任务？**

不应该直接重发。断流不证明任务失败，先查询 Session、Turn 和保存结果，确认是否仍在工作、已经完成或需要处理。如果外部操作已经发生，还要避免重复执行。

**使用自有计算环境，是否就能保证数据不离开自己的系统？**

不能。执行位置与数据流是两件事，工具输出仍可能交给托管 Harness 和模型。要检查哪些内容会回传、平台的存储与保留约定，以及业务是否允许这种处理方式。

**SDK 与托管 API 的分界，是不是“灵活”和“方便”？**

这两个词太笼统。更具体的分界是 Harness 的运行、状态管理和升级由谁承担，以及应用需要控制哪一层。托管能减少通用基础设施工作，但不会自动承担自有环境、领域权限和业务正确性。

## 参考资料

- [OpenAI — Introducing the Agents API](https://openai.com/index/introducing-the-agents-api/)
- [OpenAI Docs — Agents API Overview](https://developers.openai.com/api/docs/guides/agents-api/overview)
- [OpenAI Docs — Architecture](https://developers.openai.com/api/docs/guides/agents-api/architecture)
- [OpenAI Docs — Run and continue sessions](https://developers.openai.com/api/docs/guides/agents-api/sessions)
- [OpenAI Docs — Multi-agent](https://developers.openai.com/api/docs/guides/agents-api/multi-agent)
- [OpenAI Docs — Self-hosted sandboxes](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted)
- [OpenAI Docs — Files and artifacts](https://developers.openai.com/api/docs/guides/agents-api/environments/files)
- [OpenAI Docs — Errors and recovery](https://developers.openai.com/api/docs/guides/agents-api/errors)
- [上一篇：Agent Infrastructure SDK：Harness、Sandbox 与 Workspace 怎样组合？](/zh-cn/posts/agent-infrastructure-sdk/)
