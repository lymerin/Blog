---
title: '不是所有多步 LLM 都叫 Agent：读 Anthropic《Building effective agents》'
description: '从控制权、任务拆分和环境反馈出发，理解 Workflow 与 Agent 的区别，以及多模型协作、工具接口和自主执行中的边界与取舍。'
pubDate: 2026-10-08T17:45:04+08:00
category: notes
tags: [Agent, LLM, Workflow, Tool Engineering, 学习笔记]
draft: false
postType: metaOnly
---

之前做开源修改时，我会让不同模型辅助检查代码、对照方案。这些经历让我对模型如何分工、意见如何汇总，以及最终由谁决定下一步产生了兴趣。读 Agent 相关资料时，我也格外关注这些问题在系统里是怎样被组织起来的。

一个应用接了 LLM 和 Tool，连续跑几步，就算 Agent 吗？把任务交给几个模型，是 Multi-Agent，还是一个并行 Workflow？如果模型还会根据反馈修改结果，区别又在哪里？

带着这些问题读 [Anthropic 的《Building effective agents》](https://www.anthropic.com/engineering/building-effective-agents)，我觉得最值得展开的是一个观察系统的角度：**先看谁决定下一步，再看它用了多少模型、多少工具。**

这篇笔记以原文的架构划分为线索，结合具体例子，展开我对控制权、环境反馈和工具接口的理解。后半部分再把几个相关问题放在一起，讨论这些概念落到具体场景时的边界与取舍。

## 控制权比调用次数，更能说明系统怎么工作

按原文的划分，Workflow 由预定义的代码路径组织模型和工具；Agent 则由模型动态主导执行过程和工具使用。本文沿用这一口径，方便在同一组概念下讨论不同结构。

工具调用、多步执行和循环，都可以出现在两类系统中。例如，“提取需求 → 检索 → 生成答案”完全可以由程序预先编排，模型负责完成各个节点。仅凭执行了多少步，还看不出谁在主导整个过程。

动态决策也需要区分发生在哪一层。Routing 可以让 LLM 判断输入属于账号、退款还是技术问题；Orchestrator-Workers 可以让模型按输入拆出子任务。它们仍然被原文列在 Workflow 里。**一个节点可以动态判断，不代表模型已经获得了整个系统的控制权。**

我区分两者时，更关注这个问题：模型是在程序限定的分支里做选择，还是能根据环境反馈持续选择行动、改变执行路径？现实系统也可以混合两者，因此按不同层次说明控制权，比给整个产品贴一个互斥标签更有解释力。

## 能力是底座，模式不是升级阶梯

原文把具备检索、工具和记忆等增强能力的模型称为 **Augmented LLM**。RAG、Tool Calling、Memory 描述的是它能获得什么信息、做什么事，并不单独决定系统属于哪一种架构。

Chaining、Routing、Parallelization 等模式适合解决不同的问题。把它们连成一条通向 Agent 的长链，容易掩盖这种差异：有的任务需要稳定的步骤，有的需要分类，有的需要并行处理，并不是自主性越高就越合适。

我更倾向于把它们看成共享同一能力底座的控制结构，再根据任务需要选择和组合。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 1 · 共享能力底座，选择不同控制结构；不是从左向右升级</figcaption>
<div tabindex="0" role="region" aria-label="图 1 · 能力底座与控制结构" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg class="agents-flow" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="effective-agents-patterns-title effective-agents-patterns-desc" viewBox="0 0 640 420" style="display:block; width:100%; min-width:540px; height:auto; font-family:var(--font-sans); --node:light-dark(#e8f3fc,#142b3e); --condition:light-dark(#f4f9fe,#102333); --ink:light-dark(#235e89,#c0def4); --border:light-dark(#d0e0ed,#355167); --line:light-dark(#8e959d,#8295a6); --success:light-dark(#e5f6eb,#152f26); --success-ink:light-dark(#286447,#a9debf); --success-border:light-dark(#afd3bc,#426c57);">
<title id="effective-agents-patterns-title">能力底座与控制结构</title>
<desc id="effective-agents-patterns-desc">检索、工具和记忆增强 LLM。在这些基础能力上，可以组织预定义 Workflow，也可以构造模型根据反馈动态选择动作的 Agent。两类结构可以混合，五种 Workflow 模式之间没有必然升级顺序。</desc>
<defs><marker id="effective-agents-patterns-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<rect x="104" y="18" width="432" height="84" rx="20" fill="var(--node)" stroke="var(--border)"/>
<text x="320" y="52" text-anchor="middle" fill="var(--ink)" font-size="18" font-weight="500">Augmented LLM</text>
<text x="320" y="81" text-anchor="middle" fill="var(--ink)" font-size="14">Retrieval · Tools · Memory</text>
<g fill="none" stroke="var(--line)" stroke-width="1.2" marker-end="url(#effective-agents-patterns-arrow)"><path d="M320 102 V130 Q320 142 308 142 H174 V168"/><path d="M320 102 V130 Q320 142 332 142 H466 V168"/></g>
<rect x="24" y="170" width="300" height="218" rx="20" fill="var(--condition)" stroke="var(--border)"/>
<text x="174" y="205" text-anchor="middle" fill="var(--ink)" font-size="18" font-weight="500">Workflow</text>
<text x="174" y="232" text-anchor="middle" fill="var(--ink)" font-size="13">程序编排，可在节点内动态判断</text>
<text x="174" y="271" text-anchor="middle" fill="var(--ink)" font-size="14">Prompt Chaining · Routing</text>
<text x="174" y="303" text-anchor="middle" fill="var(--ink)" font-size="14">Parallelization</text>
<text x="174" y="335" text-anchor="middle" fill="var(--ink)" font-size="14">Orchestrator-Workers</text>
<text x="174" y="367" text-anchor="middle" fill="var(--ink)" font-size="14">Evaluator-Optimizer</text>
<rect x="352" y="170" width="228" height="218" rx="20" fill="var(--success)" stroke="var(--success-border)"/>
<text x="466" y="205" text-anchor="middle" fill="var(--success-ink)" font-size="18" font-weight="500">Agent</text>
<text x="466" y="232" text-anchor="middle" fill="var(--success-ink)" font-size="13">模型动态主导行动过程</text>
<text x="466" y="278" text-anchor="middle" fill="var(--success-ink)" font-size="15">判断 → 行动</text>
<text x="466" y="317" text-anchor="middle" fill="var(--success-ink)" font-size="15">观察 → 调整</text>
<text x="466" y="362" text-anchor="middle" fill="var(--success-ink)" font-size="13">反馈循环 + 执行边界</text>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">按原文概念重新整理的学习图，不是原图复刻。窄屏可在图内左右滑动查看。</div>
</figure>

例如，一个系统可以先 Routing，再进入一个固定流程；其中某一步需要开放探索时，再嵌入 Agent。选模式不是排等级，而是回答“哪一部分需要什么自由度”。

## 五种 Workflow，解决的是不同问题

把模式放回具体任务里，它们各自解决的问题就更清楚了。

| 模式 | 任务需要解决什么 | 一个便于理解的例子 |
| --- | --- | --- |
| Prompt Chaining | 能否拆成稳定的固定步骤？ | 生成提纲 → 程序检查 → 写正文 |
| Routing | 不同输入是否需要不同处理？ | 账号、退款、技术问题分别处理 |
| Parallelization | 是否有独立部分，或需要多次尝试？ | 分维度检查，或多份结果聚合 |
| Orchestrator-Workers | 子任务要读完输入才能确定吗？ | 根据 Issue 决定分派哪些文件的工作 |
| Evaluator-Optimizer | 标准够清楚，反馈能改善结果吗？ | 生成候选 → 评价 → 有针对性地修改 |

**Prompt Chaining** 不只是把一个大 Prompt 切成几个小 Prompt。中间的检查也重要：提纲不满足要求时，不应该直接把它传给正文生成。多次调用能否改善质量，要看拆分是否有帮助，而不是步骤越多越好。

**Routing** 的价值在于职责分离。一个通用 Prompt 同时处理很多业务，修改某一类规则可能影响其他类别；分开处理则更容易分别优化。与此同时，入口分类的准确性也会影响后续结果，因此 Router 本身也需要被评估。

**Parallelization** 中的 Sectioning 和 Voting 也不能混为一谈。前者把不同部分分给不同调用，例如安全、并发、API 兼容性三个检查维度；后者对同一个任务产生多份结果，再按规则聚合。几个调用独立运行，不意味着错误也在统计上独立。大家读着同一份不完整上下文，也可能一起漏掉同一个问题。

**Orchestrator-Workers** 可以帮助理解一些 Subagent 系统的任务组织方式。与预先安排好的并行分支相比，它把“这次该拆哪些子任务”交给模型。但外围依然可以是固定的“拆分—分派—汇总”结构，所以原文仍称它为 Workflow。动态产生任务内容，不等于每个 Worker 都能自由行动。

**Evaluator-Optimizer** 体现了另一种控制结构：生成、评价、修改组成一个预先定义的循环。这里的重点是评价标准是否有效，以及迭代有没有带来可观察的改进；如果只是让另一个模型说“很好”，循环本身并没有增加多少可信度。

## 模型数量、调用次数与 Multi-Agent，是不同的维度

模型配置、调用方式和执行主体的组织方式，描述的是系统的不同侧面。

“多模型”描述选用了哪些模型；“多次调用”描述运行了几次；“Multi-Agent”则涉及如何定义执行主体，以及它们怎样分工和协作。讨论 Multi-Agent 时，需要先说明采用的 Agent 定义，再看角色背后的执行机制。

一个 Agent 可以按需要调用不同模型；多个执行主体也可以共享同一个模型。一个固定 Workflow 还可以编排多个有自己工具循环的 Worker。**调用结构和控制权结构，需要分开看。**

理解一个多 Agent 系统，可以顺着几个具体问题展开：子任务是谁拆的？Worker 有自己的状态和行动循环吗？什么时候返回给主流程？失败由谁处理？这些信息说明了主体之间怎样协作，也让“多 Agent”不再只是一个名称。

## 环境反馈让判断可核验，但不替代验收

Agent 常见的循环是：读取目标和当前状态，选择动作，执行工具，拿到反馈，再决定下一步。这个循环的关键，在于实际执行结果能够进入上下文，影响后续判断。

比如 Coding Agent 改完代码后，应该运行相关检查，读取结果，再判断是否继续。它说“我已经修好了”，只是一个判断；测试退出状态和实际输出，才是来自环境的观察。

环境反馈也有自己的证据范围。测试通过，说明这些测试在这个环境里通过了；工具成功接受命令，说明请求已被接受。它们是否足以支持“任务完成”，还取决于验收目标。这里的 ground truth，我理解为**用来校验行动的外部反馈**，需要结合来源、可信度和覆盖范围来使用。

沿着这个循环，还可以区分行动判断与执行约束：模型提出动作，运行时检查权限、预算和停止条件。下面的图在原文反馈循环的基础上加入了这层执行边界。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 2 · 模型根据反馈选动作，运行时守住执行边界</figcaption>
<div tabindex="0" role="region" aria-label="图 2 · 有执行边界的 Agent 循环" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg class="agents-flow" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="effective-agents-loop-title effective-agents-loop-desc" viewBox="0 0 640 540" style="display:block; width:100%; min-width:540px; height:auto; font-family:var(--font-sans); --node:light-dark(#e8f3fc,#142b3e); --condition:light-dark(#f4f9fe,#102333); --ink:light-dark(#235e89,#c0def4); --border:light-dark(#d0e0ed,#355167); --line:light-dark(#8e959d,#8295a6); --warn:light-dark(#fff3d7,#352918); --warn-ink:light-dark(#8b5b22,#f3ce8d); --warn-border:light-dark(#e8c98e,#80663a); --success:light-dark(#e5f6eb,#152f26); --success-ink:light-dark(#286447,#a9debf); --success-border:light-dark(#afd3bc,#426c57);">
<title id="effective-agents-loop-title">有执行边界的 Agent 循环</title>
<desc id="effective-agents-loop-desc">目标和状态进入模型上下文，模型提出下一步动作或完成判断。完成时返回结果；动作先经过运行时的权限、预算和步数检查，拒绝、超限或阻塞时停止或人工接管，允许时执行工具。结果和错误作为观察更新上下文，回到模型判断。反馈仍需要检查可信度和覆盖范围。</desc>
<defs><marker id="effective-agents-loop-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<text x="276" y="27" text-anchor="middle" fill="var(--ink)" font-size="14">目标 + 当前状态</text>
<g fill="none" stroke="var(--line)" stroke-width="1.2" marker-end="url(#effective-agents-loop-arrow)"><path d="M276 36 V54"/><path d="M276 126 V184"/><path d="M276 256 V312"/><path d="M276 372 V428"/><path d="M156 464 H84 Q72 464 72 452 V104 Q72 90 86 90 H156"/><path d="M396 90 H452"/><path d="M396 220 H452"/></g>
<rect x="156" y="56" width="240" height="70" rx="20" fill="var(--node)" stroke="var(--border)"/>
<text x="276" y="86" text-anchor="middle" fill="var(--ink)" font-size="17" font-weight="500">模型决定下一步</text>
<text x="276" y="112" text-anchor="middle" fill="var(--ink)" font-size="13">读取上下文，提出动作或完成判断</text>
<text x="296" y="161" text-anchor="start" fill="var(--ink)" font-size="13">动作请求</text>
<rect x="156" y="186" width="240" height="70" rx="20" fill="var(--condition)" stroke="var(--border)" stroke-dasharray="3 4"/>
<text x="276" y="216" text-anchor="middle" fill="var(--ink)" font-size="16" font-weight="500">运行时检查边界</text>
<text x="276" y="242" text-anchor="middle" fill="var(--ink)" font-size="13">权限 · 预算 · 最大步数</text>
<text x="296" y="292" text-anchor="start" fill="var(--ink)" font-size="13">允许执行</text>
<rect x="156" y="314" width="240" height="58" rx="20" fill="var(--node)" stroke="var(--border)"/>
<text x="276" y="349" text-anchor="middle" fill="var(--ink)" font-size="16" font-weight="500">工具 / 环境执行动作</text>
<text x="296" y="407" text-anchor="start" fill="var(--ink)" font-size="13">读取实际结果，而非预期结果</text>
<rect x="156" y="430" width="240" height="70" rx="20" fill="var(--node)" stroke="var(--border)"/>
<text x="276" y="460" text-anchor="middle" fill="var(--ink)" font-size="16" font-weight="500">取得 Observation</text>
<text x="276" y="486" text-anchor="middle" fill="var(--ink)" font-size="13">结果 · 错误 · 状态</text>
<text x="50" y="294" text-anchor="middle" fill="var(--ink)" font-size="13" transform="rotate(-90 50 294)">更新上下文，再判断</text>
<rect x="454" y="56" width="162" height="70" rx="20" fill="var(--success)" stroke="var(--success-border)"/>
<text x="535" y="86" text-anchor="middle" fill="var(--success-ink)" font-size="16" font-weight="500">完成并返回</text>
<text x="535" y="112" text-anchor="middle" fill="var(--success-ink)" font-size="12">核对任务完成条件</text>
<rect x="454" y="186" width="162" height="70" rx="20" fill="var(--warn)" stroke="var(--warn-border)"/>
<text x="535" y="216" text-anchor="middle" fill="var(--warn-ink)" font-size="15" font-weight="500">停止 / 人工接管</text>
<text x="535" y="242" text-anchor="middle" fill="var(--warn-ink)" font-size="12">拒绝 · 超限 · 阻塞</text>
<text x="422" y="75" text-anchor="middle" fill="var(--ink)" font-size="12">完成</text>
<text x="426" y="204" text-anchor="middle" fill="var(--ink)" font-size="12">停止</text>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">权限与预算门是我的工程延伸；反馈也要检查可信度。窄屏可在图内左右滑动查看。</div>
</figure>

这些约束明确了模型在哪些范围内可以自主行动，以及什么时候需要交还控制权。完成条件、最大迭代数、卡住时如何求助，都属于执行机制的一部分。动态路径越多，越需要保留可回看的判断依据与工具结果。

## Tool 不只是接 API，也是给模型设计接口

原文附录中的 **ACI（Agent-Computer Interface）** 是我很喜欢的一点。它把注意力从模型本身，延伸到了模型怎样理解并使用环境。工具接口的设计，会直接影响模型能否选对动作、填对参数、读懂结果。

一个工具应该清楚说明它做什么、参数代表什么、什么时候不能用、失败会返回什么。两个名称很像的工具如果边界不清，模型很容易选错；返回一大段无关信息，也可能让后续判断被噪声淹没。

原文举了一个路径的例子：Agent 改变工作目录后会误用相对路径，工具改为要求绝对路径后，这类错误被消除了。对我来说，这个例子说明了接口可以主动减少歧义。当问题来自参数语义时，改进接口可能比继续补充 Prompt 更直接。

参数清晰与访问授权又是两回事：**更明确的参数不等于更大的权限**。即使用绝对路径，运行时仍需要检查它是否落在允许访问的范围里。前者减少理解歧义，后者约束实际操作，分别解决不同层面的问题。

评价工具接口，也不能只看一次调用是否成功。正常参数、歧义参数、执行失败，以及“命令已提交但最终状态还不确定”，都对应不同的反馈需求。好的接口既要让模型完成正常操作，也要让它读懂失败与不确定状态，判断是否需要查询、重试或交还控制权。

## 看懂模式之后，还要想清楚边界与取舍

把这些模式放在一起看，我更关注的是它们背后的控制权、反馈和执行边界。比如，动态拆分任务与自主决定执行路径有什么区别？多个模型意见一致，能说明什么，又不能说明什么？这些问题把不同架构之间的边界联系了起来，下面逐一展开。

**1. Router 用 LLM 选分支，为什么仍可能是 Workflow？**

模型决定某个节点的输出，不等于主导整体执行过程。如果类别和后续路径由程序限定，分类仍是编排中的一个步骤。

**再往下想：** 如果 Router 可以创建新分支、自由选工具并持续重试，原来的控制权边界会怎样变化？

**我的理解：** 要看它能改变的是“分支内容”，还是“后续执行过程”。如果只是生成一个子任务，接下来仍由程序按固定步骤执行，它依然可以是 Workflow；如果模型还能根据反馈选择下一步工具、调整路径并决定何时结束，这一部分就更接近原文所说的 Agent。控制权从程序预定的路径，转向了模型的行动判断，但权限、重试次数和预算仍应由运行时限制。自主选动作，不等于拥有无限执行权限。

**2. 动态拆任务，为什么也不自动等于 Agent？**

Orchestrator 可以动态确定子任务，外围仍按分解、分派、汇总运行。要继续看 Worker 是否拥有自己的行动循环，以及主流程允许它改变哪些东西。

**再往下想：** 一个固定 Workflow 编排多个 Agent Worker，应该怎样描述这个混合系统，而不是只选一个标签？

**我的理解：** 这个系统可以描述为“外层是固定 Workflow，内部某些节点由 Agent Worker 完成”。外层负责分派、汇总和验收，Worker 则在自己的任务范围内根据反馈选工具、迭代执行。分别说明两层的状态、停止条件和失败处理，就能讲清它们的关系。Worker 的自主性与外层的固定编排可以同时存在。

**3. 多次 Voting 都同意，为什么不能直接当成事实？**

不同调用可能共享同一种盲点。多数一致说明意见一致，是否提高正确率还需要评测。聚合规则也应匹配业务：漏洞检查中，一个有效问题不该只因其他调用没发现就被丢掉。

**再往下想：** 采用多数票，还是任一报告都送审？怎样比较误报、漏报和人工审查成本？

**我的理解：** 投票规则需要结合业务目标来评价。带有人工核验结果的样本，可以用来比较不同规则的误报、漏报、审查量和成本。漏掉严重漏洞的代价很高时，可以让任一有效报告进入复核，但“送审”不等于直接判定有漏洞；低风险任务如果误报很多，也可以提高送审门槛。多数票与送审门槛都是取舍，依据是错误的影响与复核成本。

**4. 测试全绿，为什么还不能直接宣布任务完成？**

外部反馈有覆盖范围。测试通过不代表需求完整，更不能允许模型通过降低断言或删除失败用例来“完成任务”。完成标准要和用户目标对应，而不是只和退出码对应。

**再往下想：** Agent 同时能修改代码和测试时，哪些验收依据应该独立保留？

**我的理解：** 需求与验收标准，以及独立评测流程中的关键回归用例，应当与 Agent 的自由修改范围分开。Agent 可以补测试，但不能靠删除失败用例、放松断言或改掉评测配置来证明自己完成了任务。如果原测试确实有问题，修改理由也需要单独审查。涉及兼容性、权限或数据安全的改动，人工 Review 仍有价值；代码与测试相互吻合，不一定代表它们符合原来的目标。

**5. Evaluator-Optimizer 为什么可能越改越差？**

如果评价标准与目标错位，生成者可能只是更迎合评审。明确评价依据、设置迭代预算、保留不同候选，并用独立检查比较实际质量，才能判断修改是否值得保留。

**再往下想：** 同一个模型负责生成和评价，可能有哪些共同盲点？怎样判断迭代真的带来了改善？

**我的理解：** 两次调用可能都误解同一条需求，也可能偏爱同一种表达，甚至把“更完整、更流畅”误当成“更正确”。换一个模型可以增加视角，但也不能自动消除这些盲点。保留初始结果和中间候选，在不参与修改过程的评测任务上比较，再结合可执行检查或人工盲评，可以获得更独立的依据。评价需要落到与任务目标一致的外部指标上，评审模型分数上涨本身还不够。

**6. 怎样证明有必要增加 Agent 的自主性？**

先保留简单方案作为基线，在同一组任务上比较完成质量、成本、延迟和失败类型。方案变复杂，需要有实际收益，而不是因为名称更先进。

**再往下想：** 平均成功率提高，但高风险错误也增多，是否仍然值得采用？

**我的理解：** 平均值需要和失败的影响程度一起看。普通回答不够好，和误删数据、越权操作，不应该用同一个成功率数字抵消。如果高风险错误超过可接受的上限，就需要收紧工具权限，或让关键动作经过人工确认，再评价调整后的效果。也可以只在低风险部分使用 Agent，把高风险部分留在确定性流程里。是否值得采用，取决于收益和风险边界，而不是哪一组平均分更高。

**7. 工具调用失败，应该改 Prompt 还是改接口？**

先定位失败发生在选工具、填参数、执行还是理解反馈。参数反复歧义可能需要改接口；真实执行失败则需要可理解的错误和恢复路径，不能统一归因于模型能力。

**再往下想：** 写操作超时后能直接重试吗？

**我的理解：** 超时表示客户端没有及时拿到结果，不等于服务端没有执行。直接重复提交可能产生两笔订单或两次写入，因此需要先核对操作状态。如果接口明确支持幂等请求，就在它约定的有效范围内，用同一个请求标识和相同参数重试，让服务端识别这是同一次操作；重新生成标识反而可能变成一次新请求。没有幂等保障、状态又不明确时，应先核对或交给人工处理，而不是盲目循环重试。

**8. 多模型、多次调用、多 Agent 有什么区别？**

它们分别描述模型配置、调用次数和执行主体的组织方式。先说明自己对 Agent 的定义，再介绍状态、分工、通信和控制边界，比单纯数角色 Prompt 更可靠。

**再往下想：** 三个不同的角色 Prompt，是否就足以构成三个 Agent？还缺少哪些实现信息？

**我的理解：** 按本文采用的架构口径，角色名称还不能说明执行机制。“开发者、测试者、评审者”可能只是固定流程中的三次调用。区分它们，需要看每个执行主体是否能维护自己的任务上下文，是否会根据工具反馈选择下一步，以及它们怎样交接结果、处理失败和停止。若只是依次生成三段回答，描述成角色化 Workflow 更准确；若各自有行动循环，再由上层协调，才有理由讨论 Multi-Agent。它们不一定要用不同模型，也不一定需要不同进程。

## 自主性应该放在任务真正需要它的地方

这篇文章让我最有共鸣的，是把复杂度放回任务本身来判断。任务可以稳定拆分时，固定流程有它的优势；某一部分需要探索，就把自主性放在那里。一个复杂业务，也可以由清晰的流程和局部的自主执行共同完成。

回到开头的多模型协作，我更看重的是每份判断基于什么信息、意见怎样被核验，以及最终由谁作出行动决定。多一个模型可以增加视角，但视角的价值需要落实到证据和结果上。架构名称说明组织方式，不能代替对实际效果的判断。

我的理解可以归结为一句话：**先看任务需要模型决定什么，再决定系统应该给它多少自主性。** 控制权说明谁决定下一步，反馈说明决定依据什么，执行边界说明哪些动作可以发生。把这三者放在一起，才更容易解释一个 Agent 系统为什么这样设计。

## 参考与说明

- [Anthropic — Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)，2024 年 12 月 19 日。
- 写操作重试的延伸阅读：[AWS Builders’ Library — Making retries safe with idempotent APIs](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/)。
- Workflow 分类与 Agent 定义采用原文口径；示意图是我对笔记的重新组织。
- 权限执行、投票相关性、幂等重试与文中的进一步讨论属于学习延伸，不作为原文的逐字结论。
