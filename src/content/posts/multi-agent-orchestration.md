---
title: 'Multi-Agent Orchestration：Manager、Handoff 与控制权分配'
description: '理解 Manager 的子任务调用与 Handoff 的执行接管，区分上下文、任务状态和控制权，分析多 Agent 的拆分条件与协作成本。'
pubDate: 2026-10-13T12:30:00+08:00
category: notes
tags: [Agent, OpenAI, Multi-Agent, Orchestration, 学习笔记]
draft: false
postType: metaOnly
---

[研究系统](/zh-cn/posts/multi-agent-research/)让 Lead 委派搜索，再收回材料形成报告；[并行编程](/zh-cn/posts/parallel-coding-agents/)让多个 Agent 通过任务认领、Git 和测试共同推进项目。这两种系统都包含多个 Agent，但任务在它们之间流动的方式并不一样。

理解多 Agent 编排，需要看清三件事：**谁决定下一步，工作结果返回给谁，谁继续与用户交互。** Agent 的数量和角色名称只能描述有哪些参与者，不能解释这些参与者怎样协作。

这一篇结合 OpenAI《A practical guide to building agents》的编排部分，整理两种基本关系：**Manager 把专家作为工具调用，Handoff 把后续执行交给另一位 Agent。** 先理解控制流，再看信息怎样跨边界传递，以及什么时候值得拆分 Agent。

## 一、Agent 之间怎样分配执行控制权

先看子任务结果是否返回，再看当前执行者是否切换，这是两种编排关系的核心边界。

### 1. Manager：委派子任务，再接回结果

Manager Pattern 由一个中心 Agent 负责整体请求，把有边界的工作交给专家，再依据返回结果决定下一步。专家可以在自己的执行过程中连续调用工具；对外层而言，它仍然是一次有输入、有结果的子任务调用。

以一个假设的售后请求为例：“包裹一直没到，帮我看看能不能退款。”售后 Manager 可以分别委派：

- **物流专家：** 查询运输事件，判断是否存在异常，以及哪些情况尚未确认。
- **规则专家：** 核对订单适用的退款规则，说明申请条件和必要确认。
- **Manager：** 综合事实和规则，向用户解释可选方案，组织后续操作。

这是一种 **agents as tools** 的关系。物流专家不需要接管整段售后对话，只需把自己的查询结果交回来。

例如，物流专家返回“运输停留在转运中心，尚未确认丢件”，规则专家返回“已达到申请条件，需要用户确认”。Manager 需要据此询问用户是否申请退款，而不能直接回复“退款已完成”。**专家的判断、用户的确认和真实业务操作，是不同的任务状态。**

因此，委派不能只有一句“帮我处理售后”。一个有用的委派约定至少要明确：

| 约定 | 物流查询示例 |
| --- | --- |
| 目标 | 核查订单的运输状态，而不是处理整段售后 |
| 输入 | 订单标识、用户描述、已经核实的信息 |
| 范围 | 可以查询物流，不自行提交退款 |
| 返回内容 | 运输事实、查询依据、未确认信息 |
| 结束条件 | 已取得足够证据，或明确说明信息缺口 |

Manager 保留的是**外层流程与综合答复的责任**。这不意味着它在等待专家时一直进行模型推理，也不意味着专家必须只调用一次工具。外层调用和专家内部的 Agent Loop 是两层执行过程。

### 2. Handoff：转交当前分支的后续处理

Handoff 不只是让另一位 Agent 帮忙查一件事，而是切换当前执行者，由接收方继续处理这个分支。

仍然是售后请求。如果入口 Agent 只负责识别问题类型，确认属于订单售后以后，就可以把处理交给订单 Agent。之后由订单 Agent 查询情况、向用户追问并给出答复，不必让入口 Agent 转述每一次交流。

两种关系可以压成：

> **Manager：** 委派子任务 → 收回结果 → 自己继续。  
> **Handoff：** 转交当前分支 → 接收方继续。

<figure class="not-prose" style="margin:1.75em 0;">
  <figcaption style="font-size:.8125rem;color:var(--muted-foreground);margin-bottom:1rem;text-align:center;">图 1 · Manager 收回子任务结果；Handoff 转交后续执行</figcaption>
  <div role="region" aria-label="Manager 与 Handoff 控制权对比图，可横向滚动" tabindex="0" style="overflow-x:auto;max-width:100%;border-radius:16px;padding:8px 0;background:hsl(0 0% 50% / .025);">
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 440" role="img" aria-labelledby="orchestration-title orchestration-desc" style="display:block;width:100%;min-width:600px;height:auto;font-family:var(--font-sans);--node:light-dark(#e8f3fc,#142b3e);--ink:light-dark(#235e89,#c0def4);--border:light-dark(#d0e0ed,#355167);--line:light-dark(#8e959d,#8295a6);--success:light-dark(#e5f6eb,#152f26);--success-ink:light-dark(#286447,#a9debf);--success-border:light-dark(#afd3bc,#426c57);">
      <title id="orchestration-title">Manager 与 Handoff 的控制权区别</title>
      <desc id="orchestration-desc">Manager 将专家作为工具调用，接回结果后统一答复用户。Handoff 则由 Triage 将后续执行交给 Order Agent，Order Agent 直接处理并答复，不自动返回 Triage。接收方获得的信息范围由应用约定。</desc>
      <defs><marker id="orchestration-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 1 1 L 8 5 L 1 9" fill="none" stroke="var(--line)" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
      <g fill="none" stroke="var(--line)" stroke-width="1.5" marker-end="url(#orchestration-arrow)">
        <path d="M220 105H280"/>
        <path d="M280 140H220"/>
        <path d="M130 80V55Q130 45 140 45H590Q600 45 600 55V80"/>
        <path d="M220 330H280"/>
        <path d="M460 330H520"/>
      </g>
      <path d="M40 220H680" fill="none" stroke="var(--border)" stroke-dasharray="4 5"/>
      <g fill="var(--node)" stroke="var(--border)" stroke-width="1.5"><rect x="40" y="80" width="180" height="80" rx="18"/><rect x="280" y="80" width="180" height="80" rx="18"/><rect x="40" y="290" width="180" height="80" rx="18"/><rect x="280" y="290" width="180" height="80" rx="18"/></g>
      <g fill="var(--success)" stroke="var(--success-border)" stroke-width="1.5"><rect x="520" y="80" width="160" height="80" rx="18"/><rect x="520" y="290" width="160" height="80" rx="18"/></g>
      <g text-anchor="middle" fill="var(--ink)">
        <g font-size="18" font-weight="600"><text x="130" y="113">Manager</text><text x="370" y="113">专家 Agent</text><text x="130" y="323">Triage Agent</text><text x="370" y="323">Order Agent</text></g>
        <g font-size="13"><text x="130" y="140">总体责任保留</text><text x="370" y="140">完成有边界的子任务</text><text x="130" y="350">识别售后分支</text><text x="370" y="350">接管后续处理</text></g>
      </g>
      <g text-anchor="middle" fill="var(--success-ink)" font-size="16" font-weight="600"><text x="600" y="113">Manager 答复</text><text x="600" y="140">用户</text><text x="600" y="323">Order 答复</text><text x="600" y="350">用户</text></g>
      <g fill="var(--ink)" font-size="15" font-weight="600"><text x="40" y="22">Manager · 子任务返回，负责人继续处理</text><text x="40" y="262">Handoff · 接收方继续执行与对话</text></g>
      <g text-anchor="middle" fill="var(--line)" font-size="12"><text x="250" y="94">工具调用</text><text x="250" y="156">返回结果</text><text x="365" y="37">综合结果后统一答复</text><text x="250" y="317">Handoff</text><text x="490" y="317">直接答复</text><text x="360" y="412">接管不等于自动继承所有信息；交接范围由应用约定</text></g>
    </svg>
  </div>
</figure>

Handoff 是一次**单向的执行转移**，不隐含“专家做完自动返回入口”。如果需要交回，应明确安排另一条交接关系。否则，原 Agent 不会像普通函数调用的调用者一样，自然接回一个返回值。

有时 Handoff 也通过模型可调用的工具接口暴露，例如 `transfer_to_order_agent`。接口形式相似，不代表执行语义相同：普通专家工具完成后返回结果，Handoff 则让运行程序切换当前 Agent。

交接也不等于任务完成。订单 Agent 仍然需要核实状态、确认用户意图，并处理执行失败。它接到的是后续处理责任，不是一张“已经成功”的凭证。

## 二、协作中的信息与责任怎样衔接

确定谁继续以后，还要说明接收者拿到什么信息，以及多条调用和交接怎样组合。

### 3. Context 与 State：传递背景、证据与执行进度

控制权解决“谁继续”，信息传递解决“接收者凭什么继续”。切换了 Agent，却没有交代前面发生过什么，后续判断就可能重复、遗漏，甚至把建议当成已经执行的操作。

一次售后交接可以按下面几类信息检查：

| 信息 | 需要保留的内容 |
| --- | --- |
| 用户目标与限制 | 希望调查延误；未确认是否申请退款 |
| 已核实事实 | 订单标识、运输事件、查询时间与来源 |
| 已执行动作 | 已查询物流；尚未提交退款申请 |
| 待办与缺口 | 缺少承运商调查结果，需要向用户确认下一步 |
| 必要的业务状态 | 身份校验结果、已有申请标识等 |

其中，**事实、推断和动作记录要分开**。“符合申请条件”是一项判断，“申请已提交”是一项动作结果，二者不能被压成模糊的“退款处理中”。

这些信息也不一定通过同一种通道传递：

- **会话历史**保留此前的交流和工具观察。
- **交接参数**说明交接原因和必要标识。
- **应用状态**保存业务事实和执行进度。

一个交接对象里有订单号，并不表示接收方已经获得完整历史；业务状态存在数据库中，也不表示模型已经看见它。实现时需要检查实际进入模型输入的内容，以及接收者能够通过哪些工具取得剩余信息。

Manager 委派专家同样有这条边界。专家不应依赖未提供的背景，Manager 也不应假设返回的几句话包含专家全部查询过程。**独立 Context 减少干扰，但必须通过明确的输入和输出重新建立联系。**

另外，交接信息不能代替权限检查。知道订单号、收到“用户想退款”的摘要，都不自动授予操作权限；真正执行时仍需遵守业务系统的校验和批准规则。

### 4. Pattern Composition：比较与组合调用、交接关系

两种模式的选择，可以从具体的责任关系判断，而不是先画一个看起来复杂的多 Agent 架构。

| 维度 | Manager | Handoff |
| --- | --- | --- |
| 交出的工作 | 有边界的子任务 | 当前分支的后续处理 |
| 工作结束后 | 结果返回调用者 | 接收方继续执行或答复 |
| 用户交互 | 通常由 Manager 统一组织 | 接收方可以直接推进 |
| 适合的关系 | 多份结果需要综合、比较或协调 | 专业角色能够独立处理当前分支 |
| 主要协调问题 | 委派是否清楚，汇总是否遗漏 | 交接是否正确，状态是否完整 |

例如，物流、退款规则和补偿方案需要综合权衡时，Manager 有明确价值；如果订单专家已经能够独立完成售后分支，入口 Agent 再转述所有追问，就只增加了中间传递。

两种模式也可以组合：

> 入口 Agent **Handoff** 给订单 Agent；  
> 订单 Agent再以 **Manager** 的方式调用物流专家；  
> 物流结果返回订单 Agent，由它继续回应用户。

这里有两种不同的连接：入口转交处理，订单 Agent 委派查询。只要每条连接的返回关系清楚，系统不必全局只使用一种模式。

反过来，[共享 Git 的并行开发](/zh-cn/posts/parallel-coding-agents/)并不能因为没有中心 Orchestrator，就归类为 Handoff。多个 Agent 可以通过共同产物和任务状态协调，却没有发生“把当前对话的执行权交给另一位 Agent”的操作。**共享状态和执行交接是不同的协作机制。**

## 三、什么时候值得拆分多个 Agent

拆分需要解决具体的职责冲突，也要承担新的信息传递和协调工作。

### 5. Single-Agent 与 Multi-Agent：拆分条件与协调成本

多 Agent 不一定比单 Agent 更有效。一个 Agent 连续查询订单、检查物流和读取规则，仍然可以完整完成售后任务；步骤多、工具多，都不是必须拆分的理由。

OpenAI 指南建议先尽量发挥单 Agent 的能力，再考虑拆分。这里值得分析的是**复杂性造成了什么稳定的失败**，而不是工具数量是否超过某个阈值。

例如：

- 模型反复混用不同业务规则，可能需要按领域划分职责。
- 相似工具经常被误选，应先检查命名、描述和参数，而不是立刻增加 Agent。
- 不同专业结论需要综合，可能适合中心 Manager。
- 某个分支需要持续追问和专门处理，可能适合 Handoff。

拆分的收益来自更聚焦的职责、工具集合和 Context；代价则来自新的通信边界。输入可能遗漏，结果可能失真，交接可能选错，还会增加调用与等待。

因此，评价协作设计不能只看“每位专家都回答得不错”。还要检查整个请求是否正确完成：用户是否重复提供信息，动作是否被重复执行，失败是否有人接住，最终答复是否对应真实业务结果。

我理解的编排设计，不是给每项能力安排一个角色，而是**把工作边界、信息边界和后续责任一起划清楚**。只有这些关系比拆分前更清晰，多 Agent 才真正改善了系统。

## 几个关键问题，串起控制权、上下文与职责划分

**Manager 和 Handoff 都会调用另一位 Agent，决定性区别是什么？**

看工作结束后谁继续。Manager 收回子任务结果，自己推进外层流程；Handoff 切换当前执行者，由接收方处理后续分支。

**专家内部可以有自己的 Agent Loop 吗？**

可以。专家作为工具被调用，并不意味着它只有一次模型推理。它可以反复使用工具完成子任务，再把约定的结果返回 Manager。

**Handoff 会自动回到原 Agent 吗？**

不会隐式返回。需要交回时，应明确安排另一条交接；需要接收方继续下一轮对话时，应用也要保存并恢复相应执行者与会话状态。

**有交接摘要，为什么还需要区分任务状态？**

摘要可能混淆事实、判断和已执行动作。接收方必须知道哪些操作真的发生过、哪些仍待确认，才能避免重复执行或错误宣布完成。

**工具很多时，是否应该直接拆成多个 Agent？**

不一定。先检查工具定义与指令是否清晰。如果改进接口已经解决误用，拆分只会增加协调开销；稳定的职责冲突才是更有意义的拆分信号。

**Manager 是否一定串行，Handoff 是否一定并行？**

都不是。Manager 可以调度独立专家并行工作，也可以按依赖串行调用；Handoff 描述执行者的切换，不描述并行度。调度与控制权是两个维度。

**多 Agent 协作可以只靠共享仓库吗？**

可以形成这样的协作机制，但仍需任务认领、版本同步和验证规则。共享仓库不是自动的任务调度器，也不等于 Handoff。

## 参考资料

- [OpenAI · A practical guide to building agents：Orchestration](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/#orchestration)
- [OpenAI · Orchestration and handoffs](https://developers.openai.com/api/docs/guides/agents/orchestration)
