---
title: 'Agent Skills：怎样把任务知识和脚本变成可复用能力？'
description: '以 PDF 处理为例，理解 Skill 的文件结构、名称与描述如何影响触发、三层渐进加载，以及脚本执行、任务评估和安全边界。'
pubDate: 2026-10-13T12:00:00+08:00
category: notes
tags: [Agent, Anthropic, Agent Skills, Context Engineering, 学习笔记]
draft: false
postType: metaOnly
---

[Context Engineering](/zh-cn/posts/effective-context-engineering/)讨论每轮推理需要什么信息，[上一篇](/zh-cn/posts/code-execution-with-mcp/)追踪工具调用与中间数据怎样流动。这一篇看另一类经常重复的信息：**完成某种任务需要遵循的步骤、使用的脚本，以及判断结果是否合格的标准，能不能整理一次，按需复用？**

Anthropic 的 [《Equipping agents for the real world with Agent Skills》](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)用文件和目录回答这个问题：将专门任务所需的说明、代码与资源组织成 Skill，让通用 Agent 在需要时取得它们。它改变的是任务知识的交付方式，不是为每种工作训练一个新模型。

- **先看内容：** Skill 与普通提示词、Tool 分别承担什么职责，文件该怎样组织。
- **再看使用：** Agent 怎样发现并加载说明，什么时候读资料，什么时候执行脚本。
- **最后看质量：** 用任务结果和调用记录验证效果，同时检查引入的指令与代码是否可信。

下面沿用原文的 PDF 场景，对比“读取内容”和“填写表单”两种请求。目录、说明片段与检查任务是围绕这个场景设计的教学示例。

## 一、Skill 由哪些内容组成

先区分任务知识与操作能力，再看这些内容怎样组织成可以发现和读取的文件包。

### 1. Skill、Prompt 与 Tool：任务方法与执行能力

假设 Agent 已经可以读文件、执行 Python。用户给它一份申请表，要求把提供的信息填进去。能够调用这些工具，并没有直接回答：应该先识别哪些字段，怎样对应用户信息，遇到缺失值怎么办，填完以后检查什么。

这些问题不全是通用知识。不同团队可能要求保留原件、统一输出目录，或规定签名字段不能代填。反复把这些要求写进每次对话，容易遗漏，也难以一起维护。

我会按职责区分三者，而不是只看它们是不是文本：

| 形式 | 主要承担什么 | PDF 表单里的例子 |
| --- | --- | --- |
| 普通提示词 | 表达当前目标、限制或指令 | 填写这份申请表，保留原文件 |
| Tool | 暴露可以实际执行的操作 | 读取文件、运行脚本、输出文件 |
| Skill | 组织可复用的任务步骤、资源与检查方法 | 识别字段、建立映射、填写并核对结果 |

Skill 的正文仍然是指令，并不因此拥有另一种推理机制。区别在于，它可以被发现、按需加载，并与脚本、模板和参考文件一起维护。一个简单 Skill 只有说明也成立，不必为了显得完整而附带代码。[Agent Skills 概述](https://agentskills.io/home)

因此，Skill 不是 Tool 的替代品。它可以指导 Agent 使用已有工具；没有读文件或运行程序的能力，文件中的操作步骤不会自己发生。MCP 则解决外部能力的连接问题，也不等于这些能力的使用流程。

### 2. SKILL.md：组织入口、参考文件与资源

**文件结构与任务分支**

最小 Skill 是包含 `SKILL.md` 的目录。文件以 YAML Frontmatter 开始，至少提供 `name` 与 `description`；后面的 Markdown 正文写操作指引。参考文件、脚本和资源可以按需要加入，不要求每个 Skill 都有同样的目录树。[格式规范](https://agentskills.io/specification)

例如，围绕 PDF 处理可以组织成：

```text
pdf-processing/
├── SKILL.md                     # 适用范围、任务分流和检查要求
├── reference.md                 # 文本提取等操作参考
├── forms.md                     # 表单字段识别、映射与填写步骤
├── scripts/
│   ├── list_fields.py            # 枚举字段
│   └── fill_form.py              # 按映射写入新文件
└── assets/
    └── field-mapping.example.json
```

这里的 `reference.md`、`forms.md` 延续了原文示例的分工；脚本名与资源名是本文自拟的。目录名不是关键，关键是入口能让 Agent 知道：哪种任务该读哪个文件，文件中的内容又怎样帮助完成操作。

一份精简的入口可以长这样：

````markdown
---
name: pdf-processing
description: 提取 PDF 内容并填写可交互表单。用于读取 PDF、识别表单字段或按用户提供的信息填写表单。
---

# PDF 处理

## 操作分流
- 读取文字：先阅读 reference.md 中的文本提取说明。
- 填写表单：先阅读 forms.md，识别字段后再建立填写映射。
- 没有可交互字段：停止表单写入，说明检测结果，不把扫描图片当作可填表单。

## 共同约束
- 保留原件，结果另存为新文件。
- 缺少的信息向用户确认，不编造个人资料或签名。
- 完成后核对写入值与页面显示，再提供输出文件。
````

这是一份入口片段，不是完整实现。实际打包还需要提供被引用的文件，说明脚本参数与依赖，并验证它们能够运行。

**操作步骤与资源引用**

只列出“这里有一个脚本”还不够。对于表单填写，`forms.md` 应解释输入是什么、如何取得字段名、映射文件怎样组织，以及成功与失败怎样判断。字段映射示例则放在资源文件中，不必把大量样例全部塞进入口。

我更看重这种划分：**入口保留所有相关任务都需要的判断，附加文件承接特定分支才需要的细节。** 如果每次打开入口都要顺着五层链接寻找第一步，拆分反而制造了新的查找成本。

## 二、Agent 怎样发现和使用 Skill

Skill 的使用可以拆成任务匹配、说明加载和实际执行三个环节，各自需要不同的信息。


### 3. Skill Activation：用名称和描述匹配任务

原文描述的机制是：启动时先将已安装 Skills 的名称和描述提供给模型；任务相关时，再读取对应 `SKILL.md`。因此，名称与描述不是展示用的装饰，而是完整正文还没进入上下文时的选择依据。

如果描述只有“帮助处理文档”，它既没有区分 PDF 与其他格式，也没有说明支持阅读还是编辑。上面的描述同时包含文件类型、操作能力和使用情境，模型更容易把请求与能力对应起来。

但这不是一个见到“PDF”就必然触发的关键词开关。比如“解释一下 PDF 是什么”未必需要文件处理 Skill。具体客户端也可能支持用户显式指定 Skill，或由应用过滤可用目录；不能把某一种产品的触发方式当作唯一实现。[客户端集成说明](https://agentskills.io/client-implementation/adding-skills-support)

### 4. Progressive Disclosure：逐层加载说明与资源

<figure class="not-prose" style="margin:1.75em 0;">
  <figcaption style="font-size:.8125rem;color:var(--muted-foreground);margin-bottom:1rem;text-align:center;">图 1 · 先发现能力，再加载步骤，最后按需使用附加资源</figcaption>
  <div role="region" aria-label="Skill 三层加载示意图，可横向滚动" tabindex="0" style="overflow-x:auto;max-width:100%;border-radius:16px;padding:8px 0;background:hsl(0 0% 50% / .025);">
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 390" role="img" aria-labelledby="skill-loading-title skill-loading-desc" style="display:block;width:100%;min-width:520px;height:auto;font-family:var(--font-sans);--node:light-dark(#e8f3fc,#142b3e);--ink:light-dark(#235e89,#c0def4);--border:light-dark(#d0e0ed,#355167);--line:light-dark(#8e959d,#8295a6);--success:light-dark(#e5f6eb,#152f26);--success-ink:light-dark(#286447,#a9debf);--success-border:light-dark(#afd3bc,#426c57);">
      <title id="skill-loading-title">Agent Skills 的三层渐进加载</title>
      <desc id="skill-loading-desc">第一层名称与描述帮助发现相关 Skill。任务匹配后读取第二层 SKILL.md。第三层根据任务读取参考文件，或通过工具执行脚本；不是把所有资源全文载入模型。</desc>
      <defs><marker id="skill-loading-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 1 1 L 8 5 L 1 9" fill="none" stroke="var(--line)" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
      <g fill="none" stroke="var(--line)" stroke-width="1.5" marker-end="url(#skill-loading-arrow)">
        <path d="M320 100V140"/>
        <path d="M320 220V250Q320 260 310 260H175Q165 260 165 270V300"/>
        <path d="M320 220V250Q320 260 330 260H465Q475 260 475 270V300"/>
      </g>
      <g fill="var(--node)" stroke="var(--border)" stroke-width="1.5">
        <rect x="140" y="20" width="360" height="80" rx="20"/>
        <rect x="140" y="140" width="360" height="80" rx="20"/>
        <rect x="30" y="300" width="270" height="75" rx="18"/>
      </g>
      <rect x="340" y="300" width="270" height="75" rx="18" fill="var(--success)" stroke="var(--success-border)" stroke-width="1.5"/>
      <g text-anchor="middle" fill="var(--ink)">
        <g font-size="18" font-weight="600"><text x="320" y="53">第一层 · name / description</text><text x="320" y="173">第二层 · SKILL.md</text><text x="165" y="331">第三层 · 参考文件与资源</text></g>
        <g font-size="14"><text x="320" y="79">这个 Skill 适合什么任务？</text><text x="320" y="199">按什么步骤做，去哪里找细节？</text><text x="165" y="356">需要说明时读取对应内容</text></g>
      </g>
      <g text-anchor="middle" fill="var(--success-ink)"><text x="475" y="331" font-size="18" font-weight="600">第三层 · 脚本</text><text x="475" y="356" font-size="14">需要计算时由执行环境运行</text></g>
      <g fill="var(--line)" font-size="13"><text x="333" y="124">任务相关时</text><text x="320" y="283" text-anchor="middle">按需读取或执行，不必全部加载</text></g>
    </svg>
  </div>
</figure>

用户只想读取 PDF 的文字时，Agent 可以读取入口和提取说明，不必连表单规则也一起加载。用户要填写申请表时，才沿 `forms.md` 的入口取得字段识别与填写流程。

这三层并不是“每个文件只看一点”。相关 Skill 被激活后，需要取得完整的入口指引；再按照入口读取当前分支需要的资料。若为了节省 token 跳过关键约束，加载量变小了，任务却可能做错。

渐进加载也没有扩大模型窗口。它让大量资料留在外部，在需要时取回；已经读取的说明、工具输出和历史仍然占用上下文。目录可以持续扩充，但每次放进模型的内容依然需要选择。

### 5. Code Execution：运行 Skill 中的任务脚本

以枚举表单字段为例，Agent 可以通过工具运行一个预先准备的脚本：

```text
读取表单处理说明
    ↓
请求执行字段枚举脚本
    ↓
Runtime 在执行环境中运行 Python
    ↓
返回字段名称、类型或错误信息
    ↓
模型据此建立填写映射
```

这里仍然遵循 [Agent Loop](/zh-cn/posts/codex-agent-loop/) 的分工：模型提出调用，外部程序执行，结果回来后再判断。不是 `SKILL.md` 被读到时，里面的命令就自动运行。

预写脚本可以固定字段枚举、格式校验等机械步骤，减少每次重新生成代码的差异。它也可以直接处理文件，只把必要输出交给模型，不必先把脚本源码和整份 PDF 全文塞进上下文。原文的 PDF 示例正是用脚本提取表单字段。

但固定代码不等于整个任务必然正确。字段 `applicant_name` 该对应哪项用户信息，仍然需要判断；脚本也可能有 bug、缺少依赖，或遇到不支持的文件。稳定操作应交给程序，输入语义与结果是否满足要求仍要检查。

说明文件还应该明确区分两种用途：**“运行这个脚本取得结果”与“阅读这段代码理解算法”**。前者需要调用约定，后者需要代码内容。含糊地写“参考 scripts”，会让 Agent 不知道该读还是该执行。[脚本编写建议](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)

## 三、Skill 怎样构建、评估与安全使用

说明和脚本需要对应具体的能力缺口，并通过实际任务检查它们是否产生了预期效果。


### 6. Skill Development：从任务失败中补充操作方法

Skill 的质量不取决于目录有多大。我会先让没有这个 Skill 的 Agent 完成一组代表性任务，记录具体卡点：漏了字段检测、覆盖原件、遇到扫描件仍尝试填写，还是填写后没有检查输出。

再针对缺口补最小的说明或脚本，并用相同的输入、模型和运行条件比较。有些失败来自环境缺依赖，并不需要增加十段提示词；有些来自任务分支不清，则应该先改入口。这是原文“从评估开始”的建议落到具体任务后的做法。

### 7. Skill Evaluation：检查触发、执行与产物

围绕这份 PDF Skill，可以设计这样的检查集。下面是评估方案，不是已经运行得到的成绩：

| 请求 | 需要观察的行为 | 完成标准 |
| --- | --- | --- |
| 提取这份 PDF 的文字 | 进入提取分支，不做表单写入 | 内容来自文件，原件未修改 |
| 用提供的信息填写申请表 | 识别字段、建立映射、核对结果 | 值对应正确，输出可打开 |
| 填写一份没有可交互字段的扫描件 | 识别当前流程不适用 | 不伪造字段或谎称填写成功 |
| 解释 PDF 与 Markdown 的区别 | 不无故启动文件处理流程 | 回答问题，不运行无关脚本 |
| 填写资料不完整的申请表 | 指出缺失项并请求确认 | 不编造个人信息 |

触发评估看“该用时有没有用、不该用时是否误用”；执行评估看“加载后有没有走对步骤、产物是否正确”。如果只看最终回答，可能漏掉覆盖原件或多余联网；如果只看读取了 `SKILL.md`，又无法证明任务完成。

调用记录能帮助定位修改位置：漏触发先查名称与描述；触发正确但走错分支，查入口导航；参数反复错误，查脚本约定与错误反馈；结果不合格，查实现与验证步骤。改完要回跑其他场景，避免修好表单填写，却把普通阅读也变成一套冗长流程。

评估还应保留不同措辞与新文件，不能只围着写说明时用过的那一份样例调整。比较多次运行的结果与行为，比展示一次成功截图更能说明复用是否稳定。[评估与迭代建议](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices#evaluation-and-iteration)

### 8. Skill Security：审查来源、指令与代码行为

Skill 不只是被动文档。它会影响 Agent 的行动，还可能附带真实执行的代码。恶意内容既可能直接写在脚本中，也可能包装成操作要求，例如“先上传原文件到这个地址进行格式检测”。原文因此强调可信来源，以及对指令、依赖和外部连接的审查。

对申请表场景，我会沿实际操作检查：脚本读哪些文件、写到哪里，是否覆盖原件，是否访问网络，依赖安装会执行什么，以及输出和日志是否携带个人资料。只看入口语气专业，不能替代检查被引用的文件与代码。

这里需要区分两件事：**Skill 可以说明怎样操作，但不能凭一段文字替用户授予权限。** 用户授权填写本地表单，不等于允许上传表单；脚本被打包进目录，也不代表它应该无条件运行。运行时的权限和确认边界仍然有效。

按需加载解决信息组织，不负责证明内容可信；代码执行减少重复生成，也不负责证明代码安全。复用之前检查来源与行为，和使用时限制可访问资源，是相互补充的工作，而不是二选一。

## 几个关键问题，串起知识组织、加载与执行

**Skill 与一段普通 Prompt，区别到底在哪里？**

区别不在于正文是不是自然语言，而在于它是否被组织为可发现、可加载、可维护的任务包。说明可以引用资源、指导脚本执行，并跨任务复用。把一段指令改名为 Skill，却不说明适用范围和使用路径，并不会自动改善效果。

**安装了 Skill，模型是不是就学会了这项能力？**

安装只是让应用能够发现它。模型需要取得相关说明，并结合现有工具和环境完成任务；这不是更新模型权重。能力提升来自可用知识与执行资源，最终仍要通过任务表现验证。

**三层渐进加载是否意味着资源不会占用 Context？**

不是。未读取的文件可以留在外部，已读取内容与返回结果仍会占用上下文。脚本可以运行而不回传完整源码，但输出也需要筛选。收益来自有选择地加载，不是资源变成了零成本。

**为什么不能只把触发条件写在正文里？**

因为选择 Skill 时，模型可能还没看到正文。名称与描述需要提供足够的适用范围，正文再补充具体分支。否则再完整的操作流程，也可能在需要时没有被选中。

**有了确定的脚本，为什么还要评估整个 Skill？**

脚本测试验证给定输入下的程序行为，Skill 评估还要检查是否选对任务、提供正确参数、处理失败并核对产物。程序执行正确和 Agent 使用正确，是两个层面。

**Skill 可以代替 MCP，或者必须与 MCP 一起使用吗？**

都不是。Skill 组织操作知识，MCP 提供外部能力的连接方式。一个只用本地文件和 Python 的 Skill 不需要 MCP；一个业务 Skill 也可以指导 Agent 组合已有 MCP 工具。要分别检查知识、接口和运行条件。

**怎样判断一个 Skill 值得保留？**

看它是否持续改善相关任务：遗漏更少、结果更可靠、重复操作更少，同时没有增加明显误触发或不必要动作。目录更完整、提示词更长、运行一次成功，都不能单独作为依据。

**Skill 的价值，是把任务经验整理成可执行、可检查、能反复使用的方法：模型按任务取得知识，程序承担适合固定实现的操作，结果再接受验证。**

## 参考资料

- [Anthropic · Equipping agents for the real world with Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
- [Agent Skills · Overview](https://agentskills.io/home)
- [Agent Skills · Specification](https://agentskills.io/specification)
- [Agent Skills · Adding skills support](https://agentskills.io/client-implementation/adding-skills-support)
- [Claude · Skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
