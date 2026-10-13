---
title: 'Harness Design：怎样组织长期开发与独立验收？'
description: '理解 Planner–Generator–Evaluator、Sprint Contract 和真实应用 QA，分析 Context Reset 与 Compaction 的区别，以及怎样通过移除组件改进 Harness。'
pubDate: 2026-10-13T13:10:00+08:00
category: notes
tags: [Agent, Anthropic, Harness, QA, 学习笔记]
draft: false
postType: metaOnly
---

[上一篇](/zh-cn/posts/long-running-agents/)解决了长期任务的连续性：通过任务清单、进度与 Git，让新 Context 接续工作。接下来还有一个不同的问题：**Agent 能一直开发，不代表应用的功能、交互和设计已经达到要求。**

“做完了哪些任务”与“做出来的东西是否好用”，需要不同的检查。前者依赖状态管理，后者依赖明确标准、实际操作和修正反馈。

Anthropic 在[《Harness design for long-running application development》](https://www.anthropic.com/engineering/harness-design-long-running-apps)中，从前端设计评价走向完整应用开发，又通过实验简化了自己的 Harness。这里重点整理：

- **质量反馈：** 为什么把生成与评价分开，怎样把抽象要求转成具体标准。
- **开发组织：** Planner、Generator、Evaluator 怎样配合，Sprint Contract 怎样连接规格与验收。
- **流程优化：** 哪些组件弥补了模型的不足，哪些已经成为额外负担。

## 一、长期开发需要什么质量反馈

任务接续与成果验收处理不同的问题。先区分这两层，再看独立评价提供什么反馈。

### 1. Context Management 与 Self-Evaluation：长任务的两类问题

Context 越来越长，模型可能难以稳定使用已有信息；即使任务能够继续，它也可能遗漏功能或接受不够好的结果。这是两个问题，不能只靠“再运行几轮”一起解决。

**Context Reset 与 Compaction**

两种方式都能处理历史增长，但保留信息的方式不同：

| 方式 | 怎样继续任务 | 需要承担的代价 |
| --- | --- | --- |
| Compaction | 压缩已有历史，在缩短后的上下文上继续 | 摘要可能遗漏信息，原有判断也可能延续 |
| Context Reset | 清空当前上下文，通过交接材料重新建立工作状态 | 恢复材料必须充分，重新读取增加开销 |

Reset 的收益来自重新建立一个更清晰的起点，代价是切断上下文连续性。Compaction 更直接地保留前后关系，但不是所有偏差都会因历史变短而消失。

**持续执行与质量判断**

假设一个笔记应用已经能编辑和保存，模型仍可能忽略搜索反馈、内容丢失提示或页面层级。运行时间变长，并不会自然给它增加一个更严格的验收标准。

原文将生成与评价分开，正是在补充这条反馈链：不是只让 Agent 继续做，而是让它知道**哪里与要求不同、应该依据什么修改**。

### 2. Generator–Evaluator：分开产出与评价

Generator 负责产出，Evaluator 负责依据标准检查产物，再把问题反馈给 Generator。两者分开，能减少开发者围绕自己的实现解释“为什么已经足够好”的倾向。

但换一个 Agent 并不自动得到可靠评价。Evaluator 仍可能宽松，也可能重复模板式意见。它需要明确标准、可观察证据，以及用于校准判断的例子。

**怎样把“好看、好用”变成可以讨论的要求？**

以前端为例，可以分别检查：

- **整体设计：** 色彩、字体、布局与视觉重点是否形成一致表达。
- **独特性：** 是否针对内容作出具体设计，而不是只套用默认组件。
- **制作质量：** 间距、对齐、对比度和层级是否稳定。
- **功能可用性：** 用户能否找到主要操作并完成任务。

这些维度不是一个通用审美公式，而是让评价从“感觉不错”进入有依据的讨论。实际权重应服务于产品目标：阅读型博客与密集操作的工作台，不应照搬同一套偏好。

**反馈要指向可以修改的位置**

“搜索体验不好”太宽泛；“输入关键词后没有加载状态，空结果与请求失败显示相同文案”才指出了行为缺口。

对 Generator 来说，有价值的反馈包含预期、观察和差异。它可以据此修改，再由 Evaluator 重走同一条路径，确认问题是否消失。

独立评价形成的是改进循环，不是无限修改的理由。标准达成、收益趋于停滞或成本达到约定边界时，都需要明确停止。

## 二、规划、实现与验收怎样配合

产品规格确定要交付什么，开发约定细化完成条件，实际 QA 再检查运行结果。

### 3. Planner、Generator 与 Evaluator：组织三类职责

应用开发比单页设计多了一层需求组织：一句“做一个课程笔记应用”，并没有说明完整的使用路径、功能范围和质量要求。

三种角色可以分别处理：

| 角色 | 主要产出 | 不应混淆的责任 |
| --- | --- | --- |
| Planner | 产品规格、用户路径、交付范围与高层设计 | 不提前锁死所有实现细节 |
| Generator | 可运行实现、自测结果和待验收产物 | 不以自评代替独立验收 |
| Evaluator | 实际检查、问题证据与验收判断 | 不只阅读实现者的完成报告 |

Planner 要让产品范围足够明确，同时保留开发中的判断空间。例如，它可以要求“编辑完成后能够重新打开并看到保存内容”，不必提前规定每个函数和数据库操作的具体写法。

Generator 则负责把规格落实为软件。开发过程中仍然需要自测，独立 QA 不是允许它跳过基本检查的理由。

Evaluator 连接的是规格与真实结果。它既要理解应该交付什么，也要能够访问运行中的应用，检验实现是否只停在界面展示。

原文的完整应用版本分别检查产品深度、功能、视觉设计和代码质量，并为各项设置最低门槛；任一项未达标，都需要返修，而不是靠其他维度的高分抵消功能缺口。

<figure class="not-prose" style="margin:1.75em 0;">
  <figcaption style="font-size:.8125rem;color:var(--muted-foreground);margin-bottom:1rem;text-align:center;">图 1 · Sprint 版本：先约定验收，再实现、独立检查与修正</figcaption>
  <div role="region" aria-label="图 1 · Sprint 版本：先约定验收，再实现、独立检查与修正，可横向滚动" tabindex="0" style="overflow-x:auto;max-width:100%;border-radius:16px;padding:8px 0;background:hsl(0 0% 50% / .025);">
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 540" role="img" aria-labelledby="quality-loop-title" style="display:block;width:100%;min-width:580px;height:auto;font-family:var(--font-sans);--node:light-dark(#e8f3fc,#142b3e);--ink:light-dark(#235e89,#c0def4);--border:light-dark(#d0e0ed,#355167);--line:light-dark(#8e959d,#8295a6);--success:light-dark(#e5f6eb,#152f26);--success-ink:light-dark(#286447,#a9debf);--success-border:light-dark(#afd3bc,#426c57);">
      <title id="quality-loop-title">图 1 · Sprint 版本：先约定验收，再实现、独立检查与修正</title>
      <defs><marker id="quality-loop-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 1 1 L 8 5 L 1 9" fill="none" stroke="var(--line)" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
      <path d="M290 55H430" fill="none" stroke="var(--line)" stroke-width="1.5" marker-end="url(#quality-loop-arrow)"/>
      <path d="M555 90V170" fill="none" stroke="var(--line)" stroke-width="1.5" marker-end="url(#quality-loop-arrow)"/>
      <path d="M430 205H290" fill="none" stroke="var(--line)" stroke-width="1.5" marker-end="url(#quality-loop-arrow)"/>
      <path d="M165 240V430" fill="none" stroke="var(--line)" stroke-width="1.5" marker-end="url(#quality-loop-arrow)"/>
      <path d="M290 225H360V300H555V240" fill="none" stroke="var(--line)" stroke-width="1.5" stroke-dasharray="4 4" marker-end="url(#quality-loop-arrow)"/>
      <g><rect x="40" y="20" width="250" height="70" rx="18" fill="var(--node)" stroke="var(--border)" stroke-width="1.5"/><g text-anchor="middle" fill="var(--ink)"><text x="165" y="52" font-size="17" font-weight="600">Planner</text><text x="165" y="75" font-size="13">产品规格与交付目标</text></g></g>
      <g><rect x="430" y="20" width="250" height="70" rx="18" fill="var(--node)" stroke="var(--border)" stroke-width="1.5"/><g text-anchor="middle" fill="var(--ink)"><text x="555" y="52" font-size="17" font-weight="600">Sprint Contract</text><text x="555" y="75" font-size="13">Generator 与 Evaluator 确认</text></g></g>
      <g><rect x="430" y="170" width="250" height="70" rx="18" fill="var(--node)" stroke="var(--border)" stroke-width="1.5"/><g text-anchor="middle" fill="var(--ink)"><text x="555" y="202" font-size="17" font-weight="600">Generator</text><text x="555" y="225" font-size="13">实现约定范围并自测</text></g></g>
      <g><rect x="40" y="170" width="250" height="70" rx="18" fill="var(--node)" stroke="var(--border)" stroke-width="1.5"/><g text-anchor="middle" fill="var(--ink)"><text x="165" y="202" font-size="17" font-weight="600">Evaluator</text><text x="165" y="225" font-size="13">运行应用，独立检查</text></g></g>
      <g><rect x="40" y="430" width="250" height="70" rx="18" fill="var(--success)" stroke="var(--success-border)" stroke-width="1.5"/><g text-anchor="middle" fill="var(--success-ink)"><text x="165" y="462" font-size="17" font-weight="600">通过验收</text><text x="165" y="485" font-size="13">继续下一范围或交付</text></g></g>
      <text x="405" y="322" text-anchor="middle" fill="var(--line)" font-size="13">不通过：问题反馈</text>
      <text x="165" y="380" text-anchor="middle" fill="var(--line)" font-size="13">满足约定标准</text>
    </svg>
  </div>
</figure>

这张图描述的是原文带 Sprint 的版本，并不表示所有长期开发都必须采用固定 Sprint。后面的简化实验，正是在检查这个结构里哪些部分仍然必要。

### 4. Sprint Contract：约定本轮范围与完成标准

产品规格通常描述“应该有什么”，Sprint Contract 则进一步明确：**这一轮交付哪些行为，怎样判断它们完成。**

Generator 提出实现范围和验证方式，Evaluator 在开发前检查是否遗漏关键路径。这样验收不是开发结束后临时追加要求，而是围绕双方已经确认的范围进行。

以“笔记自动保存”为例，一份自拟的简化约定可以写成：

> **范围：** 编辑正文并自动保存，不包含多人协作。  
> **验收：** 修改内容后出现保存状态；重新打开笔记仍能看到修改；请求失败时保留本地输入并显示可重试提示。  
> **检查方式：** 浏览器操作、保存请求与重新读取的数据相互对应。

这个约定比“完成自动保存功能”多了三类信息：用户能观察的行为、失败情况下的要求、验证依据。

同时，Contract 不应变成提前写完所有代码的设计书。把实现路径规定得过细，会把规划阶段的错误强加给后续开发；把验收写得过松，又容易出现有界面、没有完整行为的占位实现。

它的作用是约束交付结果，而不是消除开发者的全部判断。

### 5. Real-world QA：检查交互、接口与数据状态

独立 QA 的重点是验证应用怎样运行，而不只是检查源码里是否存在相关函数。

仍以自动保存为例，可以分三层观察：

1. **界面行为：** 输入是否保留，保存反馈是否清楚，失败后是否能够继续操作。
2. **接口行为：** 发出了什么请求，成功与失败怎样返回。
3. **数据状态：** 重新读取后是否得到刚才的内容，而不是旧数据或只存在前端内存中的值。

Playwright 等浏览器工具让 Evaluator 能够像用户一样操作应用，再结合接口与数据检查判断断点。三层证据相互补充：接口成功不能代替页面验证，截图正确也不能证明数据已持久化。

QA 返回的问题记录也应包含复现步骤与实际结果。比如“断网后继续输入，再恢复网络，内容没有重新保存”，比“存在网络异常问题”更容易驱动下一轮修正。

评价仍有能力与工具边界。新增一个 Evaluator 不等于覆盖了所有功能；如果它只点击首页，就无法检验深层编辑流程。需要检查的既包括应用，也包括 Evaluator 实际执行了哪些路径。

## 三、Harness 怎样通过实验持续简化

模型与任务变化以后，需要重新检查每个组件仍在解决什么问题。

### 6. Component Ablation：逐项移除并比较流程效果

Harness 的每个额外步骤，都在补偿某种不足：容易失去任务连贯性，就增加交接；容易缩小需求，就增加 Planner；容易漏掉功能，就增加 QA。

这些不足会随模型、任务和工具变化。因此，**过去有效的组件，不一定永远值得保留。**

原文呈现了两个不同阶段的调整：

- 较早使用 Sonnet 4.5 时，Context Reset 用于缓解长任务中的过早收尾；换用 Opus 4.5 后，这个实验能够取消强制 Reset，使用自动 Compaction 继续运行。
- 后来使用 Opus 4.6 时，作者移除了固定 Sprint，保留 Planner 与 Evaluator，将 QA 从逐 Sprint 检查改为整段开发后的检查与返修。

这不是“新模型不需要 Harness”的结论，而是模型可靠完成任务的范围发生了变化。一部分工作已经能够直接做好，另一部分边缘能力仍需要外部反馈。

**怎样判断删除是否合理？**

可以把组件与它原来要解决的问题一一对应，再逐项移除，比较结果：

| 组件 | 删除时应重点观察 |
| --- | --- |
| Planner | 功能范围是否缩小，关键用户路径是否遗漏 |
| 固定 Sprint | 实现是否失去连贯性，返工是否增加 |
| 独立 Evaluator | 真实功能缺口是否更多地进入最终产物 |
| 强制 Reset | 长任务是否再次过早收尾，交接成本是否值得 |

这些是用于分析的检查问题，不是实验已经证明适用于所有项目的结论。比较时还要看总耗时、调用成本和修正次数，而不能只看最终页面是否更丰富。

我更关注这个方法本身：先说明组件承担的职责，再用移除实验检查它是否仍然有效。**Harness 的改进既包括增加必要反馈，也包括删除已经不再承担关键作用的流程。**

## 几个关键问题，串起规划、独立验收与流程简化

**为什么长期运行不等于成果质量提高？**

持续性只保证工作能够接续。需求覆盖、设计质量和真实功能是否达标，仍需要独立标准与验证反馈。

**Context Reset 比 Compaction 更好吗？**

没有固定优劣。Reset 换取更清晰的起点，但依赖充分交接；Compaction 保留连续性，却可能延续此前偏差。应根据实际失败判断，而不是默认每轮重置。

**Evaluator 独立运行，是否就足够可靠？**

不够。它需要可操作标准、真实观察和判断校准，也要检查其测试范围。角色分离改善反馈结构，不保证每次评价正确。

**Sprint Contract 与普通任务列表有什么区别？**

任务列表说明要做什么；Contract 明确本轮结果、验收路径与完成条件。它把高层规格连接到可以实际检查的行为。

**为什么独立 QA 不能只看截图？**

截图观察视觉状态，无法完整证明交互、接口和持久化行为。真实操作与底层状态需要配合检查。

**取消 Sprint 是否等于放弃规划和验收？**

不是。原文简化版仍保留 Planner 与 Evaluator，改变的是工作切分与检查时机，而不是取消目标与质量要求。

**模型升级后，为什么要重新检查 Harness？**

因为组件建立在旧能力边界上。应确认原有问题是否仍存在、组件是否仍带来收益，以及它增加的成本是否值得。

## 参考资料

- [Anthropic · Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps)
