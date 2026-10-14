---
title: 'Agent Guardrails：怎样自动判断一个动作是否应该执行？'
description: '以 Claude Code auto mode 为例，理解输入侧注入检测、动作分类器、两阶段判断与 Reasoning-blind 设计，再分析子 Agent 检查、拒绝后的恢复，以及误报和漏报的取舍。'
pubDate: 2026-10-14T18:19:56+08:00
category: notes
tags: [Agent, Anthropic, Security, 学习笔记]
draft: false
postType: metaOnly
---

[上一篇](/zh-cn/posts/agent-security/)区分了行为监督与环境隔离：前者判断动作是否合适，后者限制实际权限。这一篇深入前者——当 Agent 连续执行很多步骤，怎样用自动判断承担一部分审批工作？

难点不是识别几个危险命令。一个动作可能看起来很正常，也确实有助于完成任务，却仍然越过用户的授权。例如，修复测试不意味着可以寻找个人凭证，排查问题也不意味着可以把项目上传到外部服务。

Anthropic 的[《How we built Claude Code auto mode: a safer way to skip permissions》](https://www.anthropic.com/engineering/claude-code-auto-mode)介绍了这种自动审批的实现与取舍。本文先区分输入检测与动作判断，再解释分类器的信息选择和两阶段流程，最后讨论委派、拒绝恢复与误判。产品细节以该文发布时的实现为背景。

仍用一个假设任务贯穿说明：用户要求修复 CSV 解析问题并运行本地测试，没有要求上传代码、寻找其他账号的凭证，或修改共享服务。示例用来解释授权边界，不代表实际发生过的安全事件。

## 一、自动审批需要检查什么

自动审批不是简单地把“用户点 Allow”换成“另一个模型点 Allow”。它需要明确判断依据，也需要区分风险在执行链的什么位置出现。

### 1. 用户授权：任务目标与具体动作的关系

用户给出一个目标，Agent 再选择实现步骤。在这两者之间，可能出现 Overeager Behavior：Agent 想帮忙，却主动做了超出用户意图的事。

例如，测试依赖下载失败之后，下面几种动作都与“让测试跑起来”有关：

- 查看项目已经声明的依赖和安装说明。
- 报告当前认证错误，请用户确认需要使用的账号。
- 搜索个人配置中的其他凭证，尝试接入另一个服务。
- 关闭共享环境的检查，把修改直接部署上去验证。

它们的影响范围明显不同。**能够解释某个动作为什么有用，不等于用户已经授权了这个动作。** 自动判断需要关心目标、数据、身份和副作用，而不是只寻找“这与任务有关”的理由。

授权还需要对应具体对象。“清理旧分支”没有明确本地还是远端，“取消任务”也没有指明哪个共享任务。目标模糊时，依据名称相似度直接删除，比先核实目标多承担了一层风险。

这里的判断问题可以压成三项：动作实际上会做什么，影响哪些资源，当前用户请求是否覆盖了这些影响。它比对命令名称做黑名单匹配更接近真实的审批工作。

### 2. 输入与输出防线：检测内容和判断行动

原文的 auto mode 有两类检查：输入侧的 Prompt Injection Probe，以及执行前的 Transcript Classifier。前者检查工具返回内容，后者判断准备执行的动作。[来源：Anthropic](https://www.anthropic.com/engineering/claude-code-auto-mode)

**输入侧检查的是 Agent 将要读到什么。** 文件、网页、Shell 输出或外部工具返回，可能混入改变任务的指令。Probe 在这些结果进入 Agent Context 前检测可疑内容，必要时附加警告，引导 Agent 回到用户请求。

警告不是把资料全部删掉，也不等于危险内容从此无法影响模型。它是在信息进入决策之前，提醒模型区分资料与指令。

**输出侧检查的是 Agent 将要做什么。** 当 Agent 准备调用工具，分类器在执行前判断动作与用户授权、风险规则是否一致。即使输入侧漏过了某段文档，只要后续上传动作没有获得授权，输出侧仍有机会阻止它。

在 CSV 场景中，文档里的“上传整个项目才能排障”属于输入侧需要警惕的内容；Agent 据此提出上传请求，则属于输出侧要判断的动作。两次检查针对的是同一条风险链的不同环节，不是把同一个问题重复问两遍。

## 二、动作分类器怎样组织判断

分类器要发挥作用，不只取决于模型能力。哪些动作送进去、给它看哪些信息，以及怎样安排快速过滤与复核，都会影响最终表现。

### 3. Permission Routing：规则放行与分类器检查

并不是每一个工具调用都要再经过一次模型审批。原文描述了分层路径：内置与用户允许规则、项目内文件操作，可以先行放行；其余需要进一步判断的动作进入分类器。进入 auto mode 时，部分过宽的代码执行允许规则也会被移除，避免直接绕过检查。[来源：原文的权限路径](https://www.anthropic.com/engineering/claude-code-auto-mode)

这个设计解释了一个重要区别：**没有发生分类器调用，不一定意味着完全没有规则；但规则放行，也不能被描述成分类器已经审查过。**

以项目编辑为例，它可以属于日常开发路径；而随后运行一个脚本，可能产生上传、删除或远程变更，就需要关注执行效果。不能因为脚本是刚在项目内创建的，就把它视为安全。

类似地，如果一个允许规则覆盖了任意解释器执行，那么复杂行为都可以包装进程序里，绕过后面的动作判断。允许规则的范围因此是防线的一部分，不只是提高便利性的设置。

理解这条路径后，再看分类器成绩才有意义：它是在特定路由与规则下工作，而不是为所有调用逐一出具安全证明。

### 4. Reasoning-blind：保留授权依据，减少解释干扰

原文的分类器主要看用户消息与 Agent 的工具调用，去掉 Agent 自己的文字和工具返回内容。这就是这里的 Reasoning-blind：**不把执行者对自己行为的解释，当成审批依据。**

假设 Agent 准备上传代码，同时写了一段说明：“用户希望尽快修复，应该已经隐含同意上传。”如果分类器把这段说明当成事实，就可能被 Agent 自己生成的授权解释带偏。

保留用户消息，是为了锚定真实请求；保留工具调用，是为了检查具体动作。去掉工具返回，则减少了恶意文档直接影响审批器的机会。主 Agent 可能已经读过可疑内容，但审批器不必沿用它读到的那套叙事。

这不是完全没有 Context。此前的工具调用仍然可以构成行动记录。例如，Agent 通过写文件调用创建了脚本，脚本内容就可能出现在调用参数中；后续执行时，需要结合这些记录判断，而不是只看一个无害的文件名。

代价是来源信息变少。如果某个目标编号只出现在被过滤的查询结果中，分类器可能无法确认它是查出来的，还是 Agent 自己推断的。**减少被操纵的信息入口，与保留完整证据之间存在取舍。** Reasoning-blind 是一种信息选择，不是对所有判断质量的保证。

### 5. Two-stage Classification：快速过滤与推理复核

对进入分类器的动作，第一阶段快速标记可疑项，第二阶段只复核被标记的部分。第一阶段倾向谨慎，第二阶段用更充分的判断减少误报；它们不是两个同样严格的检查器依次盖章。

这里尤其要分清：第一阶段的“可疑”是升级复核信号，不是最终拒绝；没有被第一阶段标记的动作，则不会再获得第二阶段检查。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 1 · 两阶段分类：先快速筛选，再对可疑动作复核，不是所有动作都检查两遍</figcaption>
<div tabindex="0" role="region" aria-label="自动审批中的快速过滤、推理复核与最终决定" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="agent-guardrails-stages-title agent-guardrails-stages-desc" viewBox="0 0 640 460" style="display:block; width:100%; min-width:540px; height:auto; font-family:var(--font-sans); --node:light-dark(#e8f3fc,#142b3e); --condition:light-dark(#f4f9fe,#102333); --ink:light-dark(#235e89,#c0def4); --border:light-dark(#d0e0ed,#355167); --line:light-dark(#8e959d,#8295a6); --success:light-dark(#e5f6eb,#152f26); --success-ink:light-dark(#286447,#a9debf); --success-border:light-dark(#afd3bc,#426c57); --warn:light-dark(#fff3d7,#352918); --warn-ink:light-dark(#8b5b22,#f3ce8d); --warn-border:light-dark(#e8c98e,#80663a);">
<title id="agent-guardrails-stages-title">动作分类器的两阶段判断</title>
<desc id="agent-guardrails-stages-desc">图中只展示需要分类的动作。第一阶段快速过滤：未标记的动作通过行为检查，标记为可疑的动作进入第二阶段推理复核。复核可以放行，也可以拒绝并反馈原因。行为检查通过后仍受执行权限约束。</desc>
<defs><marker id="agent-guardrails-stages-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<g fill="none" stroke="var(--line)" stroke-width="1.2" marker-end="url(#agent-guardrails-stages-arrow)"><path d="M320 84 V130"/><path d="M170 166 H120 Q110 166 110 176 V370"/><path d="M470 166 H500 Q510 166 510 176 V242"/><path d="M378 278 H300 Q290 278 290 288 V338 Q290 348 280 348 H151 Q141 348 141 358 V370"/><path d="M501 314 V370"/></g>
<rect x="170" y="20" width="300" height="64" rx="20" fill="var(--node)" stroke="var(--border)"/>
<text x="320" y="47" text-anchor="middle" fill="var(--ink)" font-size="18" font-weight="500">需要分类的动作</text><text x="320" y="71" text-anchor="middle" fill="var(--ink)" font-size="14">用户消息 + 工具调用记录</text>
<rect x="170" y="130" width="300" height="72" rx="20" fill="var(--condition)" stroke="var(--border)" stroke-dasharray="3 3"/>
<text x="320" y="160" text-anchor="middle" fill="var(--ink)" font-size="18" font-weight="500">第一阶段：快速过滤</text><text x="320" y="186" text-anchor="middle" fill="var(--ink)" font-size="14">谨慎筛选 · 简短决定</text>
<text x="30" y="292" fill="var(--ink)" font-size="14">未标记</text><text x="526" y="220" fill="var(--ink)" font-size="14">标记可疑</text>
<rect x="378" y="242" width="246" height="72" rx="20" fill="var(--node)" stroke="var(--border)"/>
<text x="501" y="272" text-anchor="middle" fill="var(--ink)" font-size="17" font-weight="500">第二阶段：推理复核</text><text x="501" y="298" text-anchor="middle" fill="var(--ink)" font-size="14">重新判断风险与授权</text>
<text x="302" y="332" fill="var(--ink)" font-size="14">复核放行</text><text x="514" y="347" fill="var(--ink)" font-size="14">仍需阻止</text>
<rect x="16" y="370" width="250" height="72" rx="20" fill="var(--success)" stroke="var(--success-border)"/>
<text x="141" y="400" text-anchor="middle" fill="var(--success-ink)" font-size="18" font-weight="500">通过行为检查</text><text x="141" y="427" text-anchor="middle" fill="var(--success-ink)" font-size="14">仍受执行权限约束</text>
<rect x="378" y="370" width="246" height="72" rx="20" fill="var(--warn)" stroke="var(--warn-border)"/>
<text x="501" y="400" text-anchor="middle" fill="var(--warn-ink)" font-size="18" font-weight="500">拒绝并反馈原因</text><text x="501" y="427" text-anchor="middle" fill="var(--warn-ink)" font-size="14">寻找符合边界的替代路径</text>
</svg>
</div>
</figure>

两阶段的收益是把较贵的推理集中到少数动作上。相应地，第一阶段漏过的动作不会被第二阶段补救；第二阶段也可能把真正危险的动作重新放行。

因此，不能只根据“加入推理复核”推断更安全。它可能让正常任务少受打扰，却同时改变漏报率。最终要评价整个流程，而不是只评价某一个阶段。

## 三、委派与拒绝之后怎样继续执行

动作判断不只发生在单 Agent 的工具前。任务交给子 Agent、结果回到主 Agent，以及被拒绝之后继续尝试，都会改变授权和信息的流向。

### 6. Subagent Checks：委派授权与返回警告

委派有一个特殊问题：主 Agent 自己推导出的任务，进入子 Agent 后可能表现得像一条用户要求。

例如，用户只要求本地修复，主 Agent 却把“寻找可用凭证并上传日志”交给子 Agent。如果子 Agent 只看自己的任务消息，这项工作似乎已经被明确要求了。**主 Agent 的决定，不应该因为跨过一次委派，就升级成用户授权。**

原文在委派和返回两端设置检查：委派端可以阻止任务；返回端检查子 Agent 的行动历史，发现问题时附加安全警告，而不是直接丢弃结果。子 Agent 内部还运行相应的检查流程。[来源：原文的多 Agent 处理](https://www.anthropic.com/engineering/claude-code-auto-mode)

两端解决的问题不同。委派时检查的是工作是否本来就越界；返回时则要考虑，最初合理的任务是否在执行中被外部内容带偏。

返回警告也不意味着子 Agent 已经执行的副作用被撤销。它帮助主 Agent 对结果保持警惕，但不等同于文件回滚、取消上传或恢复远程状态。这再次说明，行为检测与执行边界承担不同职责。

### 7. Deny-and-continue：拒绝反馈与安全替代

一个动作被拒绝，不一定代表整个任务无法完成。对长任务来说，允许 Agent 理解拒绝原因并寻找替代步骤，比每次拒绝都终止更有用。

例如，上传项目被拒绝后，Agent 可以改为在本地提取最小失败样例，或者说明认证问题并请求用户确认。任务目标仍然保留，但实现路径收回到允许范围内。

这里需要区分“换一种方法完成任务”与“换一种包装完成被禁止的动作”。把上传从命令改成脚本，或换一个外部地址继续发送同一份资料，并没有解决拒绝原因。

原文把拒绝作为工具反馈返回，并设置累计拒绝的停止条件，避免无限尝试；达到条件后交给人工，无交互模式则终止。[来源：Deny-and-continue 设计](https://www.anthropic.com/engineering/claude-code-auto-mode)

这个机制也能缓冲误报：正常动作被误拦一次，任务未必就完全失败。但前提是 Agent 尊重拒绝边界，恢复策略不是反复试探怎样绕过检查。

## 四、怎样评价误判与剩余风险

自动审批同时追求安全性、任务自主性和较低干扰。只看“拦住了多少动作”或“弹窗减少了多少”，都不能完整评价这项设计。

### 8. FPR 与 FNR：误报、漏报与评估分母

False Positive Rate（FPR）是正常动作中被误拦的比例；False Negative Rate（FNR）是危险动作中被放行的比例。两者分母不同，不能把一个很低的 FPR 当成整体安全率。

在原文的测试中，快速阶段与完整流程得到下面的结果：

| 流程 | 真实流量上的 FPR | 真实过度主动动作上的 FNR |
| --- | --- | --- |
| 第一阶段 | 8.5% | 6.6% |
| 第一阶段 → 第二阶段 | 0.4% | 17% |

真实流量数据包含 10,000 次调用，过度主动动作集包含 52 个样本；两列对应不同数据集。数字来自 [Anthropic 原文评估](https://www.anthropic.com/engineering/claude-code-auto-mode)，不是所有任务上的固定表现。

这张表体现了两阶段设计的取舍：复核显著减少了正常任务被误拦的情况，但也放过了更多危险动作。因此，完整流程更少打扰用户，不等于它在每个安全指标上都优于第一阶段。

分析漏报时，还需要区分两个问题：分类器没有识别动作的危险性，还是识别了危险，却错误地认为用户同意承担这次影响？后一种问题不能只靠补充危险命令词表解决，它需要更准确地理解授权范围。

在教学场景中，即使分类器知道“上传项目”意味着数据外发，也可能把“帮我排障”误读成足够授权。评价行为防线时，既要检查动作理解，也要检查授权判断。

### 9. 部署边界：自动判断与强制隔离

自动分类器的价值取决于比较基线。与完全取消审批相比，它可以提供额外防线；与认真审查每个高影响动作相比，它不一定更可靠。

因此，不能因为某种模式减少了大量干扰，就把它直接用于所有任务。对共享资源、生产数据或高权限凭证，一次漏判的后果可能远高于日常项目编辑。任务环境与影响范围应当参与选择，而不只是看平均通过率。

同样，行为检查通过只表示判断器认为动作可以继续，不代表操作系统或远程服务必须允许它。Sandbox、文件权限、网络策略和凭证范围仍然需要限制实际能力。

回到 CSV 修复任务，自动判断负责尽量拦住无授权上传；环境边界则应该让项目外凭证不可见、未授权出口不可用。即使分类器被说服，执行层也不应因此自动扩大权限。

**这篇的核心不是让审批器永远判断正确，而是让判断依据清楚、失败可分析，并把漏判之后的影响交给独立的权限边界继续限制。**

## 几个关键问题，串起自动审批的判断依据

**动作有助于完成任务，为什么还可能需要阻止？**

任务相关性不是完整授权。寻找其他账号的凭证、上传代码或改变共享服务，都可能帮助排障，但带来了用户没有明确接受的影响。需要对应目标、身份、数据和副作用判断。

**输入侧检测与输出侧分类有什么区别？**

输入侧检查外部内容是否试图改变 Agent 行为，必要时附加警告；输出侧检查实际动作是否符合规则和授权。前者减少被带偏的机会，后者在行动前再次检查，不能互相替代。

**分类器不看工具结果，怎么理解 Agent 在做什么？**

它依靠用户消息和工具调用记录判断授权与行动，包括记录中可见的参数和代码。这样减少了恶意返回内容的影响，但可能失去目标来源等信息，是有代价的信息过滤。

**两阶段分类为什么不保证漏报更少？**

第二阶段只处理第一阶段标记的动作，不能补救第一阶段漏过的内容；它还可能把真正危险的动作重新放行。减少误报与减少漏报不是同一项改进。

**子 Agent 收到明确任务，为什么还要在委派端检查？**

因为明确任务可能是主 Agent 自己推导的，而不是用户授权的。委派端还能看到它是一次 Agent 选择，避免这个选择进入子 Agent 后被当成新的用户命令。

**被拒绝之后还能重试，是否等于允许绕过防线？**

不是。重试应该改变实际风险，例如改成本地分析、缩小数据范围或请求确认；只换命令、脚本或地址继续完成同一越界动作，仍然违反拒绝原因。

**误报率很低，为什么还不能替代 Sandbox？**

误报率衡量正常动作被打扰多少，不衡量危险动作是否都被拦住。分类器存在漏判，而 Sandbox 等机制限制的是实际权限。两者需要分别评价并共同工作。

## 参考资料

- [Anthropic — How we built Claude Code auto mode: a safer way to skip permissions](https://www.anthropic.com/engineering/claude-code-auto-mode)
