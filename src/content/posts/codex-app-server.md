---
title: 'Agent Runtime：Agent Loop 之外还需要什么？'
description: '以 Codex App Server 为例，理解 Agent Loop 之外的会话管理、持久化、工具执行与客户端交互，以及 Thread、Turn、Item 和双向事件协议。'
pubDate: 2026-10-13T13:20:00+08:00
category: notes
tags: [Agent, OpenAI, Codex, Harness, JSON-RPC, 学习笔记]
draft: false
postType: metaOnly
---

[Agent Loop](/zh-cn/posts/codex-agent-loop/)说明了一次行动怎样完成：模型提出工具调用，外部程序执行，结果回到模型。把这个循环做成 IDE 或桌面里的开发助手，还需要回答另一组问题：会话保存在哪里，工具进度怎样显示，用户审批怎样影响执行，断线以后怎样恢复界面？

这些能力不属于模型的一次推理，也不只是 UI。它们构成了 Agent 的运行时与接入协议。

OpenAI 的[《Unlocking the Codex harness: how we built the App Server》](https://openai.com/index/unlocking-the-codex-harness/)介绍了 Codex 的具体实现。本文沿三条线展开：

- **运行时分层：** Codex Core 怎样执行任务，App Server 怎样向客户端开放能力。
- **会话模型：** Thread、Turn、Item 怎样组织历史与工作过程。
- **交互协议：** 请求、通知和服务器请求怎样承载事件流、审批与多客户端接入。

## 一、Agent Runtime 怎样组织执行与会话

以 Codex 为例，先区分执行核心和客户端边界，再看工作过程怎样组织成会话记录。

### 1. Codex Core 与 App Server：分开执行核心与客户端接口

Codex Core 包含 Agent Loop，以及与执行相连的会话持久化、配置、认证、工具和扩展逻辑。它既是可复用的代码库，也能运行一条 Codex 会话。

App Server 则把这些能力组织成客户端可以使用的接口，同时作为长期运行的进程承载 Core 会话。

两者不是“两个不同的 Agent”：

| 层次 | 主要职责 |
| --- | --- |
| Client | 收集输入，展示消息、工具进度与修改，取得用户决定 |
| App Server | 处理协议请求，管理会话接入，将内部事件转换为客户端通知 |
| Codex Core | 推进 Agent Loop，执行工具，维护会话与运行状态 |
| 执行环境 | 承载实际文件、命令和外部资源 |

例如，用户在 IDE 中要求运行测试。IDE 不需要自行实现“测试失败后再让模型判断”的循环；它提交请求，接收过程事件，展示输出，并在需要时提供审批交互。

这里复用的是一整套执行能力，而不只是共享一个模型名称。相同的核心运行时可以连接不同界面，界面也不必依赖所有内部 Rust 类型。

### 2. Thread、Turn 与 Item：组织会话、轮次与工作记录

三个概念分别组织持续会话、一轮工作与具体输入输出。

**Thread：持续会话的容器**

Thread 保存用户与 Agent 的会话历史，可以包含多轮任务。它不是操作系统线程，也不是模型的一次推理。

例如，先要求“检查项目测试”，再要求“修复第二个失败”，两次工作可以位于同一个 Thread 中，共用此前的对话背景。

**Turn：用户输入触发的一轮工作**

Turn 包含这次请求之后的 Agent 执行。一次“运行测试并总结失败”，内部可能包含查看目录、执行命令、分析输出和生成答复。

因此，一个 Turn 可以包含多次模型调用和工具执行。不能把 Turn 直接等同于一次 LLM inference。

**Item：一项有类型的输入或输出**

用户消息、Agent 消息、命令执行、文件修改或工具调用，都可以形成对应类型的 Item。不同类型携带不同数据：命令有输出与退出状态，文件修改有路径和差异，消息有文本内容。

以一次请求为例：

```text
Thread：项目测试排查
└── Turn：运行测试并总结失败
    ├── 用户消息
    ├── 命令执行：查看测试入口
    ├── 命令执行：运行测试
    └── Agent 消息：说明失败与下一步建议
```

这里展示的是包含关系，不是规定每轮都必须执行这些步骤。

协议还会发送计划、Diff 更新或审批请求。**Item 是工作记录，事件是记录变化与交互的通知方式；并非每条事件都代表新增一个 Item。**

## 二、运行时怎样与客户端持续交互

一项任务会产生多次更新，也可能需要用户决定。事件生命周期与双向协议共同承载这些交互。

### 3. Item Lifecycle：流式更新与完成状态

长任务不能只在结束时返回一段文字。命令可能运行很久，消息会逐步生成，文件差异也需要在过程中展示。

Item 的公共生命周期提供了几个边界：

- `item/started`：这条记录开始，界面可以创建对应位置。
- 适用类型的 delta 事件：内容逐步到达，客户端更新显示。
- `item/completed`：该 Item 结束，以最终载荷确认状态。

<figure class="not-prose" style="margin:1.75em 0;">
  <figcaption style="font-size:.8125rem;color:var(--muted-foreground);margin-bottom:1rem;text-align:center;">图 1 · 一次 Turn 包含多个 Item；这里只展开一条流式 Item</figcaption>
  <div role="region" aria-label="图 1 · 一次 Turn 包含多个 Item；这里只展开一条流式 Item，可横向滚动" tabindex="0" style="overflow-x:auto;max-width:100%;border-radius:16px;padding:8px 0;background:hsl(0 0% 50% / .025);">
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 460" role="img" aria-labelledby="turn-events-title" style="display:block;width:100%;min-width:580px;height:auto;font-family:var(--font-sans);--node:light-dark(#e8f3fc,#142b3e);--ink:light-dark(#235e89,#c0def4);--border:light-dark(#d0e0ed,#355167);--line:light-dark(#8e959d,#8295a6);--success:light-dark(#e5f6eb,#152f26);--success-ink:light-dark(#286447,#a9debf);--success-border:light-dark(#afd3bc,#426c57);">
      <title id="turn-events-title">图 1 · 一次 Turn 包含多个 Item；这里只展开一条流式 Item</title>
      <defs><marker id="turn-events-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 1 1 L 8 5 L 1 9" fill="none" stroke="var(--line)" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
      <path d="M290 55H430" fill="none" stroke="var(--line)" stroke-width="1.5" marker-end="url(#turn-events-arrow)"/>
      <path d="M555 90V170" fill="none" stroke="var(--line)" stroke-width="1.5" marker-end="url(#turn-events-arrow)"/>
      <path d="M430 205H290" fill="none" stroke="var(--line)" stroke-width="1.5" marker-end="url(#turn-events-arrow)"/>
      <path d="M165 240V350" fill="none" stroke="var(--line)" stroke-width="1.5" marker-end="url(#turn-events-arrow)"/>
      <path d="M290 385H430" fill="none" stroke="var(--line)" stroke-width="1.5" marker-end="url(#turn-events-arrow)"/>
      <g><rect x="40" y="20" width="250" height="70" rx="18" fill="var(--node)" stroke="var(--border)" stroke-width="1.5"/><g text-anchor="middle" fill="var(--ink)"><text x="165" y="52" font-size="17" font-weight="600">Thread</text><text x="165" y="75" font-size="13">创建或恢复持久化会话</text></g></g>
      <g><rect x="430" y="20" width="250" height="70" rx="18" fill="var(--node)" stroke="var(--border)" stroke-width="1.5"/><g text-anchor="middle" fill="var(--ink)"><text x="555" y="52" font-size="17" font-weight="600">turn/start</text><text x="555" y="75" font-size="13">用户请求触发本轮工作</text></g></g>
      <g><rect x="430" y="170" width="250" height="70" rx="18" fill="var(--node)" stroke="var(--border)" stroke-width="1.5"/><g text-anchor="middle" fill="var(--ink)"><text x="555" y="202" font-size="17" font-weight="600">item/started</text><text x="555" y="225" font-size="13">开始一条输出或工具记录</text></g></g>
      <g><rect x="40" y="170" width="250" height="70" rx="18" fill="var(--node)" stroke="var(--border)" stroke-width="1.5"/><g text-anchor="middle" fill="var(--ink)"><text x="165" y="202" font-size="17" font-weight="600">增量事件</text><text x="165" y="225" font-size="13">适用类型持续更新内容</text></g></g>
      <g><rect x="40" y="350" width="250" height="70" rx="18" fill="var(--success)" stroke="var(--success-border)" stroke-width="1.5"/><g text-anchor="middle" fill="var(--success-ink)"><text x="165" y="382" font-size="17" font-weight="600">item/completed</text><text x="165" y="405" font-size="13">这条 Item 形成最终状态</text></g></g>
      <g><rect x="430" y="350" width="250" height="70" rx="18" fill="var(--success)" stroke="var(--success-border)" stroke-width="1.5"/><g text-anchor="middle" fill="var(--success-ink)"><text x="555" y="382" font-size="17" font-weight="600">turn/completed</text><text x="555" y="405" font-size="13">整轮结束，检查最终 status</text></g></g>
      <text x="360" y="365" text-anchor="middle" fill="var(--line)" font-size="13">本轮全部工作结束</text>
    </svg>
  </div>
</figure>

例如，测试命令开始后，界面先显示运行状态，再接收输出增量，最后显示退出码和完整结果。接着 Agent 还可能继续分析，所以**一个命令 Item 结束，不代表整个 Turn 已经结束**。

同理，收到 RPC 的成功响应，可能只说明启动请求已经被接受。客户端还要继续消费事件，直到这一轮到达终态。

当前官方文档中，`turn/completed`还会携带 `completed`、`failed` 或 `interrupted` 等状态。名称中的 completed 表示生命周期结束，不能据此把失败或中断显示为成功。[官方文档：Events](https://learn.chatgpt.com/docs/app-server#events)

即使状态是 completed，也只是说明这轮 Agent 工作正常结束；用户要求的软件功能是否通过验收，仍需要检查实际产物。

### 4. Bidirectional JSON-RPC：请求、通知与审批

双向通信有两层含义：服务器可以持续通知客户端，也可以主动发出需要客户端回应的请求。

**客户端请求与服务器响应**

请求包含 `method`、`params` 和 `id`；响应使用相同的 `id`关联结果或错误。例如，以下是简化的 Thread 创建交换：

```json
{"method":"thread/start","id":10,"params":{}}
{"id":10,"result":{"thread":{"id":"thr_example"}}}
```

这不是完整客户端程序，实际连接还需要先初始化。

**服务器通知**

通知没有请求 `id`，用于传达状态变化，例如一轮开始、消息增量和工具进度。客户端不能只等待自己发送的请求响应，否则会错过大部分工作过程。

**服务器请求**

需要审批时，服务器向客户端发出带 `id`的请求，并等待决定。客户端展示待执行动作，取得用户选择，再以相应响应继续协议交换。

审批请求不是一句普通的聊天提示。若只把它渲染成文字，没有发送协议响应，执行就可能继续等待。反过来，也不能因为界面希望快速运行，就自动把所有审批视为允许。

一个简化的连接顺序是：

> 建立传输 → initialize / initialized → 创建或恢复 Thread → turn/start → 持续处理通知与服务器请求 → 检查 Turn 终态

App Server 使用保留请求、响应和通知形状的 JSON-RPC 变体，线上消息省略 `jsonrpc`版本字段。原文主要讲 JSONL over stdio：一行一条 JSON。协议规定交互含义，stdio 则是传输方式，二者不是同一个概念。

### 5. Message Processing：转换协议消息与管理 Core 会话

原文介绍了四个主要组件：

| 组件 | 职责 |
| --- | --- |
| stdio Reader | 读取客户端消息并交给处理层 |
| Codex Message Processor | 将 RPC 请求转换为 Core 操作，将内部事件转换为客户端协议 |
| Thread Manager | 创建、查找和管理 Thread 对应的 Core 会话 |
| Core Threads | 运行各自的 Agent 工作并产生更新 |

一条请求可以这样理解：Reader 取得消息，Processor 识别操作，取得对应 Thread 的会话句柄，再提交给 Core。执行过程产生的更新返回处理层，被整理为客户端可以理解的通知。

这里重要的不是组件名称，而是**内部执行结构与外部协议之间存在转换边界**。Core 可以演进，客户端仍然围绕 Thread、Turn、Item 等稳定概念组织界面。

多个 Thread 也需要分别关联请求与更新。某条测试输出属于哪个项目会话、哪个 Turn、哪个命令，必须由标识关联，不能只按消息到达顺序塞进当前打开的聊天窗口。

配置、认证和工具策略同样需要明确归属：客户端可以提供交互入口，真正的执行仍由运行时按配置处理。App Server 不等于绕过策略的一条命令通道。

## 三、会话怎样恢复，运行时怎样被复用

持久化保存交互背景，客户端接入则决定这套执行能力怎样进入不同产品。

### 6. Thread Persistence：创建、恢复、分叉与归档

Thread 可以创建、恢复、分叉和归档。这些操作管理的是会话及其历史，不自动完成代码仓库的对应操作。

- **恢复会话**让系统重新取得已存储的交互背景。
- **分叉会话**建立新的历史分支，不天然等于创建 Git 分支或复制工作目录。
- **归档会话**改变其存放与展示状态，不等于删除项目文件。

这也区分了它与[第十三篇的项目交接](/zh-cn/posts/long-running-agents/)：

| 状态层次 | 保存什么 | 不能单独保证什么 |
| --- | --- | --- |
| 会话持久化 | 输入输出、执行历史与交互生命周期 | 当前代码与历史描述一致 |
| 项目交接 | 需求状态、进度说明、代码版本和验证依据 | 客户端完整恢复运行时事件 |

历史里曾经显示“测试通过”，当前文件可能已经改变。因此，恢复 Thread 可以减少重新解释背景的成本，但继续开发前仍应核对真实工作区。

持久化也不等于恢复一个冻结的操作系统进程。正在运行的命令、外部连接和服务资源，具有自己的生命周期，不能仅从聊天记录推断它们仍然存在。

### 7. Client Integration：连接 IDE、桌面、Web 与 CLI

**本地 IDE 与桌面**

本地客户端可以启动 App Server 子进程，通过双向通道交互。界面负责编辑器集成、进度和审批展示，运行时负责执行与会话。

**Web**

原文的 Web 路径多了一层后端 Worker：它准备包含工作区的容器，在其中启动 App Server，再把事件经后端流向浏览器。浏览器并不是直接读取远程进程的 stdin / stdout。

由此，页面关闭与执行进程结束可以分开管理。但能否持续工作，仍取决于服务器与任务生命周期，不是所有客户端断开后都天然永久运行。

**CLI**

CLI 与 IDE 可以复用同一个 Core，但不代表每个版本都使用完全相同的接入路径。原文发布时，TUI 仍有直接连接 Core 的历史实现，接入 App Server 被列为后续改造方向；不能把这个计划当作当时已经完成的架构。

对自己的集成，先看需要哪一种控制范围：

| 方式 | 适合的需求 |
| --- | --- |
| App Server | 丰富会话界面、持续事件、审批和运行时能力 |
| Codex Exec | 非交互脚本与一次性自动化任务 |
| Codex SDK | 使用库接口编程控制，减少自己处理协议的工作 |
| Codex MCP Server | 在已有 MCP 工作流中把 Codex 作为可调用能力 |

这不是功能优劣排名。需要丰富交互，就必须承担状态与事件处理；只需要一次任务结果，则没有必要先搭完整客户端。

我对 App Server 的理解是：它把 Agent 从“能够执行的循环”变成“能够被产品连接、观察和控制的运行时”。会话模型、生命周期与双向协议，正是这一层增加的工程内容。

## 几个关键问题，串起运行时、会话与客户端协议

**App Server 与 Codex Core 有什么区别？**

Core 实现并运行 Agent 逻辑；App Server 承载会话并提供客户端协议，将请求与内部执行、事件更新连接起来。

**Turn 等于一次模型调用吗？**

不等于。它是用户请求触发的一轮工作，内部可以包含多次推理、工具执行与多个 Item。

**收到 item/completed，可以结束加载状态吗？**

可以结束该 Item 的状态，但不能据此结束整轮。还需要等待 Turn 的终态，并检查成功、失败或中断。

**为什么只实现流式文本还不够？**

Agent 还会运行工具、修改文件、请求审批并报告错误。客户端需要区分这些结构化交互，而不只是拼接回答文字。

**为什么服务器也要发送请求？**

因为运行过程可能需要用户决定或补充输入。服务器请求建立可回应的协议关系，运行时可以等待决定再继续。

**恢复或分叉 Thread，是否会恢复或分叉代码？**

不自动成立。会话历史与文件、Git 状态是不同层次，应分别管理和核对。

**不同界面复用 Harness，是否必须显示相同 UI？**

不必。它们复用执行语义和协议，仍可采用适合终端、编辑器或浏览器的交互表达。

## 参考资料

- [OpenAI · Unlocking the Codex harness: how we built the App Server](https://openai.com/index/unlocking-the-codex-harness/)
- [OpenAI Docs · Codex App Server](https://learn.chatgpt.com/docs/app-server)
