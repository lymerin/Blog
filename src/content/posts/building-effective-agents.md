---
title: 'Building Effective Agents：Workflow 与 Agent 应该怎么选？'
description: '从任务结构出发，理解 Workflow 与 Agent 的区别，逐个拆解五种常见 Workflow 的工作方式、适用场景与代价，再整理 Agent 的运行机制和选型思路。'
pubDate: 2026-10-08T17:45:04+08:00
updatedDate: 2026-10-11
category: notes
tags: [Agent, Workflow, Anthropic, LLM, 学习笔记]
draft: false
postType: metaOnly
---

读 [Anthropic 的《Building effective agents》](https://www.anthropic.com/engineering/building-effective-agents)，我最认同的是它的出发点：**先看任务有什么结构，再选择足够简单的实现方式。** 重点不是怎样搭出一个更复杂的 Agent，而是哪些地方确实需要模型自主决定。

有些任务步骤固定，按顺序处理就够了；有些任务需要分类、并行或反复修改，也可以用明确的 Workflow 完成。只有当执行路线本身难以提前确定，下一步必须根据刚获得的信息来决定时，Agent 的灵活性才真正有价值。

这篇笔记沿着这条主线展开：先区分 Workflow 与 Agent，再逐个拆解五种 Workflow，最后说明 Agent 怎样运行，以及如何在它们之间做选择。例子是为了把结构讲清楚，而不是给某一种模式贴上“更高级”的标签。

## 知识地图：先看分类，再看任务结构

原文把这些系统统称为 **Agentic Systems**，按控制结构区分为 **Workflow** 和 **Agent**。本文围绕这两类结构展开：它们是什么，五种 Workflow 分别怎样组织任务，以及什么时候需要 Agent。

原文另外把具备 Retrieval、Tools、Memory 的模型称为 **Augmented LLM**，作为这些系统共同使用的能力底座。这里不展开，重点是这些能力如何被组织成 Workflow 或 Agent。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 1 · Agentic Systems：两类控制结构，五种 Workflow</figcaption>
<div tabindex="0" role="region" aria-label="图 1 · Agentic Systems：两类控制结构，五种 Workflow" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg class="agents-flow" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="effective-agents-patterns-title effective-agents-patterns-desc" viewBox="0 0 640 474" style="display:block; width:100%; min-width:540px; height:auto; font-family:var(--font-sans); --node:light-dark(#e8f3fc,#142b3e); --condition:light-dark(#f4f9fe,#102333); --ink:light-dark(#235e89,#c0def4); --border:light-dark(#d0e0ed,#355167); --line:light-dark(#8e959d,#8295a6); --success:light-dark(#e5f6eb,#152f26); --success-ink:light-dark(#286447,#a9debf); --success-border:light-dark(#afd3bc,#426c57); --warn:light-dark(#fff3d7,#352918); --warn-ink:light-dark(#8b5b22,#f3ce8d); --warn-border:light-dark(#e8c98e,#80663a);">
<title id="effective-agents-patterns-title">Agentic Systems 的分类</title>
<desc id="effective-agents-patterns-desc">Agentic Systems 分为 Workflow 与 Agent。Workflow 的整体执行结构由程序预先设计，包含固定顺序的 Prompt Chaining、分类分流的 Routing、并行处理的 Parallelization、动态拆分的 Orchestrator-Workers，以及反馈迭代的 Evaluator-Optimizer。Agent 则由模型依据环境反馈动态决定执行过程。</desc>
<defs><marker id="effective-agents-patterns-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<rect x="200" y="18" width="240" height="66" rx="20" fill="var(--node)" stroke="var(--border)"/>
<text x="320" y="47" text-anchor="middle" fill="var(--ink)" font-size="18" font-weight="500">Agentic Systems</text>
<text x="320" y="71" text-anchor="middle" fill="var(--ink)" font-size="13">按执行过程由谁决定来区分</text>
<g fill="none" stroke="var(--line)" stroke-width="1.2" marker-end="url(#effective-agents-patterns-arrow)"><path d="M320 84 V102 Q320 112 310 112 H194 V134"/><path d="M320 84 V102 Q320 112 330 112 H502 V134"/></g>
<rect x="24" y="136" width="340" height="314" rx="20" fill="var(--condition)" stroke="var(--border)"/>
<text x="194" y="169" text-anchor="middle" fill="var(--ink)" font-size="18" font-weight="500">Workflow</text>
<text x="194" y="195" text-anchor="middle" fill="var(--ink)" font-size="13">整体执行结构由程序预先设计</text>
<rect x="40" y="214" width="308" height="38" rx="10" fill="var(--node)" stroke="var(--border)"/>
<text x="52" y="238" fill="var(--ink)" font-size="14">Prompt Chaining</text>
<text x="332" y="238" text-anchor="end" fill="var(--ink)" font-size="13">固定顺序</text>
<rect x="40" y="259" width="308" height="38" rx="10" fill="var(--node)" stroke="var(--border)"/>
<text x="52" y="283" fill="var(--ink)" font-size="14">Routing</text>
<text x="332" y="283" text-anchor="end" fill="var(--ink)" font-size="13">分类分流</text>
<rect x="40" y="304" width="308" height="38" rx="10" fill="var(--node)" stroke="var(--border)"/>
<text x="52" y="328" fill="var(--ink)" font-size="14">Parallelization</text>
<text x="332" y="328" text-anchor="end" fill="var(--ink)" font-size="13">并行处理</text>
<rect x="40" y="349" width="308" height="38" rx="10" fill="var(--node)" stroke="var(--border)"/>
<text x="52" y="373" fill="var(--ink)" font-size="14">Orchestrator-Workers</text>
<text x="332" y="373" text-anchor="end" fill="var(--ink)" font-size="13">动态拆分</text>
<rect x="40" y="394" width="308" height="38" rx="10" fill="var(--node)" stroke="var(--border)"/>
<text x="52" y="418" fill="var(--ink)" font-size="14">Evaluator-Optimizer</text>
<text x="332" y="418" text-anchor="end" fill="var(--ink)" font-size="13">反馈迭代</text>
<rect x="388" y="136" width="228" height="162" rx="20" fill="var(--success)" stroke="var(--success-border)"/>
<text x="502" y="169" text-anchor="middle" fill="var(--success-ink)" font-size="18" font-weight="500">Agent</text>
<text x="502" y="207" text-anchor="middle" fill="var(--success-ink)" font-size="14">模型依据环境反馈</text>
<text x="502" y="233" text-anchor="middle" fill="var(--success-ink)" font-size="14">动态决定执行过程</text>
<text x="502" y="274" text-anchor="middle" fill="var(--success-ink)" font-size="13">判断 → 行动 → 反馈 → 再判断</text>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">五种 Workflow 是不同组织方式，不是升级顺序。窄屏可在图内左右滑动查看。</div>
</figure>

## 1. Workflow 和 Agent 到底差在哪里？

**核心区别是：执行过程主要由谁决定。** 有没有 Tool、调用了几次 LLM、是否存在循环，都不足以单独区分两者。

**Workflow：程序规定基本路线**

以写文章为例，程序可以提前规定：**生成大纲 → 检查大纲 → 根据大纲写正文**。模型负责生成每一步的内容，但步骤的顺序、检查的时机，以及检查失败后怎么处理，都由程序安排。

原文用 **predefined code paths** 描述这种结构，也就是预定义的代码路径。这里的“预定义”不等于每一次执行都完全一样：程序可以设置分支、并行和循环，模型也可以在节点中做判断。关键是这些判断仍在事先设计的结构内发生。

**Agent：模型动态决定执行过程**

再看“修复一个陌生项目里的 GitHub Issue”。开始时很难知道要查多少文件、改几个模块、需不需要补测试，以及测试失败后该往哪里排查。

模型可能先搜索类名，读到代码后转去检查另一个模块，修改后运行测试，再根据失败信息继续定位。**下一步不是一开始就全部排好的，而是由模型根据当前信息决定的。**

两者都可以多步执行，但组织方式不同：Workflow 是让模型完成流程里的任务，Agent 则把更多行动选择交给模型。

## 2. 为什么不应该一上来就用 Agent？

Agent 的灵活性有代价。执行路线越开放，就越难提前预测会调用多少次模型和工具，也越容易增加延迟、成本与失败路径。

Anthropic 建议先寻找最简单的可行方案。对不少应用来说，改好 Prompt，补充检索信息和上下文示例，一次调用就已经足够。需要多阶段处理时，再考虑 Workflow；只有固定结构难以表达任务的不确定性时，才需要进一步引入 Agent。

因此，选型可以先问两个问题：**一次调用能否完成？如果不能，执行结构能否提前设计？** 前者决定要不要增加步骤，后者帮助判断这些步骤应该由程序编排，还是由模型动态探索。

下面五种 Workflow，就是五种不同的编排方式。它们都允许多次调用，但每一种增加调用的理由不同。

## 3. Prompt Chaining：固定步骤，一个接一个做

**Prompt Chaining 适合能清晰拆成固定顺序的任务。** 前一步的输出成为下一步的输入，每次调用只处理其中一个环节。

**怎么工作？**

仍以写文章为例：

> 生成大纲 → 检查大纲 → 根据通过检查的大纲写正文

“写一篇结构合理、内容完整、语言自然的文章”同时包含好几个目标。拆成链以后，第一步先解决结构问题，下一步检查结构，最后再展开正文。原文还举了另一个更简单的例子：先生成营销文案，再翻译成另一种语言。

拆分的价值在于，**每次调用面对的问题更集中，中间结果也更容易检查**。如果正文偏离预期，可以进一步定位是大纲本身有问题，还是正文没有遵循大纲。

**Gate：先检查，再决定是否继续**

链条不必只是一路向下。程序可以在中间加入 Gate，也就是检查关口。例如，检查大纲是否覆盖指定主题、是否包含必要章节；通过才写正文，不通过则返回修改或终止。

原文强调的是程序化检查。结构完整性、字段和长度等条件，可以直接由代码验证；如果检查的是论述质量，也可以增加一次模型评价，但评价标准仍需要事先说明。这样做是为了避免前一步已经跑偏，后面的调用还继续扩写。

**适合什么任务，代价是什么？**

它适合步骤稳定、前后有依赖，而且拆分后每一步确实更容易完成的任务。代价是串行调用增加，等待时间与成本通常也随之上升。如果一次调用已经足够好，拆成三步未必更划算。

**记住它的结构：固定顺序，逐步处理，中间可以检查。**

## 4. Routing：先分类，再选择处理路线

Prompt Chaining 关心的是“下一步做什么”，Routing 关心的是：**这条输入应该交给哪一种处理流程？**

**怎么工作？**

假设客服系统要处理普通咨询、退款申请和技术问题。可以先由 Router 判断类别，再进入对应路线：

> 用户问题 → Router 分类 → 咨询流程 / 退款流程 / 技术支持流程

普通咨询可能只需要查知识库；退款需要订单信息和业务规则；技术支持则需要故障排查。把它们分开，每条路线都可以使用更合适的 Prompt、工具和上下文。

**为什么要先分开？**

如果全部塞进一个通用 Prompt，优化退款规则时，可能影响普通咨询的回答；任务类型越多，规则之间也越容易互相干扰。Routing 的价值是**分离职责，再分别优化**，而不是单纯多加一次分类调用。

Router 不一定是 LLM，也可以是规则、传统分类模型或其他算法。还可以按难度路由：常见问题交给速度快、成本低的模型，复杂问题交给能力更强的模型。

**适合什么任务，代价是什么？**

它需要输入确实存在有意义的类别，而且分类能够比较准确。如果入口把技术问题分进退款流程，后面的处理再完善，也很难答对。分类本身也会增加一次处理，因此要看专门路线带来的收益是否值得。

**记住它的结构：先判断输入类型，再进入专门路线。**

## 5. Parallelization：可以独立做的事情同时做

有些工作不需要等待彼此的结果，可以同时执行，再汇总输出。原文把 Parallelization 分为 **Sectioning** 和 **Voting**。两者外形相近，但分工目的不同。

**Sectioning：不同子任务，分别处理**

例如审查一段代码，提前分成安全、并发和性能三个方向：

> 同一份代码 → 安全审查 / 并发审查 / 性能审查 → 汇总发现

每个调用只关注一个维度，既可以减少整体等待，也能让判断更集中。原文还举了用户请求处理与安全筛查并行的例子：一条分支负责回答，另一条专门检查请求是否合规。

这里的前提是子任务能够独立执行。如果性能分析必须先知道并发审查的结论，就不能把两者简单视为完全并行的工作。

**Voting：同一个任务，多次独立判断**

Voting 不按维度分工，而是让同一个任务产生多份判断。例如，用不同 Prompt 分别检查同一段代码是否存在漏洞，然后按规则汇总。

> 同一个问题 → 独立判断 A / B / C → 聚合结果

这里的“投票”不一定是简单多数决。原文的漏洞检查例子会使用不同 Prompt，分别寻找问题；内容分类则可以设置不同的投票门槛，平衡误报与漏报。具体怎样聚合，取决于任务希望得到什么结果。

**适合什么任务，代价是什么？**

不同工作可以独立拆开时，用 Sectioning；同一个问题需要多个角度或多次尝试时，用 Voting。并行可以降低总等待时间，但总调用量和 Token 消耗通常更高，最后还需要合理的汇总规则。

**记住区别：Sectioning 是不同事情分别做，Voting 是同一件事多次判断。**

## 6. Orchestrator-Workers：运行时决定怎么拆任务

Orchestrator-Workers 也有多个 Worker，最后也要汇总。但它与前面的固定并行分工有一个关键区别：**子任务不是提前列好的，而是读完当前输入才决定的。**

**怎么工作？**

一个中心 LLM，也就是 Orchestrator，先分析任务，拆出子任务并分派给 Worker，再综合它们的结果：

> 输入任务 → Orchestrator 动态拆分 → Workers 执行 → 综合结果

例如实现一个跨模块需求。有的需求需要改 Controller、Service 和数据库迁移；另一个需求可能只涉及缓存配置和回归测试。不能提前规定每次都让三个 Worker 修改同样的三个模块，拆分方式必须取决于当前代码和需求。

这也是它与固定 Sectioning 的区别。安全、并发、性能审查是预先确定的分工维度；具体需求涉及哪些文件、各文件怎么改，则需要分析当前任务才能知道。

**为什么原文仍把它归为 Workflow？**

动态发生在“拆出什么子任务”这一层，外围仍然可以遵循预定义的“分析 → 分派 → 汇总”结构。**局部由模型决定，不代表整个执行过程都交给了模型。** 这解释了为什么它虽然灵活，仍被原文列在 Workflow 中。

**适合什么任务，代价是什么？**

它适合可以分解，但无法提前预测具体子任务的复杂工作，例如多文件代码修改、跨来源信息搜索。相比固定分工，它多了分析任务、安排 Worker 和综合结果的调用，换来的是按当前输入调整分工的灵活性。

**记住区别：固定并行提前知道怎么分，Orchestrator-Workers 运行时才决定怎么分。**

## 7. Evaluator-Optimizer：根据明确反馈改进结果

前面几种模式主要讨论任务怎么走、怎么分。Evaluator-Optimizer 解决的是：**第一份结果还不够好，怎样有方向地修改？**

**怎么工作？**

一个调用负责生成结果，另一个负责评价并提出反馈，再把反馈交回生成环节：

> 生成候选 → 评价与反馈 → 根据反馈修改 → 再次评价

原文以文学翻译为例。初稿可能意思基本正确，但语气不合适、双关没有表达出来，或某些用词生硬。Evaluator 指出这些具体问题，Generator 再针对它们修改。

它不是反复要求“再写一次”。**反馈需要说明哪里不足，以及改进方向是什么**，这样下一轮生成才有依据。

**什么条件下反馈才有用？**

Anthropic 给出两个判断：人类提出明确反馈时，结果能够被明显改善；LLM 也有能力提供这类反馈。换句话说，任务要有可用的评价标准，评价者还要能识别与这些标准有关的问题。

如果只得到“很好”“还可以更好”这样的结论，循环很难产生有针对性的改善。能指出具体问题、指导下一轮修改的反馈，才是这个模式有价值的地方。

**适合什么任务，代价是什么？**

它适合存在清晰质量标准，而且反馈迭代能带来明显收益的任务。生成、评价和修改会增加调用次数与等待时间，因此要看这种改善是否值得额外开销。

**记住它的结构：生成 → 评价 → 按反馈修改，而不是无方向地重试。**

## 8. 五种 Workflow 放在一起，应该怎么看？

把它们放在一起时，我更关注各自解决的结构问题，而不是名字。可以用下面这张表快速对照：

| 模式 | 核心问题 | 适用的任务结构 |
| --- | --- | --- |
| Prompt Chaining | 怎样把任务逐步做好？ | 顺序固定，前一步输出供后一步使用 |
| Routing | 这条输入该交给谁？ | 类别明确，适合分开处理 |
| Parallelization | 哪些工作可以同时做？ | 子任务独立，或需要同一任务的多份判断 |
| Orchestrator-Workers | 这次应该拆成哪些任务？ | 拆分方式依赖当前输入 |
| Evaluator-Optimizer | 怎样进一步改善结果？ | 标准清楚，反馈能指导修改 |

这些模式可以组合，并不是只能选一个。例如，客服入口先 Routing，技术问题进入固定排查链，其中资料检索并行执行，最后再检查答案是否覆盖问题。它同时使用了分类、串行、并行和评价，但仍可以是一个 Workflow。

因此，**模式是组织任务的积木，不是整套系统只能贴一个的标签**。把每一部分为什么这样组织讲清楚，比把整套系统叫得更复杂更有用。

## 9. 什么时候 Workflow 不够，需要 Agent？

五种 Workflow 可以组织复杂任务，但基本执行结构仍由开发者提前设计。**如果问题是开放式的，所需步数难以预测，下一步还取决于刚获得的信息，就很难预先写出完整路径。** 这时才需要考虑 Agent。

例如调查“一个服务为什么突然变慢”。问题可能来自数据库、缓存、网络或最近一次部署。读到监控结果前，很难知道该走哪条排查路线；看完慢 SQL 后，也可能需要回头检查调用方的变化。

Agent 的价值就在这里：让模型依据新信息调整行动，而不是要求开发者提前列出所有可能分支。需要交给模型的，是这部分无法预先确定的执行路线。

## 10. Agent 怎样工作？

Agent 通常从用户给出的目标开始，必要时先澄清任务，再进入一个反馈循环：

> 目标 → 模型决定下一步 → 使用 Tool → 获得环境反馈 → 再次决定

以 Coding Agent 为例，它修改代码后运行测试，读到失败信息，再决定继续修复、补充调查，还是请求帮助。这里影响下一步的，是实际得到的结果，而不是模型对结果的预想。

原文把这种来自环境的反馈称为 **ground truth**，例如工具调用结果和代码执行输出。模型说“修好了”是一项判断，运行相关测试得到的结果，则是可以用来核对这一判断的观察。**行动改变环境，反馈再影响下一次行动。**

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 2 · Agent：依据环境反馈，持续决定下一步</figcaption>
<div tabindex="0" role="region" aria-label="图 2 · Agent：依据环境反馈，持续决定下一步" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg class="agents-flow" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="effective-agents-loop-title effective-agents-loop-desc" viewBox="0 0 640 470" style="display:block; width:100%; min-width:540px; height:auto; font-family:var(--font-sans); --node:light-dark(#e8f3fc,#142b3e); --condition:light-dark(#f4f9fe,#102333); --ink:light-dark(#235e89,#c0def4); --border:light-dark(#d0e0ed,#355167); --line:light-dark(#8e959d,#8295a6); --success:light-dark(#e5f6eb,#152f26); --success-ink:light-dark(#286447,#a9debf); --success-border:light-dark(#afd3bc,#426c57); --warn:light-dark(#fff3d7,#352918); --warn-ink:light-dark(#8b5b22,#f3ce8d); --warn-border:light-dark(#e8c98e,#80663a);">
<title id="effective-agents-loop-title">Agent 的环境反馈循环</title>
<desc id="effective-agents-loop-desc">目标进入模型，模型决定下一步行动，使用工具并读取实际环境反馈，再依据反馈做下一次决定。必要时向人类求助并获得反馈；任务完成或达到停止条件时结束。</desc>
<defs><marker id="effective-agents-loop-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<g fill="none" stroke="var(--line)" stroke-width="1.2" marker-end="url(#effective-agents-loop-arrow)"><path d="M251 70 V116"/><path d="M251 194 V248"/><path d="M251 310 V366"/><path d="M136 405 H78 Q66 405 66 393 V168 Q66 156 78 156 H136"/><path d="M366 140 H452"/><path d="M366 164 H426 Q438 164 438 176 V268 Q438 280 450 280 H454"/><path d="M454 296 H414 Q402 296 402 284 V198 Q402 186 390 186 H366"/></g>
<rect x="136" y="18" width="230" height="52" rx="20" fill="var(--node)" stroke="var(--border)"/>
<text x="251" y="50" text-anchor="middle" fill="var(--ink)" font-size="17" font-weight="500">目标</text>
<rect x="136" y="118" width="230" height="76" rx="20" fill="var(--node)" stroke="var(--border)"/>
<text x="251" y="149" text-anchor="middle" fill="var(--ink)" font-size="17" font-weight="500">模型决定下一步</text>
<text x="251" y="176" text-anchor="middle" fill="var(--ink)" font-size="13">依据当前状态与已有反馈</text>
<text x="269" y="228" fill="var(--ink)" font-size="13">继续行动</text>
<rect x="136" y="250" width="230" height="60" rx="20" fill="var(--node)" stroke="var(--border)"/>
<text x="251" y="286" text-anchor="middle" fill="var(--ink)" font-size="17" font-weight="500">使用 Tool</text>
<text x="269" y="344" fill="var(--ink)" font-size="13">读取实际结果</text>
<rect x="136" y="368" width="230" height="74" rx="20" fill="var(--node)" stroke="var(--border)"/>
<text x="251" y="399" text-anchor="middle" fill="var(--ink)" font-size="17" font-weight="500">获得环境反馈</text>
<text x="251" y="426" text-anchor="middle" fill="var(--ink)" font-size="13">工具结果 · 执行输出 · 错误信息</text>
<text x="44" y="290" text-anchor="middle" fill="var(--ink)" font-size="13" transform="rotate(-90 44 290)">根据反馈，再决定</text>
<rect x="454" y="106" width="170" height="70" rx="20" fill="var(--success)" stroke="var(--success-border)"/>
<text x="539" y="134" text-anchor="middle" fill="var(--success-ink)" font-size="12">完成 / 达到停止条件</text>
<text x="539" y="160" text-anchor="middle" fill="var(--success-ink)" font-size="16" font-weight="500">结束并返回结果</text>
<text x="438" y="225" text-anchor="middle" fill="var(--ink)" font-size="12">必要时</text>
<text x="392" y="242" text-anchor="end" fill="var(--ink)" font-size="11">人类反馈</text>
<rect x="454" y="250" width="170" height="60" rx="20" fill="var(--warn)" stroke="var(--warn-border)"/>
<text x="539" y="286" text-anchor="middle" fill="var(--warn-ink)" font-size="16" font-weight="500">请求人类帮助</text>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">环境中的实际结果进入下一轮判断。窄屏可在图内左右滑动查看。</div>
</figure>

**人类检查点和停止条件，也是循环的一部分。** Agent 可以在关键环节向人类获取反馈，遇到阻塞时请求帮助；任务完成后返回结果，也可以由最大迭代次数等条件终止执行。它不是一个必须一直运行下去的循环。

这样的执行方式也带来更高成本，以及错误累积的可能：一次误判可能影响后续搜索、修改和判断。环境反馈与人类检查点让系统有机会及时调整路线，但自主执行并不意味着每一步都会正确。

## 11. Workflow 还是 Agent：最终怎么选？

可以按下面的顺序判断：

1. **一次调用已经足够，就保持简单。** 先优化 Prompt，补充检索信息和上下文示例，不必为了多步而引入多步系统。
2. **整体路线能提前设计，就选择 Workflow。** 根据任务结构安排串行、分类、并行、动态拆分或反馈迭代，让模型在明确的结构内完成工作。
3. **路线必须在运行时探索，再考虑 Agent。** 当下一步高度依赖环境反馈，固定路径难以覆盖任务时，模型的自主决策才有明确价值。

这不是从“低级”到“高级”的升级顺序。一个复杂任务也可能有明确流程，而一句话描述的任务可能需要开放探索。**任务复杂程度，与执行路径能否预先确定，是两件不同的事。**

最终还要比较任务质量、成本和延迟：新增调用、Worker 或自主性，是否真的改善了结果？对我来说，这篇原文给出的选型主线很清楚：**先看任务结构，再安排控制方式；复杂度只有改善结果时，才值得增加。**

## 几个关键问题，串起这些模式

把前面的模式放在一起，有几个问题能帮助说明它们之间的联系与区别。

**调用了工具、执行了很多步，就算 Agent 吗？**

不一定。“检索 → 生成 → 检查”可以完全由程序编排。按本文采用的定义，要看模型是在预设结构里完成任务，还是根据环境反馈持续决定接下来采取什么行动。调用次数和工具数量，不能单独说明这一点。

**Parallelization 和 Orchestrator-Workers 都有多个 Worker，区别在哪里？**

看具体子任务是否提前确定。预先安排安全、并发和性能三个审查方向，是固定的并行分工；读完当前需求后，才决定涉及哪些模块、分别交给谁处理，是 Orchestrator-Workers。区别在拆分方式，不在 Worker 数量。

**Sectioning 和 Voting 都是并行，为什么要分开？**

Sectioning 是分工：不同调用解决不同子问题。Voting 是增加判断视角：同一个问题产生多份结果，再按规则汇总。前者关注如何拆工作，后者关注如何综合同一任务的多份判断。

**Orchestrator-Workers 能动态拆任务，Evaluator-Optimizer 也会循环，为什么仍是 Workflow？**

因为局部决策可以是动态的，整体结构仍然可以由程序预先规定。前者遵循“拆分 → 分派 → 汇总”，后者遵循“生成 → 评价 → 修改”。模型在这些结构内做判断，并不意味着它已经主导整个执行过程。动态拆分和循环，都不是 Agent 独有的特征。

**怎样判断增加自主性是否值得？**

要和更简单的方案比较：它是否解决了原先难以覆盖的任务，质量提升了多少，又增加了多少成本、延迟和失败风险。Workflow 能稳定完成的部分，可以继续交给程序；真正需要边执行边探索的部分，再交给 Agent。选择依据是任务收益，不是模式名称。

## 参考与说明

- [Anthropic — Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
- 本文按原文的架构划分整理，示例用于解释任务结构；示意图为重新绘制的学习图，不是原图复刻。
