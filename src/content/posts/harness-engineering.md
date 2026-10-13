---
title: 'Harness Engineering：怎样建设适合 Agent 自主开发的工程环境？'
description: '理解 Agent-first 工程中的仓库可读性、AGENTS.md 导航、执行计划、可观测性、机械化架构约束，以及审查和技术债的持续治理。'
pubDate: 2026-10-13T13:30:00+08:00
category: notes
tags: [Agent, OpenAI, Codex, Harness, 软件工程, 学习笔记]
draft: false
postType: metaOnly
---

[App Server](/zh-cn/posts/codex-app-server/)把 Agent 的执行能力开放给客户端。但运行时能够读文件、跑测试、管理会话，还不代表一个真实仓库已经适合长期自主开发。规则只存在于聊天里、应用很难启动、日志需要人手工截图，都会把开发过程重新卡在人类身上。

这里的 Harness Engineering，关注的不只是 Agent 外面的一段循环，而是**怎样组织整个软件工程环境，让目标可理解、行为可观察、规则可检查、反馈可积累。**

OpenAI 的[《Harness engineering: leveraging Codex in an agent-first world》](https://openai.com/index/harness-engineering/)来自一个主要由 Codex 产出代码的内部产品实验。本文提取其中的工程机制，分三部分理解：

- **知识与工具：** 仓库怎样提供背景，Agent 怎样观察真实程序。
- **边界与验证：** 重要规则怎样从文字要求变成自动检查。
- **持续改进：** 审查、缺陷和技术债怎样反馈到后续开发。

## 一、仓库怎样提供 Agent 需要的工程知识

从目标与验收要求出发，把背景、规则和决策放进能够找到、维护与核对的材料中。

### 1. Agent-first Engineering：明确人类职责与环境能力

Agent-first 不是让人类退出开发，而是改变投入的位置。模型可以生成实现，但产品目标、取舍、验收要求与允许的操作范围，仍然需要人来确定。

例如，“让笔记页面更快”并不明确：是首次打开慢、搜索慢，还是输入延迟？如果要求能够对应用户路径、测量入口和目标，Agent 才能判断应检查哪一层。

因此，一次开发失败也可能暴露环境缺口：

- 不知道应该采用什么设计，可能缺少可发现的架构依据。
- 能修改代码却无法验证，可能缺少可启动的环境或测试入口。
- 反复违反同一条规则，可能只有口头要求，没有检查机制。
- 总要人复制日志，可能缺少可访问的观测工具。

这并不排除模型能力不足，而是把问题拆得更具体。工程师可以据此决定，是调整任务、补充知识、增加工具，还是保留人工判断。

环境建设的产出也不只是给当前任务使用。一条清楚的测试入口、一份准确的模块说明，可以在后续很多轮开发中重复发挥作用。

### 2. Repository Legibility：用导航和分层文档组织知识

Repository Legibility 指的是：Agent 能否从仓库找到理解任务所需的信息，并辨认哪些内容是当前有效的依据。

源码表达实现，文档补充意图。为什么模块不能直接访问数据库、某个兼容逻辑为什么暂时不能删、设计为何放弃另一种方案，都未必能从函数名字中读出来。

**AGENTS.md 作为导航入口**

把全部规范塞进一个巨大文件，会让当前任务与无关规则争夺 Context，也增加过时内容的维护难度。更清晰的方式，是用短入口标明：

- 主要目录和业务模块在哪里。
- 架构约束与开发规范去哪里查。
- 怎样启动、测试和检查项目。
- 当前任务需要遵守哪些关键限制。

深入内容留在有主题的文档中，按任务读取。一个自拟的简化组织可以是：

```text
AGENTS.md                  工作入口与索引
docs/
├── architecture.md        模块与依赖边界
├── development.md         启动和验证入口
├── decisions/             重要设计取舍
└── plans/                 活跃计划与已完成记录
```

重点不是照搬目录名，而是入口、主题与链接关系清楚。文件越多并不等于知识越充分；重复或互相矛盾的说明，反而会降低可用性。

**让文档与代码一起维护**

文档需要标明适用范围，并在实现变化时同步更新。链接检查和结构检查可以自动完成；行为是否仍与描述一致，则需要结合代码和测试核对。

仓库中的知识也不应成为敏感信息堆放区。把必要背景整理为可访问材料，与把凭证或私人记录写进仓库，是两回事。

我理解的“可读”，不只是模型能读到文本，而是它能沿着清楚的入口，找到当前任务真正需要且足以支持判断的信息。

### 3. Execution Plans：保存决策、依赖与工作进度

简单修改可以用短计划组织；跨模块任务则需要把目标、步骤、决策和未解决问题留成可接续的材料。

Execution Plan 与[长期任务的进度文件](/zh-cn/posts/long-running-agents/)有联系，但关注范围更大：

| 内容 | 保存的理由 |
| --- | --- |
| 目标与非目标 | 防止实现不断扩大，明确哪些不属于这次工作 |
| 实现步骤与依赖 | 说明工作顺序，避免跳过前置条件 |
| 设计决策及依据 | 解释为什么采用当前方案 |
| 进度与验证 | 区分已经实现、已经检查和仍未完成 |
| 已知技术债 | 避免临时妥协被误认成长期规范 |

例如，把搜索改成异步请求时，计划可以解释为什么保留旧接口、怎样避免过期响应覆盖新结果，以及哪些兼容检查仍需执行。

这些内容如果只存在于上一轮聊天，新的 Agent 很难发现。进入版本化材料以后，后续修改可以连同当时的约束一起理解，而不是把看起来复杂的逻辑直接简化掉。

计划也不能永远停留在初稿。实现推翻了原有假设，就应记录新的决策；完成以后保留结果与遗留问题，而不是让“待办”一直悬在已经结束的任务上。

## 二、程序行为与架构规则怎样被检查

Agent 需要取得真实运行证据，也需要在重要工程边界上得到明确反馈。

### 4. Observability：观察应用、日志、指标与 Trace

Agent 能否自己取得验证证据，决定了多少工作需要人类代为操作。

**可独立启动的应用实例**

独立工作区让代码变化能够分开，配套应用实例则让各自验证也有清楚对象。否则 A 的代码在自己的目录里，浏览器访问的却是 B 启动的服务，结果就难以归因。

隔离范围还可能包括测试数据和观测输出。是否需要全部隔离，取决于任务，但至少要知道本次证据对应哪份代码、哪次运行。

**不同观察入口承担不同职责**

| 入口 | 主要回答什么 |
| --- | --- |
| DOM、截图与浏览器交互 | 用户实际看到什么，操作是否有效 |
| 日志 | 某次请求经过什么处理，哪里报告错误 |
| 指标 | 延迟、错误率等量化表现怎样变化 |
| Trace | 一条调用链的时间花在哪些环节 |

例如，“搜索慢”可以先由浏览器复现，再用 Trace 找到耗时调用，并从日志检查请求与数据范围。只看模型对源码的推测，很难确认哪一个解释成立。

观测能力不仅是“把日志塞进 Prompt”。更有效的方式是提供查询入口、关联标识和必要摘要，让 Agent 针对问题取证。大量无关输出同样会消耗 Context。

这一层不要求 Agent 永远自行解决所有问题，而是让能重复取得的事实，不必每次经过人工搬运。

### 5. Architecture Invariants：机械验证重要架构约束

文档说明规则，自动检查负责稳定执行其中能够形式化的部分。

以一个假设的分层笔记应用为例，可以规定：UI 不直接访问持久层，外部输入在边界校验，日志使用统一结构。这些规则分别可以通过依赖检查、结构测试和自定义 Linter 验证。

**约束边界，而不是规定每一行写法**

要求“数据进入领域逻辑前完成校验”，与要求“每个函数必须用某个固定模板”不同。前者保护系统边界，后者可能限制了无关的实现选择。

好的 Invariant 应说明它保护什么，并能对应明确的违规情形。对模块依赖的约束，要能识别不允许的引用；对日志的约束，要能检查字段和调用方式。

**错误信息也是反馈接口**

“架构检查失败”不足以帮助修正。更有用的错误应指出违规位置、规则和可行的修复方向，例如：

> 编辑页面直接导入了持久层模块。请通过应用服务访问笔记，保持界面与存储边界。

这不是用更多 Prompt 替代检查，而是让检查失败后仍有清晰的下一步。

机械规则也有边界。依赖方向正确，不代表业务逻辑正确；所有 Lint 通过，不代表交互好用。自动检查应与测试、运行证据和审查互补。

## 三、开发反馈怎样进入持续质量治理

当前补丁需要修正，重复出现的问题则需要沉淀为后续开发能够使用的规则和工具。

### 6. Review Loop：修复当前问题并沉淀反馈

一次 PR 的反馈，可以同时产生两种结果：修复当前补丁，以及降低同类问题再次出现的概率。

例如，审查发现多个页面重复处理保存状态。当前修改可以提取共享实现；进一步则需要判断，是否应补充使用说明或结构检查，避免后续 Agent 再复制旧模式。

<figure class="not-prose" style="margin:1.75em 0;">
  <figcaption style="font-size:.8125rem;color:var(--muted-foreground);margin-bottom:1rem;text-align:center;">图 1 · 将一次开发反馈沉淀为后续任务可以使用的文档和工具</figcaption>
  <div role="region" aria-label="图 1 · 将一次开发反馈沉淀为后续任务可以使用的文档和工具，可横向滚动" tabindex="0" style="overflow-x:auto;max-width:100%;border-radius:16px;padding:8px 0;background:hsl(0 0% 50% / .025);">
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 530" role="img" aria-labelledby="engineering-feedback-title" style="display:block;width:100%;min-width:580px;height:auto;font-family:var(--font-sans);--node:light-dark(#e8f3fc,#142b3e);--ink:light-dark(#235e89,#c0def4);--border:light-dark(#d0e0ed,#355167);--line:light-dark(#8e959d,#8295a6);--success:light-dark(#e5f6eb,#152f26);--success-ink:light-dark(#286447,#a9debf);--success-border:light-dark(#afd3bc,#426c57);">
      <title id="engineering-feedback-title">图 1 · 将一次开发反馈沉淀为后续任务可以使用的文档和工具</title>
      <defs><marker id="engineering-feedback-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 1 1 L 8 5 L 1 9" fill="none" stroke="var(--line)" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
      <path d="M290 55H430" fill="none" stroke="var(--line)" stroke-width="1.5" marker-end="url(#engineering-feedback-arrow)"/>
      <path d="M555 90V160" fill="none" stroke="var(--line)" stroke-width="1.5" marker-end="url(#engineering-feedback-arrow)"/>
      <path d="M430 195H290" fill="none" stroke="var(--line)" stroke-width="1.5" marker-end="url(#engineering-feedback-arrow)"/>
      <path d="M165 230V300" fill="none" stroke="var(--line)" stroke-width="1.5" marker-end="url(#engineering-feedback-arrow)"/>
      <path d="M290 335H430" fill="none" stroke="var(--line)" stroke-width="1.5" marker-end="url(#engineering-feedback-arrow)"/>
      <path d="M555 370V440" fill="none" stroke="var(--line)" stroke-width="1.5" marker-end="url(#engineering-feedback-arrow)"/>
      <g><rect x="40" y="20" width="250" height="70" rx="18" fill="var(--node)" stroke="var(--border)" stroke-width="1.5"/><g text-anchor="middle" fill="var(--ink)"><text x="165" y="52" font-size="17" font-weight="600">工程目标</text><text x="165" y="75" font-size="13">需求与验收要求</text></g></g>
      <g><rect x="430" y="20" width="250" height="70" rx="18" fill="var(--node)" stroke="var(--border)" stroke-width="1.5"/><g text-anchor="middle" fill="var(--ink)"><text x="555" y="52" font-size="17" font-weight="600">仓库知识</text><text x="555" y="75" font-size="13">文档 · 计划 · 规则</text></g></g>
      <g><rect x="430" y="160" width="250" height="70" rx="18" fill="var(--node)" stroke="var(--border)" stroke-width="1.5"/><g text-anchor="middle" fill="var(--ink)"><text x="555" y="192" font-size="17" font-weight="600">Agent 实现</text><text x="555" y="215" font-size="13">按需读取并操作开发环境</text></g></g>
      <g><rect x="40" y="160" width="250" height="70" rx="18" fill="var(--node)" stroke="var(--border)" stroke-width="1.5"/><g text-anchor="middle" fill="var(--ink)"><text x="165" y="192" font-size="17" font-weight="600">验证与观测</text><text x="165" y="215" font-size="13">测试 · Lint · 运行证据</text></g></g>
      <g><rect x="40" y="300" width="250" height="70" rx="18" fill="var(--success)" stroke="var(--success-border)" stroke-width="1.5"/><g text-anchor="middle" fill="var(--success-ink)"><text x="165" y="332" font-size="17" font-weight="600">PR 与审查</text><text x="165" y="355" font-size="13">修改、复核与交付</text></g></g>
      <g><rect x="430" y="300" width="250" height="70" rx="18" fill="var(--node)" stroke="var(--border)" stroke-width="1.5"/><g text-anchor="middle" fill="var(--ink)"><text x="555" y="332" font-size="17" font-weight="600">重复问题归因</text><text x="555" y="355" font-size="13">审查意见与实际缺陷</text></g></g>
      <g><rect x="430" y="440" width="250" height="70" rx="18" fill="var(--success)" stroke="var(--success-border)" stroke-width="1.5"/><g text-anchor="middle" fill="var(--success-ink)"><text x="555" y="472" font-size="17" font-weight="600">更新文档与工具</text><text x="555" y="495" font-size="13">进入后续开发的反馈循环</text></g></g>
    </svg>
  </div>
</figure>

可以把反馈按原因分流：

- **目标理解错误：** 调整需求和验收表达。
- **背景缺失：** 更新相关文档与入口。
- **实现缺陷：** 修改代码并补充针对性测试。
- **反复违反稳定规则：** 考虑将要求提升为自动检查。

不是每条意见都值得变成规则。一次性的局部偏好，写进全局约束可能影响其他任务；有广泛价值、能够清楚检查的要求，才适合持续执行。

随着环境成熟，Agent 可以从局部改代码，扩展到复现问题、实现、验证、建立 PR 和处理反馈。但这种自主性依赖仓库工具、验证与操作授权，不是发出一句“自主完成”就自动拥有全部能力。

尤其是合并、发布和涉及外部系统的操作，仍应遵守明确的责任和权限边界。闭环能力与无条件授权不是同一个概念。

### 7. Garbage Collection：持续清理技术债与重复模式

Agent 会参考仓库已有写法。坏模式一旦进入共同代码，就可能成为后续任务的示例：重复工具函数、过时文档和临时兼容逻辑都会继续扩散。

这里的 Entropy 可以理解为代码与知识组织逐渐失去一致性；Garbage Collection 则是持续、小范围地发现和清理这种退化。

例如，可以定期检查：

- 同一规则是否出现多份不一致实现。
- 文档描述是否已经落后于代码。
- 模块是否绕过了既定边界。
- 临时措施是否仍有必要，已知技术债是否得到跟踪。

清理也必须有证据。两个函数看起来相似，不代表行为相同；删除一个“多余”分支前，需要理解兼容条件并验证结果。

持续治理的价值，是让代码库提供更好的后续范例，而不只是让某次 Diff 更整洁。每轮输出都进入下一轮的工作环境，环境质量会随这些积累发生变化。

### 8. Human Attention：分配人工判断与自动检查

当代码生成越来越快，人类逐个检查所有细节容易成为瓶颈。自动测试、规则检查与针对性审查，可以承担重复性工作，把人工注意力留给目标、重要取舍和难以形式化的判断。

原文实验采用较少的阻塞式合并关卡，强调快速反馈与后续修正。这是特定产品、工具成熟度和风险条件下的取舍，不能直接推广为“测试失败也应该先合并”。

如果修改涉及不可逆的数据变更、支付或关键权限，修正成本可能很高；如果验证基础还不充分，快速合并只会放大未知风险。吞吐变化需要重新设计反馈速度，不代表可以忽略后果。

我从这篇提取的核心是：**工程约束不必全部由人反复提醒，但必须有明确承载它们的位置。** 知识进入文档，稳定规则进入工具，实际行为进入验证，重要取舍仍由人承担。

运行时决定 Agent 怎样执行；工程环境则决定它能否持续找到依据、取得证据，并让质量随着开发积累，而不是逐渐退化。

## 几个关键问题，串起仓库知识、约束与质量治理

**Harness Engineering 是重新实现 Agent Loop 吗？**

不是。这里关注仓库知识、开发工具、架构规则和反馈机制，解决的是 Agent 在真实项目中怎样持续开发。

**为什么 AGENTS.md 更适合当导航？**

入口应帮助定位当前任务需要的规则，而不是预先加载所有内容。分层文档更容易按需读取、维护和核对。

**Execution Plan 与任务清单有什么不同？**

清单描述要完成什么；执行计划还保存依赖、设计决策、验证结果和技术债，帮助后续理解为什么这样推进。

**可观测性为什么属于 Agent 的开发能力？**

它让 Agent 能取得真实程序的证据，而不只是根据源码猜测。日志、指标、Trace 和浏览器观察分别补充不同层面的信息。

**重要规则为什么不能只写在 Prompt 里？**

稳定且可检查的规则可以由 Lint、结构测试和 CI 持续执行，减少反复提醒。但无法形式化的判断仍需要其他反馈。

**架构检查通过，是否代表应用已经正确？**

不是。它验证特定结构约束，不能代替业务测试、用户路径和实际运行验证。

**为什么需要持续清理，而不只是修复当前任务？**

既有代码会影响后续生成。坏模式扩散后，修复范围会扩大；小范围治理能够同时改善当前产物和下一轮工作环境。

**Agent 能完成 PR 全流程，就可以减少所有人工检查吗？**

不能。自主程度取决于工具成熟度、验收能力和操作风险。应明确自动化能可靠承担的工作，把关键判断保留给相应负责人。

## 参考资料

- [OpenAI · Harness engineering: leveraging Codex in an agent-first world](https://openai.com/index/harness-engineering/)
