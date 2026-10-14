---
title: 'Distributed Agent Runtime：Session、Harness 与执行环境怎样解耦？'
description: '以 Anthropic Managed Agents 的架构为例，理解持久化事件历史、可重启 Harness 和可替换执行环境的职责，以及解耦怎样影响故障恢复、凭证隔离、启动延迟和横向扩展。'
pubDate: 2026-10-14T19:10:18+08:00
category: notes
tags: [Agent, Anthropic, Runtime, Architecture, 学习笔记]
draft: false
postType: metaOnly
---

[上一篇](/zh-cn/posts/production-agent-security/)讨论了权限和执行记录怎样进入组织治理。继续往运行时内部看，这些记录、负责调度的 Harness，以及真正执行命令的环境，也有各自的生命周期。一个容器停止，不应该就意味着整个任务从此无法继续。

Anthropic 的[《Scaling Managed Agents: Decoupling the brain from the hands》](https://www.anthropic.com/engineering/managed-agents)讨论的正是这个架构问题。本文先区分 Session、Harness 与执行环境，再解释状态恢复，随后分析解耦对安全、启动延迟和扩展的影响，最后回到稳定接口与工程代价。

下面仍用一个假设任务说明：Agent 修复 CSV 解析错误、补测试并整理结果。任务需要保存请求和执行经过，也需要代码文件与测试环境；如果中途进程退出，系统必须知道哪些东西还在、哪些需要重建，而不是笼统地说一句“恢复 Agent”。

## 一、运行时的组件怎样拆分

### 1. 单容器架构：共享环境与生命周期耦合

把 Harness、工作目录和会话状态放进同一个容器，是很自然的起点。读写文件可以直接调用系统接口，启动测试也不用跨服务通信。对于规模有限、任务较短的系统，这样的简单性很有价值。

问题出现在不同职责被同一个容器的生命周期绑住以后。容器失去响应时，可能同时失去执行能力、任务进度的访问入口，以及负责报告状态的进程。此时看到“没有新事件”，并不能立即分清是程序卡住、连接断开，还是环境已经失效。

在 CSV 任务里，解析脚本报错本来只是一次工具失败。如果连会话记录与调度程序都依赖这个环境存活，局部故障就可能变成整项任务无法接续。

另一类耦合来自位置假设：Harness 默认所有资源都在身边，接入其他网络或不同执行设备时，就需要改变它所在的环境。**组件共享一台机器不一定有问题；把“必须共存”写进接口，才会限制替换和扩展。**

### 2. Session、Harness 与 Hands：记录、决策和执行

原文把核心职责拆为 Session、Harness 和 Sandbox，并用 brain / hands 说明决策与行动的关系。Brain 包含模型和驱动它的 Harness；Hands 则泛指承载行动的工具与执行环境，不只是一台容器。

| 组件 | 主要职责 | CSV 任务中的例子 |
| --- | --- | --- |
| Session | 独立保存追加的任务事件 | 用户请求、工具调用及返回结果 |
| Harness | 调用模型、组织上下文、路由工具并记录进展 | 把报错交给模型，路由后续读文件与测试请求 |
| Sandbox / Hands | 接收动作并在相应环境中执行 | 修改源码、启动测试、返回输出 |

拆分后，Harness 通过接口调用执行环境，不再要求自己住在那个环境里。环境返回测试失败或执行错误，Harness 将结果纳入后续处理，并把相应事件写入 Session。

Session 因而不是“正在运行的那个进程”的别名。它保存的是任务能够接续的历史；Harness 是当前推进任务的执行者；Sandbox 是本次行动使用的工作环境。三者可以协作，但不必拥有相同的存活时间。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 1 · 三种职责通过接口连接，任务历史不依赖某个 Harness 或 Sandbox 存活</figcaption>
<div tabindex="0" role="region" aria-label="Session、Harness 与 Sandbox 的记录和执行关系" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="distributed-runtime-components-title distributed-runtime-components-desc" viewBox="0 0 640 252" style="display:block; width:100%; min-width:560px; height:auto; font-family:var(--font-sans); --node:light-dark(#e8f3fc,#142b3e); --condition:light-dark(#f4f9fe,#102333); --ink:light-dark(#235e89,#c0def4); --border:light-dark(#d0e0ed,#355167); --line:light-dark(#8e959d,#8295a6); --success:light-dark(#e5f6eb,#152f26); --success-ink:light-dark(#286447,#a9debf); --success-border:light-dark(#afd3bc,#426c57);">
<title id="distributed-runtime-components-title">Session、Harness 和 Sandbox 的解耦关系</title>
<desc id="distributed-runtime-components-desc">Harness 从独立的 Session 读取事件并追加进展，向 Sandbox 发出执行请求并接回结果。Session 保存历史，Harness 负责模型交互和调度，Sandbox 承载文件和进程操作。执行结果由 Harness 记录，不表示事件历史自动保存所有工作区文件。</desc>
<defs><marker id="distributed-runtime-components-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<g fill="none" stroke="var(--line)" stroke-width="1.2" marker-end="url(#distributed-runtime-components-arrow)"><path d="M192 100 H230"/><path d="M232 142 H194"/><path d="M408 100 H446"/><path d="M448 142 H410"/></g>
<text x="212" y="87" text-anchor="middle" fill="var(--ink)" font-size="11">读取</text><text x="212" y="163" text-anchor="middle" fill="var(--ink)" font-size="11">追加</text>
<text x="428" y="87" text-anchor="middle" fill="var(--ink)" font-size="11">调用</text><text x="428" y="163" text-anchor="middle" fill="var(--ink)" font-size="11">结果</text>
<rect x="16" y="62" width="176" height="112" rx="20" fill="var(--success)" stroke="var(--success-border)"/>
<text x="104" y="100" text-anchor="middle" fill="var(--success-ink)" font-size="19" font-weight="500">Session</text><text x="104" y="128" text-anchor="middle" fill="var(--success-ink)" font-size="14">持久化事件历史</text><text x="104" y="151" text-anchor="middle" fill="var(--success-ink)" font-size="13">独立保存任务进展</text>
<rect x="232" y="62" width="176" height="112" rx="20" fill="var(--node)" stroke="var(--border)"/>
<text x="320" y="100" text-anchor="middle" fill="var(--ink)" font-size="19" font-weight="500">Harness</text><text x="320" y="128" text-anchor="middle" fill="var(--ink)" font-size="14">组织模型交互与调度</text><text x="320" y="151" text-anchor="middle" fill="var(--ink)" font-size="13">可重启的 Brain 组件</text>
<rect x="448" y="62" width="176" height="112" rx="20" fill="var(--condition)" stroke="var(--border)"/>
<text x="536" y="100" text-anchor="middle" fill="var(--ink)" font-size="19" font-weight="500">Sandbox</text><text x="536" y="128" text-anchor="middle" fill="var(--ink)" font-size="14">执行文件与进程操作</text><text x="536" y="151" text-anchor="middle" fill="var(--ink)" font-size="13">一种 Hands 实现</text>
<text x="320" y="217" text-anchor="middle" fill="var(--ink)" font-size="13">恢复任务历史、重建执行环境，是两项不同的工作</text>
</svg>
</div>
</figure>

这里说的接口是职责边界，不要求每个组件都必须拆成一套远程服务。它们可以先同机部署，但代码不应依赖“只有这一个进程和容器能够继续任务”。

## 二、故障后任务怎样继续

### 3. Session Log 与 Context Window：历史保存和当前输入

Session 保存发生过什么，Context Window 决定模型这一轮看到什么。**可以取回一段历史，不等于每轮都要把完整历史塞给模型。**

CSV 任务可能已经执行了多轮测试，产生大量重复输出。Harness 可以只为当前推理选择相关错误、最近修改和必要背景；较早的事件仍保留在 Session 中，需要核对时再读取。压缩当前输入，不应该顺手破坏唯一一份可恢复记录。

这也是 append-only log 的作用：新的请求、动作与结果作为新事件追加，而不是用最新摘要覆盖全部执行经过。顺序记录能支持从某个位置继续读取，也能回看某次动作之前的背景。

当前官方事件文档也将实时事件流与历史查询分开。连接断开后，客户端需要结合历史和新事件恢复观察，并处理事件重复；**观看进度的连接不是任务状态的唯一存储位置**。[来源：Session event stream](https://platform.claude.com/docs/en/managed-agents/events-and-streaming)

但事件日志也不是磁盘镜像。记录“修改了解析器”可以帮助恢复执行背景，却不能代替那份修改后的文件。理解恢复机制时，至少要分清三类状态：

- **任务事件：** 请求、调用、结果与进度，保存在 Session 一侧。
- **当前推理上下文：** Harness 从历史中组织出的输入，可以重新构造。
- **环境状态：** 文件、依赖、运行中的进程及中间产物，需要相应的保存或重建机制。

这三类状态会互相引用，但不能用“会话还在”推断它们全部完好。

### 4. Failure Recovery：重启 Harness 与替换执行环境

Harness 可以无状态重启，指的是任务接续不依赖旧进程的内存继续存在，并不是说它运行时不保存变量、缓冲区或当前上下文。

原文的恢复过程，是由外部编排层唤起新的 Harness，读取独立保存的 Session 事件，然后从已记录的位置接着处理。运行期间持续写入进展，才能让替代者知道此前做了什么，而不是只拿到最初的用户请求。

Sandbox 失效则走另一条路径：Harness 接到执行错误，把失败反馈给模型；需要继续时，再按资源配置准备新的环境。这里替换的是执行能力，不是换一个全新的任务。

| 故障位置 | 可以保留什么 | 继续前需要确认什么 |
| --- | --- | --- |
| 客户端事件连接 | 服务端已经保存的历史 | 补取遗漏记录，避免重复展示 |
| Harness 进程 | 独立 Session 中的进展 | 重建上下文，确认未完成调用 |
| Sandbox | Session 和未受影响的组件 | 恢复所需文件、依赖与资源，再核对环境 |

用 CSV 任务举例：如果仅 Harness 退出，而执行环境仍在，替代 Harness 可以先检查文件和测试结果；如果环境也丢失，就需要从可靠保存的源码与产物恢复。只存在旧的测试成功事件，却没有对应版本的代码，不能直接宣称当前环境已经通过测试。

从这个架构还能推导出一个重要限制：**恢复记录，不自动提供外部操作的“恰好执行一次”。** 假设提交结果的请求已经被远程服务接受，但返回途中断开，日志中可能只有调用请求，没有成功结果。此时直接重发可能产生重复提交，需要查询实际状态，或由接口提供幂等机制。

这是分布式执行的恢复问题，不是原文已经承诺解决的全部语义。把故障隔离开，是为了能够定位并继续处理，而不是把所有失败都变成无条件重试。

## 三、解耦后怎样管理执行与扩展

### 5. Security Boundary：执行环境与凭证访问

执行用户代码的环境，与管理模型调用和外部服务认证的组件，承担不同信任职责。把它们放进同一环境，并让代码能读取运行时凭证，会让一次错误执行拥有更大的影响范围。

原文将凭证访问移到执行环境之外，并以 MCP 代理和 Vault 说明：调用者提出工具请求，受控组件取得对应凭证，再与外部服务交互，而不是把真实凭证交给生成的脚本。[来源：原文的安全边界设计](https://www.anthropic.com/engineering/managed-agents)

官方 Vault 文档也将凭证注册与会话引用分开，MCP 凭证在连接对应服务时注入。这个接口让“任务可以使用某项服务”与“模型可以读取凭证正文”成为两件事。[来源：Authenticate with vaults](https://platform.claude.com/docs/en/managed-agents/vaults)

对于 CSV 任务，脚本读取项目数据，并不意味着它应该拿到创建其他任务的管理凭证。即使需要访问一个外部工具，也可以由受控入口完成认证。

不过，凭证不可见不等于调用没有风险。Agent 仍然可能请求工具执行不合适的操作，因此工具权限、网络范围与审批仍然要落实。解耦缩小了凭证暴露面，没有取消行动授权问题。

### 6. Lazy Provisioning：执行环境与启动关键路径

把 Brain 放在容器里，还会让模型开始工作依赖容器先准备好。如果启动会话必须依次等容器创建、资源装载、仓库准备和 Harness 启动，用户在第一段回答出现前就承担了整条准备链的耗时。

解耦后，Harness 可以先读取 Session 并开始模型交互。只有确实需要执行代码或操作文件时，再准备相应环境。一个只需要分析已提供资料的任务，也不必为了一个不会用到的 Shell 先启动容器。

可以用两条简化路径理解这个变化：

```text
耦合启动：接收任务 → 准备容器与资源 → 启动 Harness → 首次推理
按需准备：接收任务 → Harness 读取事件 → 首次推理
                                      → 需要执行时再准备环境
```

这里优化的是 **TTFT（Time to First Token）**：从接收工作到出现首个响应 Token 的等待。Anthropic 报告，在它们这次架构调整中，p50 TTFT 下降约 60%，p95 下降超过 90%。这是该系统改造后的结果，原文没有给出可直接推广到任意工作负载的统一收益。[来源：原文的性能结果](https://www.anthropic.com/engineering/managed-agents)

按需准备没有让环境创建成本消失。CSV 任务一旦要跑测试，仍需等待必要环境就绪；如果第一步就必须使用 Shell，收益也取决于实际关键路径。首个 Token 更早出现，与整项任务更早完成，是两项不同指标。

### 7. Many Brains / Many Hands：计算扩展与执行目标

Brain 与 Hands 不再一一绑定后，两边可以按不同需求扩展。

**Many Brains** 关注推进任务的 Harness：多个任务可以由多个可替换实例承接，不必每启动一个实例，就同时启动一台专属容器。原文讨论的是这类横向扩展能力，不意味着多个 Harness 可以毫无协调地同时改写同一任务。

**Many Hands** 关注行动目标：一个 Brain 可以把不同工作送到不同环境或工具。CSV 修复可能在代码环境中改解析器，在另一套环境中执行兼容性测试，再通过专门工具保存结果。一个目标失败，不必连带毁掉其他环境和会话历史。

这也对模型和接口提出了新要求。模型需要分清当前操作应该送到哪里，Harness 需要把请求路由到正确目标，结果则要能对应回原来的调用。否则，“文件不存在”可能只是读错了环境，而不是文件真的丢失。

因此，统一执行接口的价值不是抹平所有环境差异，而是让调用方式稳定，同时保留目标身份、能力和结果语义。**能够连接多个执行环境，与能够可靠协调这些环境，是两个不同层次的能力。**

## 四、稳定接口怎样支持 Harness 演进

Harness 包含上下文组织、工具调度、停止判断等策略。这些策略与模型能力有关：某个模型需要的补救流程，换一个模型后可能成为额外负担。若策略和会话存储、执行环境绑在一起，更换策略就会牵动整个运行时。

原文用 **Meta-harness** 描述承载不同 Harness 的基础设施。它不是再增加一个更聪明的 Agent 来指挥所有 Agent，而是固定相对稳定的契约：如何取得事件、如何记录进展、如何准备资源，以及如何提出执行请求。具体 Harness 可以在这些契约之上变化。

对 CSV 任务而言，旧 Harness 可以使用一种历史整理方式，新 Harness 使用另一种；只要事件语义和执行接口兼容，就不必为了修改上下文策略，连同任务记录和测试环境一起推翻。

但稳定接口不等于没有工程成本。组件分开以后，需要处理调用延迟、超时、重复消息、版本兼容，以及跨组件定位故障。独立 Session 也成为需要保证可用性与持久性的基础设施，而不是把数据移出去就自动获得可靠性。

这些是从解耦结构得到的工程取舍：小型系统可以保持同机部署，长任务或多环境需求增加后再逐步分离。判断架构是否有价值，应看它是否让状态、执行和策略能够独立演进，而不是只看服务数量有没有增加。

## 几个关键问题，串起状态、恢复与扩展

**Session 与 Context Window 都保存交互信息，为什么还要分开？**

前者保存可恢复、可查询的任务历史，后者是模型当前推理的输入。Harness 可以压缩或选择输入，而不删除历史原件。这样既控制每轮信息量，也保留回看旧事件的能力。

**Harness 无状态，是否意味着每次都从零开始？**

不是。它从外部 Session 读取进展并重建上下文。“无状态”强调不依赖某个进程的内存长期存活，不是任务没有状态，也不是每次只拿最初的用户请求重新做一遍。

**Sandbox 可以替换，为什么文件还可能丢失？**

可替换描述的是组件生命周期，不承诺所有临时状态都自动持久化。源码、产物和依赖需要相应保存或重建；内存与运行中的进程也不能只靠事件文字还原。恢复后还要核对实际环境与日志所指向的版本是否一致。

**日志里没有成功结果，就可以重试工具调用吗？**

不一定。远程动作可能已经发生，只是响应丢失。查询状态、调用标识和幂等机制用于处理这种不确定性；单纯重放事件不能保证不重复产生副作用。

**按需创建 Sandbox 为什么改善 TTFT，却不保证缩短总耗时？**

它把环境准备从首次模型交互的必经路径中移出，让不需要环境的工作先开始。但需要执行时仍要支付准备成本。应该分别测量首个响应、首次工具可用和任务完成的时间。

**Many Brains 与 Many Hands 是在说同一种扩展吗？**

不是。前者扩展负责模型交互与调度的实例，后者扩展行动所作用的环境和工具。二者解耦后不必按固定比例增长，但多执行者的协调、多环境的状态对应仍需单独设计。

**把 Runtime 拆成多个服务，就算完成解耦了吗？**

不算。若某个服务退出仍会丢掉任务唯一状态，或所有组件必须同步重启，生命周期依旧耦合。真正要检查的是：哪个组件可以替换、替换后从哪里恢复、接口是否保留了必要语义，以及故障会影响哪些职责。

## 参考资料

- [Anthropic — Scaling Managed Agents: Decoupling the brain from the hands](https://www.anthropic.com/engineering/managed-agents)
- [Claude Platform Docs — Session event stream](https://platform.claude.com/docs/en/managed-agents/events-and-streaming)
- [Claude Platform Docs — Authenticate with vaults](https://platform.claude.com/docs/en/managed-agents/vaults)
- [上一篇：Production Agent Security：怎样统一管理权限、审计与安全响应？](/zh-cn/posts/production-agent-security/)
