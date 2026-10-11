---
title: '从架构到一个真正的 Agent：Model、Tools、Instructions 与 Orchestration'
description: '从模型、工具和指令理解单 Agent 的执行，再分析 Manager 与 Handoff 怎样组织协作，以及 Guardrails 和人工介入怎样约束行动。'
pubDate: 2026-10-11T21:50:00+08:00
category: notes
tags: [Agent, OpenAI, LLM, 学习笔记]
draft: false
postType: metaOnly
---

[上一篇](/zh-cn/posts/building-effective-agents/)讨论的是系统结构：哪些步骤由程序提前组织，哪些行动交给模型根据反馈决定。这一篇把视角放到 Agent 内部，看看它怎样从理解请求走到实际执行，又怎样与其他 Agent 协作。

结合 OpenAI 的 [《A practical guide to building agents》](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/)，本文从三个层次展开：

- **组成与执行：** Model、Tools、Instructions 各自负责什么，怎样配合完成一次单 Agent 的执行。
- **协作方式：** 什么时候需要拆分为多个 Agent，Manager 与 Handoff 分别怎样委派工作和转交处理权。
- **行动边界：** Guardrails 怎样约束操作，哪些情况需要 Human Intervention（人工介入）。

下面用一个假设的订单售后场景贯穿全文：用户说“包裹一直没到，帮我看看能不能退款”。沿着这条请求，逐步说明这三层关系。

## 一、一个 Agent 怎样完成任务

OpenAI 将 Agent 的基本组成归为 **Model、Tools 和 Instructions**。可以分别理解为：负责判断的模型、连接外部系统的工具，以及指导处理过程的指令。

这三个组成不能互相替代。模型能够理解“我想退款”，不代表它知道这笔订单的真实状态；能查询订单，也不代表它有权修改订单；有了修改工具，仍然需要知道什么情况下应该使用。

### 1. Model：依据当前信息，决定下一步

面对售后请求，模型首先要处理的是判断问题：用户是在询问物流，还是已经明确要求退款？现有信息足够吗？应该先问订单号，还是可以查询当前账号的订单？

这些判断会影响后面的工具调用。如果订单还在运输途中，接下来可能需要查物流；如果已经退回仓库，就要结合售后规则判断下一步。**模型的作用不只是组织回答，而是把当前信息转化为下一步行动。**

因此，评价模型是否适合这个任务，不能只看它回答得是否流畅。还要看它能否识别缺失信息、选对工具，并根据工具结果调整判断。例如，查询返回“未找到订单”时，是否会请求核实订单号，而不是继续编出一个物流状态。

模型能力、延迟与成本也需要放在具体任务中看。OpenAI 建议先用能力较强的模型建立效果基线，再尝试用较小模型承担能够胜任的部分。这样才能区分：问题出在模型能力，还是工具和指令本身没有设计清楚。

### 2. Tools：让判断连接真实信息和操作

模型可以根据用户的话提出退款建议，但订单状态、物流记录和退款结果，都需要从外部系统获取。Tools 承担的就是这层连接。

在这个例子里，可以按用途理解几类能力：

| 工具用途 | 假设的工具 | 提供什么能力 |
| --- | --- | --- |
| Data：读取信息 | `get_order`、`get_delivery_status` | 获取订单和物流状态 |
| Action：执行操作 | `submit_refund_request` | 向售后系统提交申请 |
| Orchestration：委派工作 | 调用专门的物流 Agent | 让另一个 Agent 完成一部分任务 |

最后一类也是后面 Manager 模式的连接点：**对调用者来说，另一个 Agent 可以表现为一个工具；区别在于，这个工具内部也会进行判断和执行。**

工具定义是否清楚，会直接影响模型能否正确使用它。假设同时存在 `refund_order` 和 `submit_refund_request`，但没有解释两者的差别，模型就可能把“提交申请”误当成“直接完成退款”。

更清楚的定义应该交代：什么时候用、需要哪些参数、会产生什么效果，以及结果代表什么。例如，`submit_refund_request` 返回申请编号，只能说明申请已经受理，不能据此回复“退款已经到账”。

这也说明，**调用成功和业务完成是两回事**。工具不仅要能被调用，还要让返回结果足以支持下一步判断。

### 3. Instructions：把处理规则写成可执行的指导

“你是一名专业的售后助手”只规定了角色，没有解释售后请求应该怎样处理。真正影响执行的是更具体的规则：需要先查什么，缺少信息怎么办，哪些条件下可以继续，哪些情况必须停止。

例如，可以把这个场景的指导写成：

1. 缺少订单信息时，先请求用户补充，不猜测订单。
2. 查询订单及物流状态，依据返回的信息说明当前情况。
3. 按现行售后政策判断可用的处理方式，不自行承诺例外。
4. 提交申请前确认用户意图；需要人工批准的操作先暂停。
5. 根据工具返回的实际状态答复，区分申请受理、退款处理中和退款完成。

这几条分别说明了信息缺失、正常处理、业务条件、操作边界和结果表达。它们比单纯要求“认真负责、准确回答”更容易落实到具体行动。

已有的业务政策、操作文档和客服流程，可以成为指令的基础，但不能只是整段塞进上下文。整理时需要把条件和动作对应起来：**遇到什么情况，应该做什么；不能继续时，又该怎样处理。**

不过，指令仍然是在指导模型。把“不要操作其他人的订单”写进 Prompt，不等于完成了订单访问控制。真正的权限校验，需要由工具和业务系统落实。这一点会在第三部分继续串起来。

### 4. Single-Agent：三种组成怎样协同执行

有了模型、工具和指令，接下来要解决的是执行怎样持续推进，也就是 **Orchestration（编排）**。它不是与前三者并列的第四种基础组件，而是把这些能力组织起来的方式。

单 Agent 可以连续进行多次判断和工具调用，并不等于“一次模型调用”。对于这条售后请求，一段执行可能是：

> 识别用户意图 → 查询订单 → 读取物流结果 → 判断可用的处理方式 → 答复用户或请求确认

如果用户没有提供订单号，就先等待补充；如果查询失败，就依据失败信息决定是否重试。**下一步依据当前状态决定，不要求每一条请求都完整走过同样的步骤。**

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 1 · 单 Agent：指令提供规则，模型决定下一步，工具返回实际信息</figcaption>
<div tabindex="0" role="region" aria-label="单 Agent 的三个组成与执行关系" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="practical-components-title practical-components-desc" viewBox="0 0 640 560" style="display:block; width:100%; min-width:520px; height:auto; font-family:var(--font-sans); --node:light-dark(#e8f3fc,#142b3e); --condition:light-dark(#f4f9fe,#102333); --ink:light-dark(#235e89,#c0def4); --border:light-dark(#d0e0ed,#355167); --line:light-dark(#8e959d,#8295a6); --success:light-dark(#e5f6eb,#152f26); --success-ink:light-dark(#286447,#a9debf); --success-border:light-dark(#afd3bc,#426c57);">
<title id="practical-components-title">单 Agent 中 Model、Tools 与 Instructions 的协作</title>
<desc id="practical-components-desc">用户请求进入模型。指令提供处理规则，模型选择查询工具，读取工具结果后继续判断。可以继续查询，也可以答复用户或暂停等待。</desc>
<defs><marker id="practical-components-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<g fill="none" stroke="var(--line)" stroke-width="1.2" marker-end="url(#practical-components-arrow)"><path d="M320 98 V152"/><path d="M164 201 H198"/><path d="M320 248 V320"/><path d="M440 364 H490 Q500 364 500 354 V214 Q500 204 490 204 H442"/><path d="M200 225 H186 Q176 225 176 235 V494 Q176 504 186 504 H198"/></g>
<rect x="200" y="24" width="240" height="74" rx="20" fill="var(--condition)" stroke="var(--border)"/>
<text x="320" y="55" text-anchor="middle" fill="var(--ink)" font-size="18" font-weight="500">Instructions</text><text x="320" y="79" text-anchor="middle" fill="var(--ink)" font-size="14">目标、处理步骤与异常规则</text>
<rect x="24" y="162" width="140" height="78" rx="20" fill="var(--node)" stroke="var(--border)"/>
<text x="94" y="194" text-anchor="middle" fill="var(--ink)" font-size="17" font-weight="500">用户请求</text><text x="94" y="219" text-anchor="middle" fill="var(--ink)" font-size="13">查询订单售后</text>
<rect x="200" y="154" width="240" height="94" rx="20" fill="var(--node)" stroke="var(--border)"/>
<text x="320" y="190" text-anchor="middle" fill="var(--ink)" font-size="18" font-weight="500">Model</text><text x="320" y="219" text-anchor="middle" fill="var(--ink)" font-size="14">依据当前信息决定下一步</text>
<text x="320" y="290" text-anchor="middle" fill="var(--ink)" font-size="13">需要补充信息</text>
<rect x="200" y="322" width="240" height="84" rx="20" fill="var(--node)" stroke="var(--border)"/>
<text x="320" y="356" text-anchor="middle" fill="var(--ink)" font-size="18" font-weight="500">Tools</text><text x="320" y="382" text-anchor="middle" fill="var(--ink)" font-size="14">查询获准访问的订单与物流</text>
<text x="516" y="271" fill="var(--ink)" font-size="13">结果返回</text><text x="516" y="293" fill="var(--ink)" font-size="13">继续判断</text>
<text x="142" y="423" text-anchor="end" fill="var(--ink)" font-size="13">可以答复</text><text x="142" y="445" text-anchor="end" fill="var(--ink)" font-size="13">或需等待</text>
<rect x="200" y="466" width="240" height="74" rx="20" fill="var(--success)" stroke="var(--success-border)"/>
<text x="320" y="497" text-anchor="middle" fill="var(--success-ink)" font-size="17" font-weight="500">答复用户 / 暂停等待</text><text x="320" y="521" text-anchor="middle" fill="var(--success-ink)" font-size="13">完成当前处理，或请求补充与确认</text>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">图中展示信息查询。涉及修改状态的操作，还需要执行前检查。窄屏可在图内左右滑动查看。</div>
</figure>

这里还有一个容易忽略的区别：**模型决定下一步做什么，运行程序负责真正执行工具、记录结果并控制是否继续。** 最大轮次、调用失败和等待用户输入等退出条件，不能只靠模型自由发挥。

所以，单 Agent 已经可以包含完整的判断与执行过程。新增一项查询能力，首先可以考虑增加定义清楚的工具，而不是立即增加一个 Agent。

## 二、多个 Agent 怎样协作

### 5. 什么时候单 Agent 需要拆分？

OpenAI 的建议是先充分发挥单 Agent 的能力，再考虑 Multi-Agent。这个顺序很重要：**拆分应该解决已经出现的职责复杂度，而不是为了让架构看起来更完整。**

可以从两个具体问题判断。

**第一，处理规则是否已经难以集中表达。** 如果同一个 Agent 同时承担物流查询、退款争议和商家申诉，大量条件分支混在一起，不同任务的指令就可能互相干扰。可以先整理共用规则，把变化的政策抽成模板参数；这些方式仍然难以管理时，再按职责拆分。

**第二，工具之间是否持续发生混淆。** 关键不只是数量，而是名称、用途和参数有没有明显重叠。先改进工具定义；如果模型仍然频繁把某一领域的工具用于另一领域，就可以让不同 Agent 只接触各自需要的工具。

拆分后的价值，应该能够说清楚：哪个 Agent 负责什么，它需要哪些信息，向谁交付什么结果。如果这些问题没有答案，只是把原来的一大段 Prompt 分成几段，复杂度未必真的下降。

而且，职责分开也会带来新的工作：上下文如何传递、结果怎样汇总、失败由谁处理。**Multi-Agent 是重新分配职责，同时也重新分配了协调成本。**

### 6. Manager：委派工作，再接回结果

假设一个售后请求需要综合物流情况和退款规则，但最终仍希望由同一个负责人向用户解释。可以让一个 Manager Agent 委派具体工作，再读取结果、继续判断。

例如，Manager 调用物流 Agent，获得包裹状态；必要时再调用售后规则 Agent，获得可用方案。随后由 Manager 综合这些信息，决定是解释物流、请求确认，还是提出需要批准的操作。

**被调用的 Agent 完成的是一项委派工作，结果会返回 Manager。** Manager 仍然负责整体处理，不是把用户交出去后就退出。

这就是 agents as tools 的含义。专门 Agent 内部可以调用自己的工具、进行多步处理，但对 Manager 暴露的是一项可调用的能力。

这种结构适合需要统一组织结果的任务。相应地，Manager 也必须正确理解子任务的返回结果：物流 Agent 说“信息不足”，不能被汇总成“包裹已丢失”；规则 Agent 说“满足申请条件”，也不等于退款已经执行。

### 7. Handoff：把后续处理交给接手者

另一种情况是，入口 Agent 只负责识别请求类型。确认这是订单售后问题后，后面的追问、查询和答复，都可以由售后 Agent 独立完成。

这时使用 **Handoff（交接）** 更贴切：接待 Agent 转交相关上下文与执行控制，由接手者继续处理。

它与 Manager 的区别不在于有没有分类，也不在于用了几个 Agent，而在于：**专门 Agent 是返回一份结果，还是接过后续处理权。**

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 2 · Manager 接回结果，Handoff 转交后续处理</figcaption>
<div tabindex="0" role="region" aria-label="Manager 与 Handoff 的控制关系对比" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="practical-orchestration-title practical-orchestration-desc" viewBox="0 0 640 460" style="display:block; width:100%; min-width:560px; height:auto; font-family:var(--font-sans); --node:light-dark(#e8f3fc,#142b3e); --condition:light-dark(#f4f9fe,#102333); --ink:light-dark(#235e89,#c0def4); --border:light-dark(#d0e0ed,#355167); --line:light-dark(#8e959d,#8295a6); --success:light-dark(#e5f6eb,#152f26); --success-ink:light-dark(#286447,#a9debf); --success-border:light-dark(#afd3bc,#426c57);">
<title id="practical-orchestration-title">Manager 与 Handoff 的区别</title><desc id="practical-orchestration-desc">Manager 调用专门 Agent，专门 Agent 返回结果，同一个 Manager 继续处理并统一答复。Handoff 则由接待 Agent 把处理权交给售后 Agent，接手者继续与用户交互，不隐含自动返回。</desc>
<defs><marker id="practical-orchestration-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<rect x="16" y="16" width="608" height="202" rx="20" fill="var(--condition)" stroke="var(--border)"/>
<text x="40" y="51" fill="var(--ink)" font-size="18" font-weight="500">Manager · 调用专门能力，结果返回负责人</text>
<g fill="none" stroke="var(--line)" stroke-width="1.2" marker-end="url(#practical-orchestration-arrow)"><path d="M184 118 H242"/><path d="M396 118 H454"/></g>
<text x="214" y="104" text-anchor="middle" fill="var(--ink)" font-size="12">调用</text><text x="426" y="104" text-anchor="middle" fill="var(--ink)" font-size="12">返回结果</text>
<rect x="32" y="86" width="152" height="64" rx="18" fill="var(--node)" stroke="var(--border)"/><text x="108" y="113" text-anchor="middle" fill="var(--ink)" font-size="17" font-weight="500">Manager</text><text x="108" y="136" text-anchor="middle" fill="var(--ink)" font-size="13">委派物流查询</text>
<rect x="244" y="86" width="152" height="64" rx="18" fill="var(--node)" stroke="var(--border)"/><text x="320" y="113" text-anchor="middle" fill="var(--ink)" font-size="17" font-weight="500">物流 Agent</text><text x="320" y="136" text-anchor="middle" fill="var(--ink)" font-size="13">完成委派工作</text>
<rect x="456" y="86" width="152" height="64" rx="18" fill="var(--success)" stroke="var(--success-border)"/><text x="532" y="113" text-anchor="middle" fill="var(--success-ink)" font-size="16" font-weight="500">同一 Manager</text><text x="532" y="136" text-anchor="middle" fill="var(--success-ink)" font-size="13">综合结果、继续处理</text>
<text x="320" y="186" text-anchor="middle" fill="var(--ink)" font-size="14">用户仍由 Manager 统一答复</text>
<rect x="16" y="242" width="608" height="202" rx="20" fill="var(--condition)" stroke="var(--border)"/>
<text x="40" y="277" fill="var(--ink)" font-size="18" font-weight="500">Handoff · 转交处理权，由接手者继续推进</text>
<g fill="none" stroke="var(--line)" stroke-width="1.2" marker-end="url(#practical-orchestration-arrow)"><path d="M184 344 H242"/><path d="M396 344 H454"/></g>
<text x="214" y="330" text-anchor="middle" fill="var(--ink)" font-size="12">交接</text><text x="426" y="330" text-anchor="middle" fill="var(--ink)" font-size="12">继续</text>
<rect x="32" y="312" width="152" height="64" rx="18" fill="var(--node)" stroke="var(--border)"/><text x="108" y="339" text-anchor="middle" fill="var(--ink)" font-size="17" font-weight="500">接待 Agent</text><text x="108" y="362" text-anchor="middle" fill="var(--ink)" font-size="13">识别请求类型</text>
<rect x="244" y="312" width="152" height="64" rx="18" fill="var(--node)" stroke="var(--border)"/><text x="320" y="339" text-anchor="middle" fill="var(--ink)" font-size="17" font-weight="500">售后 Agent</text><text x="320" y="362" text-anchor="middle" fill="var(--ink)" font-size="13">接收上下文与处理权</text>
<rect x="456" y="312" width="152" height="64" rx="18" fill="var(--success)" stroke="var(--success-border)"/><text x="532" y="339" text-anchor="middle" fill="var(--success-ink)" font-size="17" font-weight="500">继续处理</text><text x="532" y="362" text-anchor="middle" fill="var(--success-ink)" font-size="13">接手者直接答复用户</text>
<text x="320" y="412" text-anchor="middle" fill="var(--ink)" font-size="14">不会自动回到接待 Agent；再次交接需要显式安排</text>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">两个模式的核心差别是处理权怎样流动。窄屏可在图内左右滑动查看。</div>
</figure>

Handoff 本身不隐含“做完再回来”。如果售后 Agent 处理过程中发现需要转回接待 Agent，应该明确设计另一次交接，而不是把它当作普通函数返回。

把两种关系放在一起，可以这样对照：

| 对比项 | Manager | Handoff |
| --- | --- | --- |
| 专门 Agent 的职责 | 完成委派工作并返回结果 | 接手后续处理 |
| 谁继续组织任务 | Manager | 接手的 Agent |
| 谁面向用户 | 通常由 Manager 统一答复 | 接手者可以继续与用户交互 |
| 适合的情况 | 需要综合多份结果、保留统一负责人 | 某项职责可以交给专门角色独立推进 |

同一套系统也可以组合两种模式。接待 Agent 先把请求交给售后 Agent；售后 Agent 再以 Manager 的方式调用物流查询能力。**要看清的是每一次调用和交接的含义，不是给整个系统贴一个固定标签。**

## 三、Agent 的行动边界怎样确定

### 8. Guardrails：提出操作，不等于获准执行

前两部分解决了怎样判断、怎样执行和怎样分工，但还有一个独立问题：模型提出的操作，是否可以真正执行？

同样是工具调用，查询物流与修改收款账户的风险显然不同。即使模型认为“这样能够满足用户要求”，系统也需要检查它是否有权这么做、是否符合业务规则，以及是否需要额外批准。

我更愿意沿着一次处理过程理解 **Guardrails（防护约束）**：

- **接收请求时：** 识别越界请求或试图改变系统行为的恶意指令。
- **执行操作前：** 检查身份、资源访问权限、业务条件，以及必要的批准。
- **生成答复时：** 检查敏感信息和实际结果，避免泄露他人数据或错误宣称操作已完成。

这是从执行过程组织检查的位置，不意味着只需设置三道固定关卡。不同风险可能分别由程序规则、内容检查或模型判断处理；它们也不能替代业务系统原有的身份认证和权限控制。

例如，指令可以要求“只处理当前用户的订单”，但查询工具仍应验证订单归属。否则，一旦模型传入别人的订单号，单靠一句指令就无法阻止数据被读出。

类似地，涉及资金的操作如果要求人工批准，就必须先取得批准，再执行工具。**事后检测到违规，不能撤销已经发生的所有影响。** 有些普通检查可以并行进行，但不应把这种做法直接套到必须先获准的高风险操作上。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 3 · 高风险操作：先检查必要条件，再决定执行、拒绝或等待人工</figcaption>
<div tabindex="0" role="region" aria-label="高风险操作的检查与人工批准流程" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="practical-guardrails-title practical-guardrails-desc" viewBox="0 0 640 620" style="display:block; width:100%; min-width:540px; height:auto; font-family:var(--font-sans); --node:light-dark(#e8f3fc,#142b3e); --condition:light-dark(#f4f9fe,#102333); --ink:light-dark(#235e89,#c0def4); --border:light-dark(#d0e0ed,#355167); --line:light-dark(#8e959d,#8295a6); --success:light-dark(#e5f6eb,#152f26); --success-ink:light-dark(#286447,#a9debf); --success-border:light-dark(#afd3bc,#426c57); --warn:light-dark(#fff3d7,#352918); --warn-ink:light-dark(#8b5b22,#f3ce8d); --warn-border:light-dark(#e8c98e,#80663a);">
<title id="practical-guardrails-title">高风险操作的执行前约束</title><desc id="practical-guardrails-desc">模型提出操作后，系统先检查身份、权限、规则和必要批准。不允许则拒绝；需要人工批准则等待，将审批结果带回重新检查；全部通过才执行工具。之后核对结果，答复实际状态。</desc>
<defs><marker id="practical-guardrails-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<g fill="none" stroke="var(--line)" stroke-width="1.2" marker-end="url(#practical-guardrails-arrow)"><path d="M320 80 V128"/><path d="M200 170 H156 Q146 170 146 180 V298"/><path d="M320 210 V298"/><path d="M440 170 H506 Q516 170 516 180 V298"/><path d="M596 339 H606 Q616 339 616 329 V118 Q616 108 606 108 H410 Q400 108 400 118 V128"/><path d="M320 378 V438"/><path d="M320 504 V550"/></g>
<rect x="200" y="20" width="240" height="60" rx="20" fill="var(--node)" stroke="var(--border)"/><text x="320" y="56" text-anchor="middle" fill="var(--ink)" font-size="18" font-weight="500">模型提出操作</text>
<rect x="200" y="130" width="240" height="80" rx="20" fill="var(--condition)" stroke="var(--border)" stroke-dasharray="3 3"/><text x="320" y="164" text-anchor="middle" fill="var(--ink)" font-size="18" font-weight="500">执行前检查</text><text x="320" y="189" text-anchor="middle" fill="var(--ink)" font-size="14">身份、权限、规则、必要批准</text>
<text x="146" y="267" text-anchor="middle" fill="var(--ink)" font-size="13">不允许</text><text x="320" y="267" text-anchor="middle" fill="var(--ink)" font-size="13">全部通过</text><text x="516" y="267" text-anchor="middle" fill="var(--ink)" font-size="13">需要批准</text>
<rect x="76" y="300" width="140" height="78" rx="20" fill="var(--warn)" stroke="var(--warn-border)"/><text x="146" y="344" text-anchor="middle" fill="var(--warn-ink)" font-size="17" font-weight="500">拒绝执行</text>
<rect x="252" y="300" width="136" height="78" rx="20" fill="var(--node)" stroke="var(--border)"/><text x="320" y="331" text-anchor="middle" fill="var(--ink)" font-size="17" font-weight="500">调用工具</text><text x="320" y="356" text-anchor="middle" fill="var(--ink)" font-size="13">执行获准操作</text>
<rect x="436" y="300" width="160" height="78" rx="20" fill="var(--warn)" stroke="var(--warn-border)"/><text x="516" y="331" text-anchor="middle" fill="var(--warn-ink)" font-size="17" font-weight="500">等待人工</text><text x="516" y="356" text-anchor="middle" fill="var(--warn-ink)" font-size="13">此时不执行操作</text>
<text x="601" y="96" text-anchor="end" fill="var(--ink)" font-size="12">带回审批结果，重新检查</text>
<rect x="220" y="440" width="200" height="64" rx="20" fill="var(--node)" stroke="var(--border)"/><text x="320" y="479" text-anchor="middle" fill="var(--ink)" font-size="17" font-weight="500">核对实际结果</text>
<rect x="220" y="552" width="200" height="58" rx="20" fill="var(--success)" stroke="var(--success-border)"/><text x="320" y="587" text-anchor="middle" fill="var(--success-ink)" font-size="17" font-weight="500">答复实际状态</text>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">人工批准后，仍需满足当前权限与业务条件；拒绝批准则不执行。窄屏可在图内左右滑动查看。</div>
</figure>

### 9. Human Intervention：知道什么时候交给人

人工介入不只是“模型答错以后找人补救”。它也可以是正常处理过程中的明确安排：有些事情允许 Agent 准备信息和提出建议，但最后的决定必须由人作出。

第一类情况是**无法继续可靠推进**。例如订单系统连续查询失败，或者反复确认仍无法识别用户要处理哪一笔订单。继续重试不一定增加有效信息，反而可能消耗时间或产生重复操作。系统需要设置尝试上限，达到条件后停止并转交。

第二类情况是**操作风险本身要求人工决定**。例如存在争议的退款或不可逆操作，即使模型已经给出清楚的理由，也不代表可以省略必要的批准。

交给人时，真正有用的不是一句“处理失败”，而是一份能够接着往下工作的说明：用户想解决什么、已经查到什么、尝试过哪些操作、卡在哪里，以及需要人决定哪件事。

这也与前面的 Handoff 不同。Handoff 是 Agent 之间转交执行；人工介入是把特定决定或后续处理交给人。两者都涉及控制权变化，但接手者的责任和可执行权限并不相同。

## 把组成、协作与边界连起来

从这条售后请求回看整套结构，Model 依据当前信息判断下一步，Tools 连接订单与物流系统，Instructions 说明处理规则。单 Agent 可以把它们组织成完整执行；职责复杂到需要拆分时，再明确是由 Manager 接回结果，还是通过 Handoff 交出处理权。

而无论由哪个 Agent 处理，提出一个操作都不等于获得执行许可。权限校验、防护检查与人工批准，需要约束真正发生的行动。

**理解一个 Agent，既要看它如何作出决定，也要看决定如何被执行、由谁继续负责，以及什么情况下必须停下来。** 这几层关系清楚了，组件和编排方式才能对应到具体任务，而不只是停留在架构图里的名称。

## 几个关键问题，串起组成、协作与边界

沿着前面的售后场景，可以把这些关系归纳成几个问题。

**模型已经能理解用户意图，为什么还需要 Tools 和 Instructions？**

理解“我想退款”，不等于知道订单状态，也不等于知道这笔订单适用什么规则。Model 负责依据已有信息判断，Tools 提供实际信息和操作能力，Instructions 说明处理目标与规则。三者解决的是不同问题：换一个更强的模型，不能替代缺失的订单接口；增加退款工具，也不能替代清楚的处理规则。

**模型决定下一步，为什么还需要程序控制执行？**

模型可以提出“查询物流”或“提交退款申请”，但真正调用工具、接收结果、保存状态和限制重试次数，仍需要运行程序完成。这里要区分**行动决策和执行控制**：模型决定想做什么，程序控制这个动作如何发生、是否允许发生，以及执行何时暂停或结束。Orchestration 组织的正是这些关系，而不是与 Model、Tools、Instructions 并列的第四种基础组件。

**一个 Agent 的工具越来越多，就应该拆成多个 Agent 吗？**

工具多只是现象，要看它是否造成持续的职责冲突或选择混淆。如果工具定义清楚、处理规则一致，单 Agent 仍然可以完成多步任务；如果不同领域需要不同规则、工具和权限，拆分才可能让职责更清晰。判断拆分是否有价值，不只看子 Agent 是否更专注，还要看增加的上下文传递、结果汇总和失败处理成本是否值得。

**同样是找另一个 Agent 帮忙，Manager 和 Handoff 到底差在哪里？**

看交出去的是**一项工作，还是后续处理权**。Manager 请物流 Agent 查包裹，拿到结果后仍由自己继续处理和答复；Handoff 则把请求交给售后 Agent，由接手者继续追问、查询和回应。前者返回的是子任务结果，后者改变的是当前负责人。Handoff 不隐含自动返回，如果还要交回原 Agent，需要明确安排另一次交接。

**Instructions 已经写了“不能越权”，为什么还要做执行前检查？**

指令是在指导模型的判断，权限校验是在限制系统实际能执行的操作。即使模型传入了别人的订单号，工具也应该拒绝读取，而不是依赖模型记住一句“只处理当前用户的订单”。同样，需要批准的退款必须在调用工具前暂停。**描述一条规则，与在操作发生的位置执行这条规则，是两回事。** Guardrails 需要与身份认证、权限控制配合，不能替代它们。

**转交另一个 Agent、继续重试和交给人工，分别解决什么问题？**

转交 Agent 解决的是职责归属，例如把售后请求交给专门角色；重试适合预期能够恢复的临时失败，但必须有次数或时间上限；人工介入则用于需要人作出决定，或系统已无法可靠推进的情况。订单查询暂时超时，可以有限重试；达到上限后，应交代已有信息和失败位置；退款需要人工批准时，则应直接等待批准，不能靠重试或换一个 Agent 绕过去。

## 参考资料

- [OpenAI — A practical guide to building agents](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/)
- [上一篇：理解 Workflow 与 Agent：五种工作流与智能体的运行原理](/zh-cn/posts/building-effective-agents/)
