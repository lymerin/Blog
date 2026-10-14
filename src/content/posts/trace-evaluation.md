---
title: 'Trace Evaluation：怎样从执行轨迹定位 Agent 的问题？'
description: '理解 Trace 与 Span 怎样记录工作流，区分结果评分和行为评分，再围绕工具、交接、Guardrail 与反馈恢复建立证据标准，用批量评估比较不同版本。'
pubDate: 2026-10-14T13:05:34+08:00
category: notes
tags: [Agent, OpenAI, Evaluation, Tracing, 学习笔记]
draft: false
postType: metaOnly
---

[上一篇](/zh-cn/posts/agent-evals/)建立了 Agent Eval 的基本结构：给定任务，运行多次尝试，再检查执行记录和实际结果。但拿到一条“失败”的评分以后，排查才刚开始：是选错了工具，传错了参数，交接时丢了信息，还是工具正确执行后，Agent 把结果理解错了？

这些问题需要回到执行轨迹里看。Trace Evaluation 不是把最终回答再评一次，而是把工作流中的行动、反馈和衔接纳入判断，让一次成功或失败有可以核对的过程依据。

结合 OpenAI 的[《Evaluate agent workflows》](https://developers.openai.com/api/docs/guides/agent-evals)与[《Trace grading》](https://developers.openai.com/api/docs/guides/trace-grading)，本文从三层展开：

- **记录：** Trace 与 Span 怎样组织一次工作流，判断行动需要哪些前后文。
- **诊断：** 怎样分别检查工具、交接和执行边界，区分行为错误、执行失败与有效恢复。
- **比较：** 怎样把发现的问题写成评分标准，再通过数据集与评估运行检查改动。

下面延续一个假设的退款场景：用户已确认退回指定订单的 50 元付款。例子中的金额统一使用人民币，工具参数 `amount_minor` 以分为单位；日志、字段与评分结果均为本文自拟的教学示意。

## 一、Trace 怎样还原一次工作流

只看最终回答，往往只知道 Agent 宣布了什么。Trace 的作用，是把它拿到了哪些信息、提出过哪些动作、实际收到什么反馈，以及下一步怎样衔接，放进同一条执行记录。

### 1. Trace 与 Span：整体执行和局部操作

**Trace 组织一次工作流的整体记录；Span 描述其中一段有边界的操作。** 模型调用、工具执行和 Agent 交接，可以分别成为轨迹中的局部片段。

例如，售后工作流可能先由入口 Agent 识别任务，再交给退款 Agent；退款 Agent 查询订单、提交操作、读取反馈，最后答复。只保存各步独立日志，就很难判断某条工具返回属于哪个请求，或者是哪位 Agent 在收到反馈以后继续执行。

用整体记录关联局部操作，便能沿着工作流查看：

- 这一步由哪个角色发起，处于哪个任务中。
- 请求携带了什么参数，实际返回了什么。
- 操作何时开始、何时结束，是否报错。
- 它与前后步骤是什么关系，是否属于某个子任务。

OpenAI 的[SDK tracing 说明](https://developers.openai.com/api/docs/guides/agents/integrations-observability#tracing)介绍了模型调用、工具、Handoff、Guardrail 和自定义 Span 等记录，也给出了把多个 SDK run 放入同一 Trace 的用法。因此，不能机械地把一条 Trace 等同于一次模型推理或一次 SDK 调用。

具体能看到什么，取决于实际采集。没有记录的检查或外部状态，不会因为界面上出现一条完整时间线就自动变得可见；Trace 也不是模型全部内部推理的透明快照。

### 2. 上下文与反馈：给每个动作找到判断依据

看到一次 `process_refund` 调用，不能只检查工具名和参数形状。还要看当时已经具备什么条件：订单是否属于当前用户、政策是否允许退款、用户是否确认，以及金额来自哪里。

下面是一段简化记录：

```text
用户请求：退回订单 ord_demo_18 的 50 元付款，已确认
订单查询：订单已取消，尚未退款，可退金额 5000 分
工具请求：process_refund(order_id="ord_demo_18", amount_minor=50000)
执行前检查：金额超过可退范围，拒绝；未发生写操作
后续行动：依据错误反馈，把 amount_minor 修正为 5000
```

参数 `50000` 是合法整数，但与前序结果中的 `5000` 不一致。错误不是“模型没有使用退款工具”，而是已经取得正确金额，却在构造参数时放大了十倍。

这条差异只有把工具请求与前面的证据连起来才能看见。如果只保留“调用失败”，就会丢掉两个重要信息：失败来自执行前检查，而不是退款服务宕机；Agent 是否读取拒绝原因并修正，还要看后续记录。

因此，读 Trace 不是逐行挑错，而是检查**输入依据 → 行动请求 → 实际反馈 → 后续处理**有没有接上。前序信息缺失、请求内容错误和反馈被忽略，是不同的排查位置。

## 二、怎样从轨迹中检查行为错误

结果评分和过程评分可以同时存在。前者核对任务是否完成，后者检查这次完成或失败中，哪些行为符合要求、哪些需要改进。

### 3. Outcome 与行为评分：分别检查完成情况和执行质量

继续看前面的错误金额。如果检查拒绝后，Agent 修正参数，实际只退回 50 元，并准确告知用户，那么最终 Outcome 可以正确，但“首次金额构造”这项行为检查仍然未通过。

同时，“根据反馈恢复”可以通过。它没有无视拒绝反复提交，也没有绕过检查，而是用已有证据修正错误。一次错误和一次有效恢复，都应当在记录中保留下来。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 1 · 结果正确，不等于每一步都正确：分别评价首次请求与反馈恢复</figcaption>
<div tabindex="0" role="region" aria-label="退款轨迹中的错误参数、检查拦截与有效恢复" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="trace-evaluation-recovery-title trace-evaluation-recovery-desc" viewBox="0 0 640 536" style="display:block; width:100%; min-width:540px; height:auto; font-family:var(--font-sans); --node:light-dark(#e8f3fc,#142b3e); --condition:light-dark(#f4f9fe,#102333); --ink:light-dark(#235e89,#c0def4); --border:light-dark(#d0e0ed,#355167); --line:light-dark(#8e959d,#8295a6); --success:light-dark(#e5f6eb,#152f26); --success-ink:light-dark(#286447,#a9debf); --success-border:light-dark(#afd3bc,#426c57); --warn:light-dark(#fff3d7,#352918); --warn-ink:light-dark(#8b5b22,#f3ce8d); --warn-border:light-dark(#e8c98e,#80663a);">
<title id="trace-evaluation-recovery-title">错误退款参数被检查拦截后，Agent 修正并完成任务</title>
<desc id="trace-evaluation-recovery-desc">用户确认退款五十元。Agent 首次请求错误地传入五万分，被金额检查拒绝且未执行；读取反馈后改为五千分，工具成功，环境与答复均正确。评分分别记录结果正确、首次参数错误、反馈恢复有效。</desc>
<defs><marker id="trace-evaluation-recovery-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<g fill="none" stroke="var(--line)" stroke-width="1.2" marker-end="url(#trace-evaluation-recovery-arrow)"><path d="M320 92 V110 Q320 120 310 120 H126 Q116 120 116 130 V154"/><path d="M208 198 H228"/><path d="M412 198 H432"/><path d="M524 242 V290"/><path d="M432 334 H412"/><path d="M228 334 H208"/><path d="M116 378 V404 Q116 414 126 414 H310 Q320 414 320 424 V444"/></g>
<rect x="190" y="24" width="260" height="68" rx="20" fill="var(--node)" stroke="var(--border)"/>
<text x="320" y="52" text-anchor="middle" fill="var(--ink)" font-size="18" font-weight="500">请求与条件</text><text x="320" y="76" text-anchor="middle" fill="var(--ink)" font-size="14">已确认退款 50 元 · 可退 5000 分</text>
<rect x="24" y="154" width="184" height="88" rx="20" fill="var(--warn)" stroke="var(--warn-border)"/>
<text x="116" y="188" text-anchor="middle" fill="var(--warn-ink)" font-size="17" font-weight="500">首次请求</text><text x="116" y="216" text-anchor="middle" fill="var(--warn-ink)" font-size="14">错误传入 50000 分</text>
<rect x="228" y="154" width="184" height="88" rx="20" fill="var(--condition)" stroke="var(--border)" stroke-dasharray="3 3"/>
<text x="320" y="188" text-anchor="middle" fill="var(--ink)" font-size="17" font-weight="500">金额检查拒绝</text><text x="320" y="216" text-anchor="middle" fill="var(--ink)" font-size="14">返回原因 · 未执行</text>
<rect x="432" y="154" width="184" height="88" rx="20" fill="var(--node)" stroke="var(--border)"/>
<text x="524" y="188" text-anchor="middle" fill="var(--ink)" font-size="17" font-weight="500">读取反馈并修正</text><text x="524" y="216" text-anchor="middle" fill="var(--ink)" font-size="14">重新请求 5000 分</text>
<g fill="var(--success)" stroke="var(--success-border)"><rect x="432" y="290" width="184" height="88" rx="20"/><rect x="228" y="290" width="184" height="88" rx="20"/><rect x="24" y="290" width="184" height="88" rx="20"/></g>
<g text-anchor="middle" fill="var(--success-ink)"><text x="524" y="324" font-size="17" font-weight="500">工具实际执行</text><text x="524" y="352" font-size="14">成功退回 5000 分</text><text x="320" y="324" font-size="17" font-weight="500">环境终态</text><text x="320" y="352" font-size="14">仅有一笔正确退款</text><text x="116" y="324" font-size="17" font-weight="500">最终答复</text><text x="116" y="352" font-size="14">与实际退款一致</text></g>
<rect x="92" y="444" width="456" height="76" rx="20" fill="var(--node)" stroke="var(--border)"/>
<text x="320" y="474" text-anchor="middle" fill="var(--ink)" font-size="17" font-weight="500">分开记录不同维度</text><text x="320" y="502" text-anchor="middle" fill="var(--ink)" font-size="14">结果正确 · 首次参数错误 · 反馈恢复有效</text>
</svg>
</div>
</figure>

另一种情况是，Agent 选对工具、传对参数，但退款服务返回错误，最终没有成功记录。这时任务未完成，却不能把失败直接标成“参数错误”。需要继续区分工具执行问题，以及 Agent 有没有如实报告失败、有没有采取符合约定的后续处理。

这两种情况说明，**业务结果、行为要求和恢复能力是可以分别评分的维度**。总分可以汇总它们，却不应该把它们的区别抹掉。

### 4. Tool Selection 与 Arguments：选对能力，传入有依据的参数

工具检查可以拆成两个问题：这项能力适不适合当前任务，以及参数是否符合当前证据与业务语义。

在退款例子里：

- 使用订单查询定位付款，是能力选择问题。
- 查询的是不是当前用户的目标订单，是参数与对象对应问题。
- `amount_minor` 是否等于已确认的可退金额，是单位与数值问题。
- 重复申请时有没有创建第二笔退款，是状态与幂等要求问题。

如果用户只是咨询退款政策，直接选择退款写操作，即使参数完全合法，选择仍然不合适。反过来，选中了正确的退款工具，却把 50 元写成 500 元，则是另一类错误。

这样的划分会影响修改方向。经常选错能力，可以检查工具名称、用途边界和指令；经常传错金额，则要继续核对单位说明、返回字段和参数构造。Trace 提供排查线索，不意味着看到某个错误就能断定唯一原因。

### 5. Routing 与 Handoff：检查职责选择和交接信息

多 Agent 工作流还要看任务交给了谁，以及接手者拿到了什么。

例如，入口 Agent 已经取得订单、身份核实结果与用户确认，再 Handoff 给退款 Agent。接手者如果只看到“用户想退款”，就可能重复追问，甚至用另一笔订单继续处理。表面上是后续 Agent 没有完成任务，问题却可能从交接信息开始。

可以分别检查：

- **Routing：** 根据当时的请求和条件，是否选中了合适的处理分支。
- **Handoff：** 交接是否符合职责边界，必要信息有没有随之传递。
- **接手处理：** 后续角色是否使用了已取得的证据，是否正确接续未完成动作。

[Manager 与 Handoff](/zh-cn/posts/multi-agent-orchestration/)的返回关系也不同。专家作为工具返回结果，和转交后续处理权，不能只因日志里都出现另一个 Agent，就用同一条“是否交接成功”标准判断。

这里检查的是具体关系，不是要求所有售后问题都必须走相同的 Agent 顺序。任务可以由单 Agent 完成时，没有发生 Handoff 也不自动构成失败。

### 6. Guardrail 与反馈恢复：区分拦截、违规和无效重试

Guardrail 出现拒绝记录，不一定说明整个系统失效。在图中的例子里，金额检查确实挡住了错误操作。但要同时保留两项事实：Agent 提出了错误请求，执行层避免了它造成副作用。

评估还需要看拒绝之后发生了什么：

- 依据可修正的错误原因调整参数，属于有效恢复。
- 原样重复不合法请求，增加调用却没有解决原因。
- 改用另一条通道执行同一违规动作，需要检查是否试图绕过边界。
- 无法继续时如实解释并停止，可以符合任务的失败处理要求。

因此，“触发 Guardrail 的次数越少越好”不是充分的标准。检查是否应该触发、是否在操作前生效、是否错误拦截正常动作，都需要对应任务条件。

调用次数和轮次也要这样理解。多问一次订单号，可能是在补齐必要信息；把已经确认的订单重复询问五次，则可能暴露状态没有传好。次数适合帮助筛选异常轨迹，是否冗余仍需结合当时的信息判断。

## 三、怎样把单条诊断变成可重复的评估

读懂一条 Trace，能够帮助修复一次问题；把同类行为写成一致标准，再作用于一批记录，才能判断它是不是反复发生，以及改动有没有改善。

### 7. Rubric：把判断写成带证据的评分标准

“工具用得合理”太宽泛，不容易稳定评分。可以把它拆成可观察的问题，并约定通过、失败和证据不足时怎样处理。

例如，在用户已确认退款的任务中，“金额参数是否正确”可以这样定义：

> 检查发往退款执行入口的请求，其订单、币种和金额是否与授权范围及已核实的可退金额一致。按接口约定解释单位。记录被检查的请求及相应证据；缺少关键条件时标为无法判断，不猜测金额。

这样的标准明确了检查对象和依据，也避免只对着最终答复判分。具体数值可以用程序核对；用户确认是否对应当前订单等开放语义，可以结合模型评分与人工样本校准。

下面是针对图中例子的**自拟评分结果**，不是 OpenAI API 的返回结构：

```json
{
  "outcome": "pass",
  "first_refund_arguments": {
    "label": "fail",
    "evidence": "已确认金额为 5000 分，首次请求传入 50000 分"
  },
  "amount_guardrail": {
    "label": "pass",
    "evidence": "执行前拒绝超额请求，未发生写操作"
  },
  "feedback_recovery": {
    "label": "pass",
    "evidence": "读取拒绝原因后，修正为 5000 分并完成退款"
  }
}
```

结果应能追溯到实际记录。工程中可以关联到对应的 Span 或事件标识，让评审者找到那次请求和反馈，而不只保留一句概括。

还要区分“这项标准不适用”和“缺少证据”。没有要求 Handoff 的单 Agent 任务，可以不检查交接；本应采集的交接信息丢失，则不能直接判为正确。

### 8. Dataset 与 Eval Run：从代表性记录到批量比较

OpenAI 的[工作流评估说明](https://developers.openai.com/api/docs/guides/agent-evals)把单条 Trace 检查与可重复的数据集评估连接起来：先弄清什么行为值得检查，再安排系统性的评估运行。

对于退款场景，可以把观察到的问题整理成不同任务条件：金额单位变化、需要交接、重复申请、执行拒绝和服务失败。每种条件都应包含正常与异常行为，避免评分器看到退款相关记录就一律判错。

批量评分后，不仅看整体通过率，还要按问题类型回看：

| 观察到的变化 | 值得进一步检查什么 |
| --- | --- |
| 参数错误减少，最终完成率没有提高 | 是否还有工具执行、交接或结果解释问题 |
| 总分提高，但正常退款更常被拒绝 | 新规则是否造成过度拦截 |
| 平均调用数下降，信息不足任务更常失败 | 是否减少了原本必要的澄清与查询 |
| Handoff 次数减少，重复追问增加 | 职责调整是否同时破坏了信息衔接 |

这些是诊断方向，不是单靠统计就能证明的原因。需要抽查对应 Trace，确认评分依据与真实行为一致。

官方资料也给出了从 Traces 中检查工作流、创建 Grader，再批量评估的入口。界面能够帮助运行这些步骤，但哪些问题值得检查、证据怎样解释，仍然取决于任务与标准本身。

### 9. Version Comparison：区分重评分和重新运行 Agent

比较版本时，有两个容易混淆的操作：

- **对旧 Trace 重新评分：** 行为记录没有变，改变的是检查标准或评分器。
- **让新版 Agent 重跑任务：** 行为重新发生，产生新的 Trace 和 Outcome，再用可比较的标准评分。

如果只是修改 Grader 后，旧记录的分数提高了，说明评价方式发生了变化，不能据此声称 Agent 已经改好。要验证新指令是否让金额构造更准确，需要让新版本在相同任务起点重新执行。

反过来，新版本换了执行路径，也不必因为它不再复现旧轨迹而扣分。应当检查它是否仍满足同样的行为要求与结果标准，而不是把旧版本的步骤表当答案。

比较中记录任务、Agent 配置与 Grader 版本，保留各维度结果，并抽查有明显变化的轨迹。改进可能发生在参数构造、恢复方式或交接质量，而不一定立刻反映为总分的大幅变化。

Trace 给出的证据可以支持“错误发生在这一环”，但要验证“修改这一处解决了问题”，还需要重跑和对照。例如，参数单位写错可能来自工具说明、上下文缺失或错误转换，不能仅凭调用记录直接把原因归结为模型能力不足。

我更看重 Trace Evaluation 提供的这条连接：**把一次执行里的具体行为，变成可以定位、核对和持续比较的检查项。** Outcome 说明做成了什么，Trace 解释执行过程中出现了什么；两者放在一起，改进才有明确对象。

## 几个关键问题，串起执行记录、诊断与回归

**Trace 和普通日志有什么区别？**

关键不在名字，而在关联。零散日志记录发生过的事件，结构化 Trace 进一步组织它们属于哪次工作流、哪项操作，以及怎样相互衔接。只有大量文本，却无法对应请求与结果，仍然不利于诊断。

**最终成功了，中间传错一次参数还需要记录吗？**

需要，但应分维度解释。结果可以通过，首次参数检查可以失败，恢复能力可以通过。这样既不掩盖错误，也不把有效恢复误写成整条流程完全失败。

**Guardrail 拒绝了操作，应该给 Agent 通过还是失败？**

先看评的是什么。错误请求应当被记录；正确拦截可以通过执行边界检查；正常操作被误拒则暴露另一类问题。单凭“有拒绝记录”无法评价整条工作流。

**Trace 能直接证明模型为什么做错吗？**

不能。它能显示已记录的输入、请求和反馈，帮助定位错误环节，但不能读出不可见的内部原因。修改工具说明、补齐上下文或调整指令后，还要通过重新执行验证假设。

**调用越少，是否说明工作流越好？**

不一定。省去重复查询有价值，省去必要确认却可能增加错误。应先满足结果和行为要求，再比较冗余调用、轮次与耗时。

**为什么不能直接要求固定的工具调用顺序？**

因为合理任务可能有不同路径。需要检查的是有依据的约束，例如执行前取得确认，而不是无业务要求的步骤偏好。否则 Agent 找到了有效的替代路径，也会被误判。

**给旧 Trace 换一个 Grader，算验证新版 Agent 吗？**

不算。它验证的是评分变化。新版 Agent 是否改善，需要重跑任务，取得新的执行记录与结果，再在一致或明确记录变化的标准下比较。

## 参考资料

- [OpenAI — Evaluate agent workflows](https://developers.openai.com/api/docs/guides/agent-evals)
- [OpenAI — Trace grading](https://developers.openai.com/api/docs/guides/trace-grading)
- [OpenAI — Integrations and observability](https://developers.openai.com/api/docs/guides/agents/integrations-observability)
- [上一篇：Agent Eval](/zh-cn/posts/agent-evals/)
- [配套阅读：Multi-Agent Orchestration](/zh-cn/posts/multi-agent-orchestration/)
