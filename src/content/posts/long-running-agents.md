---
title: 'Long-running Agent：怎样跨多个 Context 持续完成任务？'
description: '理解 Initializer、Feature List、Progress File 与 Git 的分工，建立新会话恢复、增量实现、端到端验证和状态交接的完整流程。'
pubDate: 2026-10-13T13:00:00+08:00
category: notes
tags: [Agent, Anthropic, Harness, Long-running, 学习笔记]
draft: false
postType: metaOnly
---

[Agent Loop](/zh-cn/posts/codex-agent-loop/)解释了模型怎样根据工具结果继续行动。但一个软件项目可能需要很多轮开发，甚至跨越多个 Context Window。模型继续运行，不等于任务能够连续推进：上一轮的推理结束以后，下一轮要根据什么判断现状？

长期开发需要保存的不是每一句历史，而是**可核对的任务状态**：完整需求是什么、哪些功能已经验证、代码处于哪个版本，以及下一步从哪里开始。

Anthropic 的[《Effective harnesses for long-running agents》](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)给出了一种跨会话开发方案。本文围绕三个问题展开：

- **状态保存：** 功能清单、进度记录和 Git 各自承担什么职责。
- **增量开发：** 一轮工作怎样形成可验证、可交接的结果。
- **会话恢复：** 新 Context 怎样检查现状，而不是重新猜测项目进度。

## 一、长期任务怎样跨 Context 接续

先看连续开发在哪里中断，再明确首次会话需要为后续留下什么起点。

### 1. Long-running：跨会话开发的失败模式

长期任务经常在两个位置失去连续性。

**中断在实现过程里。** 一轮同时修改页面、接口和存储，Context 耗尽时只完成了一部分。下一轮看到文件已经存在，却不知道哪些能运行、哪些只是占位，也不知道失败是新引入的还是早就存在。

**把已有进展当成全部完成。** 页面能够打开、主要按钮已经出现，不代表原始需求全部满足。如果完整需求没有留下可检查的记录，下一轮容易根据眼前的成果判断项目已经结束。

Compaction 可以压缩历史，让模型保留重要信息，但它与项目状态管理承担不同职责。摘要主要描述此前发生过什么；需求清单则必须保留尚未完成的目标，验证记录必须对应某份真实代码。

例如，摘要写着“已加入文章搜索”，仍然留下几种可能：只写好了搜索框，查询能返回结果，或者筛选、空结果与移动端交互都验证过了。**同一句历史描述，不能代替明确的完成条件。**

因此，压缩和外部状态并不互斥：摘要帮助恢复背景，项目材料提供可逐项核对的事实。长期开发需要把“发生过什么”和“现在可以确认什么”分开。

### 2. Initializer：准备环境与完整任务清单

Initializer 是首次运行的初始化角色。它的产出不应只是一批源码，还包括后续会话使用的工作约定：怎样启动项目、怎样判断功能完成、怎样记录进度。

原文实验里的 Initializer 与后续 Coding Agent 使用相同的 Harness 和工具，主要区别在于首次提示词。**初始化是一种工作阶段，不必为了它另造一套 Runtime。**

一个最小起点可以包含：

| 材料 | 解决的问题 |
| --- | --- |
| 环境启动脚本，如 `init.sh` | 怎样启动应用并进入可测试状态 |
| 功能清单，如 `feature_list.json` | 完整需求包含什么，哪些尚未完成 |
| 进度文件，如 `claude-progress.txt` | 当前工作位置和交接说明 |
| Git 初始提交 | 初始化实际增加了哪些文件 |

启动脚本的价值在于让操作可重复，而不是保证环境永远不出错。依赖、端口或服务状态变化以后，仍需检查启动结果。

下面以一个假设的课程笔记应用为例：用户要求笔记编辑、标签筛选和关键词搜索。Initializer 需要把这些目标转成可观察的行为，而不是只建好三个组件就算完成准备。

## 二、任务状态怎样记录与更新

完整需求、进度解释和实际代码需要分别保存，再通过一轮可验收的工作保持对应。

### 3. Feature List、Progress File 与 Git：记录需求、进度与代码

这三类材料分别回答三个问题：**还要做什么、之前做了什么、代码实际变成了什么。**

**Feature List：保存需求和验收状态**

一项功能应当写到能够测试的粒度。例如，搜索不是“有搜索模块”，而是用户输入关键词后能看到匹配笔记，并能识别无结果状态。

下面是自拟的简化记录：

```json
{
  "id": "search-notes",
  "description": "用户可以按关键词搜索笔记",
  "checks": [
    "输入正文中存在的关键词，显示对应笔记",
    "输入不存在的关键词，显示空结果提示",
    "清空关键词，恢复完整列表"
  ],
  "passes": false
}
```

这里最重要的不是 JSON 语法，而是**需求不会因实现困难而被悄悄缩小**。状态应依据测试更新；需求本身发生变化，则应明确记录变更，而不是把失败的检查直接删掉。

**Progress File：保存交接所需的解释**

进度记录补充代码没有直接表达的信息，例如：

> 本轮完成搜索接口与列表联动，正常查询和空结果已验证。清空关键词后列表没有恢复，仍未通过。问题位于筛选状态重置；本轮未修改标签功能。

下一轮据此可以定位缺口，也知道哪些范围没有处理。它不需要复述所有搜索和尝试，而应保留结果、依据、未完成项与必要提醒。

**Git：保存实际修改和可恢复版本**

Git 能说明本轮改了哪些文件、不同修改如何演进，并提供可恢复的代码版本。但提交存在，不代表功能正确；一个名叫“完成搜索”的 commit，也不能自动成为验收证据。

三者需要相互对应：清单里的通过状态应能找到验证依据，进度应说明对应的代码位置，提交则保存那份实际产物。出现矛盾时，应回到代码和测试核查，而不是只相信某一份说明。

### 4. Incremental Progress：完成可以验证和交接的功能

增量不是机械地限制修改行数，而是控制一轮工作的范围，使它能够完整实现、验证并交接。

例如，“加入笔记搜索”可以成为一个闭环：从输入关键词，到查询和显示结果，再到空结果与清空行为。只实现输入框、把后端和验证留给下一轮，仍然是没有闭合的功能。

<figure class="not-prose" style="margin:1.75em 0;">
  <figcaption style="font-size:.8125rem;color:var(--muted-foreground);margin-bottom:1rem;text-align:center;">图 1 · 项目材料把首次初始化、当前会话和新 Context 连接起来</figcaption>
  <div role="region" aria-label="图 1 · 项目材料把首次初始化、当前会话和新 Context 连接起来，可横向滚动" tabindex="0" style="overflow-x:auto;max-width:100%;border-radius:16px;padding:8px 0;background:hsl(0 0% 50% / .025);">
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 530" role="img" aria-labelledby="handoff-state-title" style="display:block;width:100%;min-width:580px;height:auto;font-family:var(--font-sans);--node:light-dark(#e8f3fc,#142b3e);--ink:light-dark(#235e89,#c0def4);--border:light-dark(#d0e0ed,#355167);--line:light-dark(#8e959d,#8295a6);--success:light-dark(#e5f6eb,#152f26);--success-ink:light-dark(#286447,#a9debf);--success-border:light-dark(#afd3bc,#426c57);">
      <title id="handoff-state-title">图 1 · 项目材料把首次初始化、当前会话和新 Context 连接起来</title>
      <defs><marker id="handoff-state-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 1 1 L 8 5 L 1 9" fill="none" stroke="var(--line)" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
      <path d="M290 55H430" fill="none" stroke="var(--line)" stroke-width="1.5" marker-end="url(#handoff-state-arrow)"/>
      <path d="M555 90V160" fill="none" stroke="var(--line)" stroke-width="1.5" marker-end="url(#handoff-state-arrow)"/>
      <path d="M430 195H290" fill="none" stroke="var(--line)" stroke-width="1.5" marker-end="url(#handoff-state-arrow)"/>
      <path d="M165 230V300" fill="none" stroke="var(--line)" stroke-width="1.5" marker-end="url(#handoff-state-arrow)"/>
      <path d="M290 335H430" fill="none" stroke="var(--line)" stroke-width="1.5" marker-end="url(#handoff-state-arrow)"/>
      <path d="M555 370V440" fill="none" stroke="var(--line)" stroke-width="1.5" marker-end="url(#handoff-state-arrow)"/>
      <g><rect x="40" y="20" width="250" height="70" rx="18" fill="var(--node)" stroke="var(--border)" stroke-width="1.5"/><g text-anchor="middle" fill="var(--ink)"><text x="165" y="52" font-size="17" font-weight="600">Initializer</text><text x="165" y="75" font-size="13">首次建立环境与任务边界</text></g></g>
      <g><rect x="430" y="20" width="250" height="70" rx="18" fill="var(--node)" stroke="var(--border)" stroke-width="1.5"/><g text-anchor="middle" fill="var(--ink)"><text x="555" y="52" font-size="17" font-weight="600">项目交接材料</text><text x="555" y="75" font-size="13">功能清单 · 进度 · Git</text></g></g>
      <g><rect x="430" y="160" width="250" height="70" rx="18" fill="var(--node)" stroke="var(--border)" stroke-width="1.5"/><g text-anchor="middle" fill="var(--ink)"><text x="555" y="192" font-size="17" font-weight="600">恢复与基线检查</text><text x="555" y="215" font-size="13">读取材料，验证项目现状</text></g></g>
      <g><rect x="40" y="160" width="250" height="70" rx="18" fill="var(--node)" stroke="var(--border)" stroke-width="1.5"/><g text-anchor="middle" fill="var(--ink)"><text x="165" y="192" font-size="17" font-weight="600">实现一项功能</text><text x="165" y="215" font-size="13">完成端到端验证</text></g></g>
      <g><rect x="40" y="300" width="250" height="70" rx="18" fill="var(--success)" stroke="var(--success-border)" stroke-width="1.5"/><g text-anchor="middle" fill="var(--success-ink)"><text x="165" y="332" font-size="17" font-weight="600">保存可接续状态</text><text x="165" y="355" font-size="13">更新清单、进度与提交</text></g></g>
      <g><rect x="430" y="300" width="250" height="70" rx="18" fill="var(--node)" stroke="var(--border)" stroke-width="1.5"/><g text-anchor="middle" fill="var(--ink)"><text x="555" y="332" font-size="17" font-weight="600">新会话接手</text><text x="555" y="355" font-size="13">重新读取并核对项目状态</text></g></g>
      <g><rect x="430" y="440" width="250" height="70" rx="18" fill="var(--success)" stroke="var(--success-border)" stroke-width="1.5"/><g text-anchor="middle" fill="var(--success-ink)"><text x="555" y="472" font-size="17" font-weight="600">推进下一项功能</text><text x="555" y="495" font-size="13">继续遵守恢复与交接约定</text></g></g>
      <text x="360" y="322" text-anchor="middle" fill="var(--line)" font-size="13">跨 Context</text>
    </svg>
  </div>
</figure>

每轮可以按同一套步骤组织：

1. 从完整清单选择一项优先工作，确认依赖已经具备。
2. 实现功能及必要的测试，不同时铺开无关改动。
3. 按用户路径验证结果，检查已有能力是否被破坏。
4. 根据实际结果更新功能状态与进度。
5. 保存清楚的代码变更，为下一轮留下可使用的起点。

原文采用每轮一项功能的约束。它的作用是防止范围不断扩张，而不是证明所有项目都只能按同一种大小切分。

如果本轮无法完成，交接时应准确标记未完成状态、失败证据和已修改范围。干净交接不是把所有状态写成成功，也不是为了得到一个整洁提交而隐藏问题；它要求下一轮能辨认并接续当前工作。

## 三、新会话怎样恢复和验证项目

交接材料提供入口，当前代码与运行结果则用来核对这个入口是否仍然可信。

### 5. Session Handoff：恢复环境与核对已有进度

这里的 Handoff 指跨会话交接项目状态，不是上一篇编排文章中切换执行 Agent 的协议操作。

新会话的第一项工作，不应是立即实现下一功能，而是建立对当前项目的可信认识。

**读取任务与代码状态**

先确认工作目录，检查当前修改、最近提交和进度，再看完整功能清单。这一步把目标、解释和实际代码对应起来，也能发现进度记录落后于源码的情况。

**启动环境，验证基本路径**

对于课程笔记应用，可以先打开列表、进入一篇已有笔记，再执行一条已完成的查询。基线检查不需要重复全部验收，但要覆盖足以判断项目能否继续开发的关键路径。

如果基本路径已经损坏，应先定位原因。否则继续增加功能，会把原有故障和新修改混在一起，下一次更难判断是哪一步出了问题。

**根据当前证据选择任务**

恢复完成后，再从未通过的清单里选择工作。最近进度写着“接下来做标签”，并不意味着无需查看实际依赖；如果搜索仍有未解决的回归，应调整顺序并说明原因。

这个流程的目的，是让新 Context 快速恢复必要信息，而不是把整个旧会话重新加载一遍。

### 6. End-to-end Testing：验证功能的实际完成状态

代码检查、单元测试和端到端测试观察的是不同层次。

搜索函数能返回数据，不代表界面正确显示；接口请求成功，也不代表用户清空关键词后能恢复列表。**功能完成需要验证声明中的那条用户路径。**

对 Web 应用，可以通过浏览器实际输入、点击、切换页面，观察显示与状态变化；必要时再结合请求、日志和数据检查解释失败原因。

测试范围要与功能声明一致。“桌面端正常查询通过”不能被写成“所有搜索交互完成”。验证工具也有观察边界：没有覆盖到的交互，不应被默认为已经检查。

因此，完成判定应形成一条对应关系：

> 功能要求 → 可执行的检查 → 观察到的结果 → 更新完成状态

我认为这套交接设计最有价值的地方，是让长期开发不依赖某一轮模型对历史的模糊记忆。每轮都能留下可读的说明、可检查的结果和可恢复的代码，下一轮才有可靠的起点。

## 几个关键问题，串起状态记录、增量开发与恢复

**有 Compaction，为什么还需要项目状态文件？**

压缩帮助延续背景，状态文件则明确保存需求、完成条件和交接位置。两者用途不同，摘要不能自动证明某项功能已经通过。

**Initializer 是一套独立的 Agent Runtime 吗？**

不一定。原文实验主要通过首次提示词区分初始化与后续开发，工具和 Harness 相同。角色差异不等于底层实现必须不同。

**为什么不能只保留 Git？**

Git 保存修改与版本，但不直接表达完整需求、尚未完成的任务和交接解释。它需要与功能清单、进度记录配合。

**Incremental Progress 等于每轮少改几行吗？**

不是。重点是工作范围能形成实现、验证、记录的闭环。小补丁也可能只留下半成品，较大改动也可能具有清晰边界。

**新会话为什么要检查已完成功能？**

因为当前代码可能已经发生变化，进度记录也可能过时。基线检查确认当前起点可用，避免在损坏状态上叠加新功能。

**什么时候可以把功能标为完成？**

相关验收路径得到实际验证，结果与声明范围一致时。生成了代码、提交了修改，或者 Agent 口头宣布完成，都不足以单独支持这个状态。

## 参考资料

- [Anthropic · Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
