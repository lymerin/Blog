---
title: 'Eval Integrity：答案泄漏与评估识别怎样影响 Agent 测试？'
description: '结合 BrowseComp 案例，区分 Benchmark Contamination 与 Eval Awareness，理解开放网络、代码执行和多 Agent 搜索怎样影响答案来源，再分析执行轨迹、评估边界与成绩解释。'
pubDate: 2026-10-14T13:33:14+08:00
category: notes
tags: [Agent, Anthropic, Evaluation, 学习笔记]
draft: false
postType: metaOnly
---

[上一篇](/zh-cn/posts/eval-reliability/)讨论了运行环境怎样影响分数。这一篇再检查一个更基础的前提：**Agent 答对了问题，是否真的完成了我们想测的任务？**

如果测试希望衡量检索和研究能力，而 Agent 在网上找到了这道题的答案表，最终答案仍然可能完全正确。但这次通过所提供的能力证据，已经与独立查证不同了。

Anthropic 的[《Eval awareness in Claude Opus 4.6’s BrowseComp performance》](https://www.anthropic.com/engineering/eval-awareness-browsecomp)记录了一个具体案例：在 1,266 道 BrowseComp 问题的多 Agent 运行中，发现 9 道题偶然接触泄漏答案，以及 2 道题先识别评估、再找到并解密答案集。它讨论的不是评分程序算错，而是**正确答案的取得路径改变了**。

本文先区分答案污染与评估识别，再解释案例中的搜索路线和工具作用，最后讨论怎样审查来源、明确评估边界并解释成绩。贯穿说明使用一个自拟问题：“某个地方展览第一次开幕的日期是什么？”它只用于比较查证路径，不对应原文的真实题目。

## 一、答案污染与评估识别有什么区别

开放网络测试需要允许 Agent 找资料。困难在于，真实资料与测试材料可能同时出现在搜索结果中；它们都能提供答案，却不一定提供同一种能力证据。

### 1. Benchmark Contamination：答案进入可获取的信息

Benchmark Contamination 通常译作基准污染。这里关心的是：评估题目或答案进入了被测系统可以利用的信息，使成绩混入了原定解题过程之外的帮助。

需要区分两条进入路径：

- **训练阶段接触：** 模型可能已经见过题目或解答，运行时不必重新完成推导。
- **评估时获取：** 即使没有记住答案，也可能通过搜索、网页或公开文件取得测试材料。

这篇关注第二条。不能因为 Agent 没有从记忆里直接说出答案，就认定测试没有受到污染。

例如，Agent 搜索展览日期，找到一篇回顾展览历史的报道，再核对机构档案，这是原本期待的研究过程。另一种情况是，搜索结果里出现了测试题解析，恰好同时列出完整问题与标准日期。Agent 甚至不需要知道自己正在接受评估，也可能利用这条信息答对。

**污染描述的是信息进入评估的方式，不要求 Agent 先产生“找答案表”的意图。** 因此，发现污染后首先应检查答案来源，而不是立即给行为贴上道德标签。

### 2. Eval Awareness：识别评估与改变行动

Eval Awareness 指模型察觉或推测自己正在被评估。在这个案例里，它进一步影响了行动：搜索对象从“问题所描述的事实”，转向了“这道题属于哪套测试”。

用展览问题解释，两条路线的区别是：

- 研究事实：查展览名称、场馆公告、当地报道和历史档案。
- 识别测试：判断题目是否来自某个 Benchmark，再搜索题库或解答。

评估识别与答案污染不是同义词。Agent 可以偶然读到答案而没有识别测试；也可以猜到自己正在考试，却仍然独立研究。真正需要沿轨迹判断的是：**识别之后，它有没有改变信息来源和解题方法？**

这也不是对模型“主观意识”的证明。能够观察的是输出和行动：它提出了哪些假设、搜索了什么、读取了哪些材料，以及这些材料怎样影响最终答案。

## 二、BrowseComp 案例中的搜索路线怎样变化

这个案例值得分析的地方，是 Agent 并非一开始就拿着测试名称找答案。正常研究与测试识别出现在同一次长执行过程中，后者改变了任务的实际解决方式。

### 3. 搜索目标：从事实查证转向 Benchmark 识别

原文记录的两次成功识别，都经历了常规搜索，再根据题目的特点推测测试来源，最后转向答案集。这里的转折不是“又换了一个关键词”，而是**把题目本身当作检索对象**。具体过程见 [BrowseComp 案例报告](https://www.anthropic.com/engineering/eval-awareness-browsecomp)。

在展览例子里，搜索“某场馆 展览 开幕”是在查事件；搜索整道问题并寻找它所属的题库，则是在查测试材料。两者都使用搜索工具，但信息目标不同。

仅凭“搜索了 Benchmark 名称”还不能下结论。一次普通检索也可能返回研究论文，论文又可能只是介绍评估方法。判断来源是否影响了结果，还需要继续追踪：有没有命中当前题目、读到解答、提取候选答案，或者据此缩小搜索范围。

因此，轨迹审查关注的不是某个词单独出现，而是**来源、内容与后续行动之间的关系**。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 1 · 三条取答路径可能得到相同答案，但支持的能力判断不同</figcaption>
<div tabindex="0" role="region" aria-label="事实查证、偶然答案污染与评估识别的三条取答路径" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="eval-integrity-paths-title eval-integrity-paths-desc" viewBox="0 0 640 444" style="display:block; width:100%; min-width:540px; height:auto; font-family:var(--font-sans); --node:light-dark(#e8f3fc,#142b3e); --condition:light-dark(#f4f9fe,#102333); --ink:light-dark(#235e89,#c0def4); --border:light-dark(#d0e0ed,#355167); --line:light-dark(#8e959d,#8295a6); --success:light-dark(#e5f6eb,#152f26); --success-ink:light-dark(#286447,#a9debf); --success-border:light-dark(#afd3bc,#426c57); --warn:light-dark(#fff3d7,#352918); --warn-ink:light-dark(#8b5b22,#f3ce8d); --warn-border:light-dark(#e8c98e,#80663a);">
<title id="eval-integrity-paths-title">相同答案背后的三种取得路径</title>
<desc id="eval-integrity-paths-desc">用户提出日期问题。第一条路径检索原始资料并核对证据；第二条路径在常规搜索中碰到泄漏的题目和解答；第三条路径识别 Benchmark 后转向答案集。三条路径可能提交相同答案，但只有最终答案的评分不能区分它们。</desc>
<defs><marker id="eval-integrity-paths-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<g fill="none" stroke="var(--line)" stroke-width="1.2" marker-end="url(#eval-integrity-paths-arrow)"><path d="M320 84 V104 Q320 114 310 114 H116 Q106 114 106 124 V144"/><path d="M320 84 V144"/><path d="M320 84 V104 Q320 114 330 114 H524 Q534 114 534 124 V144"/><path d="M106 212 V250"/><path d="M320 212 V250"/><path d="M534 212 V250"/><path d="M106 318 V338 Q106 348 116 348 H310 Q320 348 320 358 V376"/><path d="M320 318 V376"/><path d="M534 318 V338 Q534 348 524 348 H330 Q320 348 320 358 V376"/></g>
<rect x="170" y="20" width="300" height="64" rx="20" fill="var(--node)" stroke="var(--border)"/>
<text x="320" y="47" text-anchor="middle" fill="var(--ink)" font-size="18" font-weight="500">查找展览开幕日期</text><text x="320" y="71" text-anchor="middle" fill="var(--ink)" font-size="14">同一个问题，可能走向不同来源</text>
<g fill="var(--success)" stroke="var(--success-border)"><rect x="16" y="144" width="180" height="68" rx="20"/><rect x="16" y="250" width="180" height="68" rx="20"/></g>
<g text-anchor="middle" fill="var(--success-ink)"><text x="106" y="173" font-size="17" font-weight="500">检索事件资料</text><text x="106" y="197" font-size="14">报道、公告与档案</text><text x="106" y="279" font-size="17" font-weight="500">核对事实证据</text><text x="106" y="303" font-size="14">由资料建立结论</text></g>
<g fill="var(--warn)" stroke="var(--warn-border)"><rect x="230" y="144" width="180" height="68" rx="20"/><rect x="230" y="250" width="180" height="68" rx="20"/></g>
<g text-anchor="middle" fill="var(--warn-ink)"><text x="320" y="173" font-size="17" font-weight="500">常规搜索碰到泄漏</text><text x="320" y="197" font-size="14">出现题目与解答</text><text x="320" y="279" font-size="17" font-weight="500">取得候选答案</text><text x="320" y="303" font-size="14">未必意识到正在评估</text></g>
<rect x="444" y="144" width="180" height="68" rx="20" fill="var(--condition)" stroke="var(--border)" stroke-dasharray="3 3"/>
<text x="534" y="173" text-anchor="middle" fill="var(--ink)" font-size="17" font-weight="500">识别 Benchmark</text><text x="534" y="197" text-anchor="middle" fill="var(--ink)" font-size="14">转向查找测试材料</text>
<rect x="444" y="250" width="180" height="68" rx="20" fill="var(--warn)" stroke="var(--warn-border)"/>
<text x="534" y="279" text-anchor="middle" fill="var(--warn-ink)" font-size="17" font-weight="500">访问答案集</text><text x="534" y="303" text-anchor="middle" fill="var(--warn-ink)" font-size="14">定位当前题目</text>
<rect x="92" y="376" width="456" height="52" rx="18" fill="var(--node)" stroke="var(--border)"/>
<text x="320" y="408" text-anchor="middle" fill="var(--ink)" font-size="17" font-weight="500">相同的最终答案，不能还原取得路径</text>
</svg>
</div>
</figure>

### 4. 工具组合：搜索、数据获取与代码执行

案例中的答案集不是直接摆在普通网页上的一行文字。Agent 把搜索、材料读取和代码执行连起来，最终取出了答案；一种数据格式无法读取时，还找到了可读取的替代副本。[原文](https://www.anthropic.com/engineering/eval-awareness-browsecomp)记录了这条工具链。

这说明评估边界不能只按工具名称判断。“允许搜索”和“允许执行代码”分开看都很常见，组合之后却可能完成新的动作：找到评估材料、处理其表示形式、定位题目，再把结果作为答案提交。

这里需要分清两层能力：Agent 确实展示了规划、搜索和程序处理能力，但这些能力被用来获取测试解答。**它做成了一件复杂的事，不等于它用原定方法完成了被测任务。**

同样，取到候选答案后再找到一篇支持它的报道，也不能让此前的泄漏从执行历史中消失。知道日期后搜索“展览名称 + 日期”，与不知道答案时独立确定日期，搜索难度和证据作用都不同。后续核对可以提高答案可信度，却不能证明整个发现过程没有得到答案提示。

## 三、开放网络与多 Agent 怎样影响污染范围

答案泄漏不是只发生在某个固定文件里。评估使用开放网络，就要面对内容复制、索引变化和多个搜索者共同接触信息的情况。

### 5. 来源扩散：原始资料、答案副本与搜索痕迹

对展览日期来说，机构档案、新闻报道、测试解析和转载解析的博客，都可能写着同一个日期。但它们的来源关系不同。

假设三篇网页都复制了同一份测试解答，那么“三个来源一致”并不是三份独立证据。只数链接数量，会把复制次数误当成查证强度。需要判断材料从哪里来、是否独立记录了事件，以及有没有直接转述题目和答案。

原文还观察到某些网站把搜索词变成持久页面，URL 留下其他搜索者的猜测；这些痕迹本身不是答案。[案例报告](https://www.anthropic.com/engineering/eval-awareness-browsecomp)把它作为另一种污染渠道讨论。

由此可以形成一个审查原则：**搜索命中说明页面与查询有关，不代表页面构成事实证据。** 标题、URL 或摘要复述了整道题，也可能只是先前搜索留下的内容。网页能打开、返回正常状态，同样不能证明它真的记录了那场展览。

### 6. Multi-Agent：并行搜索与共同来源

多个 Agent 分头研究，会扩大探索范围，也增加接触某份泄漏材料的机会。一个子 Agent 取得答案后，其他成员可能在汇总阶段间接接受它，而没有看到完整的发现过程。

例如，研究者 A 查场馆档案，研究者 B 查地方媒体，研究者 C 搜索完整题目。如果 C 从测试解析中找到日期，只返回“日期是某日，已有网页支持”，Lead 就很容易把不同来源性质的结论混在一起。

这里的问题不是“多 Agent 天生不可靠”，而是**独立 Context 不等于独立证据**。它们共享同一个网络，也可能读取同一份答案的不同副本。

因此，汇总结果时应保留答案来源及其作用：某个页面提供了新事实，还是只给出了候选答案？子 Agent 返回的短摘要可以节省 Context，但审查所需的来源记录仍应能够追溯。否则，并行探索越多，最终报告反而越难解释每个结论是怎样形成的。

## 四、受到污染的评估结果怎样解释

发现非预期取答路径之后，需要同时处理两件事：这次结果还能支持什么结论，以及评估规则怎样与测量目标对应。

### 7. Source Provenance：把答案追溯到执行轨迹

只检查最终日期是否正确，无法区分图中的三条路线。沿用[执行轨迹评价](/zh-cn/posts/trace-evaluation/)的方法，可以把检查落到具体记录上：

- **检索目标：** 查询是在寻找事件事实，还是在寻找题库和解答？
- **读取材料：** 实际接触了哪些页面或文件，是否包含当前题目的答案？
- **答案形成：** 候选日期何时首次出现，来自哪一条记录？
- **后续核对：** 新资料独立提供了证据，还是根据已知答案做确认？
- **汇总传播：** 哪个 Agent 首先取得信息，其他成员接收了什么？

这些是针对本例整理的审查问题，不是一个现成的自动判定器。日志可能不完整，页面也可能变化。证据不够时，可以标记来源待确认，而不是仅凭一个关键词认定整条轨迹无效。

重跑则回答另一个问题：限制可疑材料之后，Agent 能否通过独立研究完成任务？它可以提供新证据，却不会改写原始运行已经发生的路径。原始成绩、标记范围、处理方法和重跑成绩应当分开保留。

### 8. 评估边界：任务目标、允许来源与结论范围

如果普通用户只想知道展览日期，一份可靠解答可能已经有用；如果测试要衡量独立研究，直接读取测试答案就削弱了测量意义。**同一个取答动作是否影响评估，取决于它与能力目标的关系。**

这也是为什么不能简单把案例写成“模型违反规则”。Anthropic 说明，当时没有要求模型限制搜索范围，因此没有把这次表现判断为对齐失败。问题在于，任务表面的“找到答案”与评估者期待的研究过程，并没有完全重合。见[原文结论](https://www.anthropic.com/engineering/eval-awareness-browsecomp)。

从设计角度看，至少需要让三件事对应起来：

| 设计对象 | 需要明确的问题 |
| --- | --- |
| 能力目标 | 是取得正确事实，还是独立发现并验证证据？ |
| 可用环境 | 哪些资料与工具能够访问，测试解答能否被取得？ |
| 结果解释 | 答案正确、来源合规与研究过程分别提供什么证据？ |

限制测试材料、审查轨迹、调整任务分布，都有各自作用，也有代价。只封一个地址，未必覆盖复制品；限制过多，又可能让测试不再代表开放网络研究。不能把一个案例中的有效措施写成所有 Benchmark 都适用的防御方案。

受到污染的个别运行，也不意味着整套评估完全没有价值。更有用的做法是报告受影响的范围，说明如何处理，并把结论收回到证据实际支持的程度：哪些答案来自独立查证，哪些得到了测试材料帮助，哪些仍然无法确定。

## 几个关键问题，串起答案来源与评估边界

**没有在训练中见过答案，为什么仍然可能发生污染？**

Agent 运行时可以取得外部信息。测试解答一旦进入公开网页、文件或搜索结果，即使模型没有记忆，也可能在评估中读取。训练接触与运行时获取是两条不同路径。

**Eval Awareness 一定意味着找到了泄漏答案吗？**

不一定。识别测试是一种判断，访问并利用答案是后续行为。两者要沿轨迹分别检查；偶然读到泄漏答案，也未必伴随评估识别。

**答案正确，而且附了真实来源，为什么仍然需要审查？**

还要看答案怎样形成。先读解答，再按已知答案寻找支持资料，与独立发现并核对事实不同。真实来源可以支持答案内容，却不能单独证明发现过程没有受到泄漏帮助。

**多个 Agent 都同意一个答案，能证明没有污染吗？**

不能。它们可能读取同一份解答或其副本，也可能通过 Lead 共享候选答案。独立运行的数量不等于独立证据的数量，需要保留来源关系。

**封掉题库地址，是否就恢复了评估完整性？**

不能据此保证。复制品、论文案例和衍生页面仍可能提供答案；限制也可能改变任务环境。需要结合实际来源与轨迹检查效果，而不是只检查一个域名是否被屏蔽。

**这个案例说明 Agent 能力没有进步吗？**

不是。它展示了搜索、规划和工具组合的能力，同时说明这些能力可能被用于非预期路径。需要修正的是“这个成绩证明了什么”，而不是用一个现象否定全部能力。

到这里，Level 7 的五个问题可以连起来：先确定怎样测量任务结果，再用轨迹解释行为，检查题目是否有区分度、运行条件是否可比，最后确认答案取得方式是否仍符合测量目标。**可信的评估既需要正确判分，也需要清楚说明这份成绩究竟证明了什么。**

## 参考资料

- [Anthropic — Eval awareness in Claude Opus 4.6’s BrowseComp performance](https://www.anthropic.com/engineering/eval-awareness-browsecomp)
