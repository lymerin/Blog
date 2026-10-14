---
title: 'Agent Infrastructure SDK：Harness、Sandbox 与 Workspace 怎样组合？'
description: '以 OpenAI Agents SDK 为例，理解 Agent 定义、Sandbox Client 和 Manifest 怎样连接执行环境，以及目录权限、产物保存、Snapshot 与运行状态怎样支持持续工作。'
pubDate: 2026-10-14T19:28:32+08:00
category: notes
tags: [Agent, OpenAI, SDK, Infrastructure, 学习笔记]
draft: false
postType: metaOnly
---

[上一篇](/zh-cn/posts/distributed-agent-runtime/)解释了为什么任务记录、Harness 和执行环境需要独立演进。这一篇把视角放到开发者接口：应用拿到 SDK 后，怎样为 Agent 准备工作区，把工具请求送进执行环境，并在暂停或环境更换后接着工作？

OpenAI 的[《The next evolution of the Agents SDK》](https://openai.com/index/the-next-evolution-of-the-agents-sdk/)将 model-native harness 与 native sandbox execution 放在一起介绍。本文沿着一次运行整理：先连接 Agent 与计算环境，再声明工作区和权限，随后保存产物与恢复状态，最后分析跨环境迁移时哪些东西可以复用、哪些仍需核对。

继续使用假设的 CSV 修复任务：应用提供源码和输入样本，Agent 定位解析错误、修改代码、运行测试，最后交出补丁与说明。样本需要保持原样，代码需要可修改，输出需要被应用取走。这些要求既是任务说明，也是工作环境必须落实的条件。

## 一、SDK 怎样连接 Agent 与执行环境

### 1. Harness：模型交互与执行控制

SDK 提供的不只是一次模型请求的包装。Harness 负责驱动 Agent Loop，处理模型返回的工具请求、结果回传、审批和运行状态；应用则在这个框架上定义任务目标、领域工具与业务约束。

这里的 **model-native** 可以理解为：Harness 的工具和执行方式围绕模型擅长使用的能力组织，例如文件检查、Shell、补丁编辑与分层加载资料。它不是让模型直接取得操作系统控制权，也不意味着所有任务都应该套用同一组工具。

对于 CSV 任务，模型可以提出“先读解析器，再运行这个测试”。Harness 将请求送到相应工具，把真实输出带回下一轮；缺少授权时则按配置暂停或处理。**模型决定下一步，运行程序组织这一步怎样发生。**

Sandbox 参与以后，这个关系没有改变。新增的是文件和命令的实际执行位置，而不是重新定义一种脱离普通 Agent 机制的智能体。

### 2. Sandbox Client 与 Session：接入方式和运行实例

开发者需要区分“怎样连接环境”和“这一次使用哪个环境”。Sandbox Client 封装 Provider 的接入方式；Sandbox Session 则是已经准备出来、能够执行命令和保存当前文件的实例。

可以按下面几个问题看 SDK 接口，而不是把所有对象都叫作 Agent：

| 接口对象 | 回答的问题 | CSV 任务中的对应内容 |
| --- | --- | --- |
| `SandboxAgent` | 要做什么，默认带哪些能力？ | 修复解析器的指令、工具与默认工作区 |
| `Manifest` | 新工作区从什么内容开始？ | 源码、样本、任务说明和输出目录 |
| Sandbox Client | 通过什么实现准备和操作环境？ | 本地、容器或托管环境的适配入口 |
| Sandbox Session | 当前命令和文件变化发生在哪里？ | 这一次修复任务使用的工作区实例 |
| Sandbox Run Config | 这一轮创建、复用还是恢复环境？ | 指定 Client，或传入已有 Session |

这些名称沿用[官方 Sandbox Agents 文档](https://developers.openai.com/api/docs/guides/agents/sandboxes)。其中 Session 指 **Sandbox 的执行会话**，不能直接等同于上一篇的持久化事件日志，也不能与 SDK 保存消息历史的会话混为一谈。

原文支持把 Harness 与 Compute 放在同一机器，也支持分开。分开以后，应用侧可以保留模型认证、审批和审计等职责，Sandbox 只接收完成当前工作需要的资源与执行请求。

OpenAI 的[代码迁移 Cookbook](https://developers.openai.com/cookbook/examples/agents_sdk/sandboxed-code-migration/sandboxed_code_migration_agent)就采用了这种组织：宿主进程运行 Harness，任务代码在可替换的 Sandbox 中处理，再把补丁和报告交回宿主。这里值得借鉴的是职责分配，不是要求所有应用复制它的部署方案。

## 二、Workspace 怎样声明和使用

### 3. Manifest：新工作区的初始契约

Manifest 说明一个新环境准备好时应该有什么：哪些文件来自本地，哪个仓库需要放进来，外部存储出现在哪个路径，以及输出应该写到哪里。

对 CSV 任务，可以先设计下面这个布局。它是本文的工作区示意，不是可直接提交给 SDK 的配置文件：

```text
/workspace/
  repo/                 源码、测试与任务说明
    task.md
    src/
    tests/
  samples/              原始 CSV 样本
  output/               补丁、测试报告与修复说明
```

工作区路径让任务说明有了明确对象：从 `samples/` 取证据，在 `repo/` 修改实现，把可交付结果写到 `output/`。应用不必把整个仓库和全部样本都塞进 Prompt，模型也能通过工具取得需要的文件。

这里有一个容易混淆的生命周期：**Manifest 描述新工作区的起点，不是每轮运行都强制同步的最终状态。** 任务已经改过文件时，继续使用同一个 Sandbox，应该接着看当前文件；从快照创建环境时，也要保留所选快照代表的工作状态，而不是默默回到最初源码。

因此，应用在开始一轮工作之前，需要先决定“复用、恢复还是新建”。只有确定是新建，初始 Manifest 才成为这次准备工作区的重要输入。不能把重新传一份 Manifest 当作通用的更新或恢复操作。

### 4. Capabilities：把工作区连接到模型可用的工具

文件已经存在，不代表模型已经获得相应的操作入口。Capabilities 用来把 Sandbox 相关工具与行为接到 Agent 上。

对于 CSV 修复，Shell 可以启动测试和搜索程序，文件编辑能力可以生成补丁；只有任务需要专门操作知识时，再接入 Skills。Memory 与 Compaction 则分别服务于可复用经验和上下文维护，不能用它们代替源码与产物保存。

这个组合关系比“工具越多越好”更具体：模型要运行测试，就需要可用的命令入口和正确的依赖环境；模型要改代码，就需要编辑能力和实际写权限。只有一个名字叫作 Shell 的工具，却没有测试运行时，任务仍然做不下去。

指令也要与能力一致。比如要求保留原始样本、补充边界测试并给出修改说明，工具和目录就必须允许完成这些动作。反过来，任务只要求阅读资料时，没有必要为了统一模板就开放修改和命令执行能力。

### 5. Permissions 与 Mounts：目录访问和外部数据范围

目录布局说明“东西在哪里”，权限说明“当前执行身份能够怎样访问”。对这个任务，一个合理的目标是样本只读、源码可修改、输出目录可写。

这不能只靠 `task.md` 里一句“不要修改样本”。应当核对 Provider 支持的账号、文件权限与挂载设置，并检查工具是否确实以预期身份运行。SDK 可以表达工作区配置，但具体隔离能力还取决于执行实现。

| 工作区位置 | 本文场景希望允许的操作 | 原因 |
| --- | --- | --- |
| `samples/` | 读取，不覆盖原件 | 保留用于复现的输入证据 |
| `repo/` | 读取、修改和运行测试 | 让 Agent 完成实际修复 |
| `output/` | 写入并由应用取回 | 保存可以审阅的结果 |

这张表是权限设计目标，不代表创建这些目录以后就自动具备表中的限制。验证时要看允许动作能否完成，也要看越界动作是否真的失败。

外部存储挂载还增加了一层范围问题。原文介绍了通过 Manifest 接入 S3、GCS、Azure Blob 和 R2 等存储，但“能接入”不是“应该把整个存储账户暴露给任务”。CSV 修复只需要对应样本，就应围绕这组数据安排路径和授权。

凭证也应作为运行时资源管理，而不是写进任务文件、提交的 Manifest 或模型指令。把 Harness 放在 Sandbox 外，有助于保留控制面凭证；确实需要交给执行层的挂载或工具授权，则仍需限制范围。

## 三、一次运行怎样保存结果并继续

### 6. Artifacts：模型答复与可交付文件

模型回答“已经修好了”与应用拿到一份可检查的补丁，是两种不同的结果。前者是答复，后者是产物；文件还留在即将清理的环境里，也不等于已经完成交付。

在 CSV 任务结束时，应用至少要知道补丁和报告保存在哪里、对应哪个代码版本，以及测试返回了什么。然后把需要保留的文件复制到可靠存储或交给审阅流程，再处理环境的关闭与清理。

前面的代码迁移 Cookbook 将补丁、报告和审计记录交回宿主后再清理任务环境，体现的正是这条交付边界。应用负责接收和检查产物，不能只把 Agent 的最后一段话当作文件已经保存的证据。

下面的关系图把初始准备、执行和保存连在一起。真实部署中，Sandbox 可以在宿主本机，也可以由其他 Provider 承载。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 1 · 应用组合执行能力：定义 Agent，准备 Workspace，再分别保存运行状态与产物</figcaption>
<div tabindex="0" role="region" aria-label="Agent 定义与 Manifest 分别进入 Harness 和 Sandbox，执行后保存运行状态与产物" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="infrastructure-sdk-flow-title infrastructure-sdk-flow-desc" viewBox="0 0 640 448" style="display:block; width:100%; min-width:560px; height:auto; font-family:var(--font-sans); --node:light-dark(#e8f3fc,#142b3e); --condition:light-dark(#f4f9fe,#102333); --ink:light-dark(#235e89,#c0def4); --border:light-dark(#d0e0ed,#355167); --line:light-dark(#8e959d,#8295a6); --success:light-dark(#e5f6eb,#152f26); --success-ink:light-dark(#286447,#a9debf); --success-border:light-dark(#afd3bc,#426c57);">
<title id="infrastructure-sdk-flow-title">Harness、Sandbox 与 Workspace 的组合</title>
<desc id="infrastructure-sdk-flow-desc">Agent 定义配置 Harness 的模型、指令与能力。Manifest 描述新工作区的起始内容，由 Sandbox 接入实现准备。Harness 经 Sandbox Client 发出执行请求并接回结果。运行状态保存在应用侧，需要保留的产物和工作区快照另行保存；快照不等于完整 Harness 状态。</desc>
<defs><marker id="infrastructure-sdk-flow-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<g fill="none" stroke="var(--line)" stroke-width="1.2" marker-end="url(#infrastructure-sdk-flow-arrow)"><path d="M150 84 V150"/><path d="M490 84 V150"/><path d="M280 198 H358"/><path d="M360 256 H282"/><path d="M150 292 V356"/><path d="M490 292 V356"/></g>
<g fill="var(--condition)" stroke="var(--border)"><rect x="20" y="20" width="260" height="64" rx="20"/><rect x="360" y="20" width="260" height="64" rx="20"/></g>
<text x="150" y="47" text-anchor="middle" fill="var(--ink)" font-size="18" font-weight="500">Agent 定义</text><text x="150" y="71" text-anchor="middle" fill="var(--ink)" font-size="13">模型、指令、Capabilities</text>
<text x="490" y="47" text-anchor="middle" fill="var(--ink)" font-size="18" font-weight="500">Manifest</text><text x="490" y="71" text-anchor="middle" fill="var(--ink)" font-size="13">新工作区的初始契约</text>
<g fill="var(--node)" stroke="var(--border)"><rect x="20" y="152" width="260" height="140" rx="20"/><rect x="360" y="152" width="260" height="140" rx="20"/></g>
<text x="150" y="188" text-anchor="middle" fill="var(--ink)" font-size="19" font-weight="500">应用侧 Harness</text><text x="150" y="219" text-anchor="middle" fill="var(--ink)" font-size="14">模型交互、调度与审批</text><text x="150" y="249" text-anchor="middle" fill="var(--ink)" font-size="14">管理本轮运行状态</text>
<text x="490" y="188" text-anchor="middle" fill="var(--ink)" font-size="19" font-weight="500">Sandbox Session</text><text x="490" y="219" text-anchor="middle" fill="var(--ink)" font-size="14">Workspace、文件与命令</text><text x="490" y="249" text-anchor="middle" fill="var(--ink)" font-size="14">由 Provider 承载执行</text>
<text x="320" y="184" text-anchor="middle" fill="var(--ink)" font-size="12">执行请求</text><text x="320" y="230" text-anchor="middle" fill="var(--ink)" font-size="12">经 Client</text><text x="320" y="278" text-anchor="middle" fill="var(--ink)" font-size="12">实际结果</text>
<g fill="var(--success)" stroke="var(--success-border)"><rect x="20" y="358" width="260" height="68" rx="20"/><rect x="360" y="358" width="260" height="68" rx="20"/></g>
<text x="150" y="387" text-anchor="middle" fill="var(--success-ink)" font-size="17" font-weight="500">运行记录与恢复状态</text><text x="150" y="412" text-anchor="middle" fill="var(--success-ink)" font-size="13">由应用持久化需要的内容</text>
<text x="490" y="387" text-anchor="middle" fill="var(--success-ink)" font-size="17" font-weight="500">产物与工作区快照</text><text x="490" y="412" text-anchor="middle" fill="var(--success-ink)" font-size="13">按交付与恢复需要保存</text>
</svg>
</div>
</figure>

### 7. Snapshot 与 Run State：恢复文件和恢复执行进度

原文介绍了 snapshotting 与 rehydration：保存状态后，可以在新环境中重新准备工作区，避免容器失效就让任务从头开始。要把这个能力用对，还需要明确保存的究竟是哪种状态。

可以用三个问题区分它们：

- **Harness 运行状态：** Agent 正停在哪里，有哪些模型交互、工具状态或待处理审批？
- **Sandbox 会话状态：** 应用怎样重新连接或恢复对应的执行会话？
- **Workspace Snapshot：** 新工作区从哪一份已经保存的文件内容开始？

官方文档分别使用 `RunState`、序列化 Sandbox Session State 和 `snapshot` 描述这些恢复入口，而不是把三者当成可互换的备份。[来源：Resume or seed future work](https://developers.openai.com/api/docs/guides/agents/sandboxes#resume-or-seed-future-work)

在 CSV 任务中，假设 Agent 修改了解析器，保存快照后暂停等待审阅。恢复工作区可以取回那一版代码，但要继续之前的执行，还需要对应的会话与运行背景。如果只把文件快照交给一个新任务，它可以在这些文件上工作，却不等于接续了原来那个暂停点。

Checkpoint 之后尚未保存的变化，也不能被当作已经恢复。恢复完成后，应用和 Agent 应先确认源码版本、必要依赖与已有测试产物，再继续操作；不能拿一份更早的测试报告证明后来恢复出的工作区正确。

外部挂载还有不同语义：工作区快照并不自动复制所有远程存储内容。远程数据可能需要重新挂载，并核对访问授权和数据版本。由此可见，**保存会话、保存文件和保存外部资源，都需要对应的契约，而不是一个统一的“保存全部”。**

## 四、环境更换后哪些部分可以复用

### 8. Provider Portability：应用契约与执行差异

SDK 将 Provider 接入与 Agent 定义分开，让开发者可以保留任务指令、工作区布局和工具能力，改变承载它们的计算环境。

例如，CSV 修复可以先在适合本地验证的环境中组织流程，再接入独立容器或托管 Provider。原文列出了多种集成，也支持自行接入 Sandbox；这里重要的不是背 Provider 名单，而是应用不必把“修复解析器”的业务逻辑写死在某个容器服务里。

但接口可移植，不等于运行条件完全一致。切换前仍要核对运行时和依赖、账号权限、网络、挂载方式、存活时间，以及快照和恢复能力。本地工具能够启动，不证明新的环境已经具备同样条件。

适配层隐藏的是接入细节，不应该隐藏影响任务正确性的差异。如果某个环境没有所需测试运行时，就要准备依赖；如果输入来自外部挂载，就要核对范围；如果环境会到期，就要安排保存和取回产物。

这也明确了 SDK 的职责边界：**应用仍然运行 Harness，并决定资源、授权、交付和恢复策略。** 使用托管 Sandbox，只是将计算环境交给 Provider，不代表整个 Agent Runtime 的运维都已经交出去了。

## 几个关键问题，串起工作区、执行与恢复

**Manifest 与 Prompt 都能告诉 Agent 去哪里找文件，为什么还需要两者？**

Prompt 指导模型怎样工作，Manifest 准备新工作区实际有什么。写一句“读取样本”不能让文件自动出现；准备一个样本目录，也不能替代对任务目标和完成条件的说明。

**每轮都传同一个 Manifest，能保证工作区始终一致吗？**

不能这样理解。Manifest 主要描述新环境的起点，已有 Session、恢复状态和快照可能决定当前工作区。继续任务时，应先明确环境来源，再检查实际文件，不能把初始声明当作当前状态。

**Sandbox Client、Sandbox Session 和会话历史有什么区别？**

Client 是 Provider 接入实现，Sandbox Session 是当前执行实例，会话历史保存模型交互。知道怎样连接一个 Provider，不代表已经拥有一个工作区；保留消息历史，也不代表磁盘文件仍在。

**有了文件编辑工具，是否就拥有所有文件的写权限？**

没有。工具暴露操作入口，权限限制入口实际能够作用的资源。样本只读、源码可写，应该由执行身份和底层权限落实，而不是依赖模型记住一条指令。

**Snapshot、Memory 和 Compaction 都能帮助继续任务，能互相替代吗？**

不能。Snapshot 保存可用于恢复工作区的内容，Memory 组织可复用经验，Compaction 处理当前上下文规模。保存了一条“CSV 引号需要特殊处理”的经验，不能恢复尚未保存的解析器补丁。

**工作区已经恢复，为什么还需要运行状态？**

文件回答“当前有什么”，运行状态回答“执行停在哪里”。暂停审批、待处理工具调用和活跃 Agent 位置，不能只从源码推断。恢复文件可以成为新任务的起点，但不自动还原原任务的控制过程。

**更换 Provider 只需要改一个 Client 吗？**

接入接口可以保持简洁，但实际迁移仍需验证能力与约束是否兼容。目录路径不变，不代表依赖、权限、网络和恢复语义都相同。可移植性减少业务代码与 Provider 的耦合，不是取消环境验证。

## 参考资料

- [OpenAI — The next evolution of the Agents SDK](https://openai.com/index/the-next-evolution-of-the-agents-sdk/)
- [OpenAI Docs — Sandbox Agents](https://developers.openai.com/api/docs/guides/agents/sandboxes)
- [OpenAI Cookbook — Migrate a Legacy Codebase with Sandbox Agents](https://developers.openai.com/cookbook/examples/agents_sdk/sandboxed-code-migration/sandboxed_code_migration_agent)
- [上一篇：Distributed Agent Runtime：Session、Harness 与执行环境怎样解耦？](/zh-cn/posts/distributed-agent-runtime/)
