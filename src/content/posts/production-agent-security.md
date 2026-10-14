---
title: 'Production Agent Security：怎样统一管理权限、审计与安全响应？'
description: '以 OpenAI 内部使用 Codex 的治理实践为例，理解受管配置、Sandbox 与审批、命令规则、网络与身份控制，以及 Agent 日志怎样支持安全调查和策略改进。'
pubDate: 2026-10-14T18:46:41+08:00
category: notes
tags: [Agent, OpenAI, Security, Governance, 学习笔记]
draft: false
postType: metaOnly
---

[上一篇](/zh-cn/posts/agent-sandbox/)解释了操作系统怎样约束工具进程。把 Agent 放到团队开发流程里，还需要回答另一组问题：不同开发者使用的权限是否一致？谁能批准例外？如果某次执行触发告警，安全团队能不能还原当时发生了什么？

OpenAI 的[《Running Codex safely at OpenAI》](https://openai.com/index/running-codex-safely/)提供了一个组织级案例。本文沿着一次任务的完整过程整理：先确定统一运行策略，再检查具体动作，随后管理外部连接和身份，最后用执行记录支持调查与策略调整。

仍以一个假设任务贯穿说明：开发者请 Agent 修复 CSV 解析错误、补测试并准备变更。正常工作包括读取项目、修改源码和运行测试；上传原始数据到外部网站、修改项目外配置，则不能因为“可能有助于排查”就自动获得许可。下面的情节用于说明治理关系，不代表已经在当前博客或电脑部署了这些控制。

## 一、组织怎样统一 Agent 的运行策略

### 1. Managed Configuration：强制要求与默认设置

个人设置解决“我希望怎样运行”，组织策略解决“在这里运行至少必须满足什么条件”。两者最重要的区别，是用户能不能改变它。

官方文档将 **Requirements** 与 **Configuration Defaults** 分开：前者是管理员强制执行的要求，后者提供初始设置，允许用户在支持的范围内调整。与强制要求冲突的本地配置，不能仅因来自用户文件或启动参数就覆盖它。[来源：Managed configuration](https://learn.chatgpt.com/docs/enterprise/managed-configuration)

例如，团队可以默认让开发任务在项目内写入，同时强制限制可选的权限范围。默认值让开发者启动后就能工作；强制要求则防止某个人为了少点几次批准，直接把组织禁止的运行方式打开。

这也说明，**统一分发配置，不等于统一执行约束**。如果分发的是可修改的默认值，用户仍然能改；如果确实需要不可覆盖的限制，就要把它放进对应的强制策略，而不是只写在操作手册里。

### 2. Policy Scope：客户端、执行环境与生效范围

一条策略还要说明它约束谁、在哪里生效。桌面客户端、CLI、IDE 扩展可能都能发起任务，但本机进程与云端执行环境不是同一个落点。

OpenAI 的案例通过云端管理、设备管理和本地要求文件组合下发配置。理解这里的治理方式，关键不是记住所有配置来源的优先级，而是区分：**谁管理策略，哪个客户端读取策略，哪个执行环境实际落实限制。**

对于 CSV 任务，可以先在一个受管环境里检查两类行为：正常修改项目文件能否完成；尝试写入禁止位置时，是否确实被拒绝。同样的检查还要覆盖组织实际使用的其他执行路径，不能把本机验证结果直接当作云端也已受控。

这些检查关注的是策略的有效范围，不是让各团队自行绕开基线。允许差异化的部分可以按环境配置，但真正生效的要求仍需核对客户端版本、执行位置和管理层配置。

## 二、一次动作怎样获得执行许可

### 3. Sandbox 与 Approval：执行边界和例外审查

Sandbox 描述当前执行环境允许做什么；Approval Policy 决定什么动作需要额外审查。两者不是“严格模式”和“宽松模式”的二选一。

在 CSV 任务中，修改项目源码可以在既有边界内完成；写入项目外配置则可能触发权限请求。此时应该审查的是**具体目标、动作和必要性**，而不是给整个任务补一句“都可以”。

| 检查层次 | 对 CSV 任务提出的问题 |
| --- | --- |
| 组织要求 | 当前环境允许申请这种权限吗？ |
| 执行边界 | 当前进程能否直接访问目标资源？ |
| 审批判断 | 这次额外访问是否必要，是否得到相应授权？ |
| 实际执行 | 最终获得的权限是否足够完成获准动作？ |

批准不是修改组织禁令的通用开关，也不保证操作系统或目标服务必然放行。它只在组织允许的例外机制内，对相应请求作出决定。

原文还介绍了 Auto-review：把待执行动作和近期上下文交给自动审查者，减少常规请求对用户的打断。这里需要区分的是，**自动化的是部分审查工作，不是取消执行边界**。审查者仍然可能判断错误，因此它不能替代 Sandbox 或组织要求。

### 4. Command Rules：命令匹配与放行范围

除了结合上下文判断，还可以把经常出现的命令模式写成规则。Codex 的 Rules 用于控制命令在 Sandbox 外的执行，支持 `allow`、`prompt`、`forbidden` 等决定；多个规则匹配时采用更严格的结果。[来源：Rules](https://learn.chatgpt.com/docs/agent-configuration/rules)

这与提示词里的“谨慎操作”不同：规则匹配的是实际命令参数，而不是模型对命令的解释。原文用只读 PR 查询说明可以预先放行的常见操作，但不能据此把整个 `gh` 命令入口都视为只读。

以我们的任务为例，“查看 PR”与“合并 PR”会产生不同影响；“运行某个已知测试”与“运行任意项目脚本”，也不是同一个范围。规则前缀越宽，覆盖的行为就越多，不能只凭程序名字看起来熟悉就放行。

复合 Shell 命令还可能包含多个动作。官方规则机制会在可以安全解析时分别检查子命令，不能安全拆分时则检查完整调用。**一个获准命令出现在开头，不代表后面附带的动作也获准。** 因此，验证规则时既要检查应当匹配的样例，也要检查不应匹配的样例。

## 三、Agent 的外部连接怎样管理

### 5. Network Policy：连接目标与访问通道

文件权限回答“能改哪里”，网络策略还要回答“能把信息送到哪里、能从哪里取回内容”。项目文件没有被破坏，不代表数据没有被上传。

对于 CSV 修复，访问批准的依赖服务与上传原始数据，是不同的动作。即使二者都通过 HTTP 完成，也不能共享一个模糊的“允许联网”判断。

OpenAI 的内部案例对目的地进行区分：已知目标按策略处理，禁止目标阻断，陌生目标需要额外审批。它还将 Web Search 限制为缓存模式。这里包含两类不同控制：**命令进程的网络访问**与**搜索工具取得网页内容的方式**，后者不能替代前者。

当前官方文档也强调：域名规则必须由对应的网络执行机制落实，写下允许列表本身不等于已经启动约束；命令网络策略也不自动覆盖所有 Web Search、App 或 MCP 通道。若允许完整的 Sandbox 升级，还要检查升级后的网络路径，不能只验证普通执行时的代理限制。[来源：Agent approvals & security](https://learn.chatgpt.com/docs/agent-approvals-security)

因此，在组织里检查“这份数据能否出去”，需要先找到实际通道：Shell 启动的程序、搜索工具，还是外部连接器。然后确认那个通道的策略，而不是看到某处配置了域名列表就结束。

域名获准也只说明可以连接该目标，不证明发送的每份数据都合适。把原始 CSV 上传到一个常用开发平台，仍然需要判断内容和用途；从可信站点取回的页面，也不能因此获得指挥 Agent 的权限。

### 6. Identity 与 Credentials：使用身份和凭证保管

联网目标确定后，还要知道以谁的身份访问。用户的 Codex 登录、工具进程的本机身份、外部服务的 OAuth 授权，是不同层次。

原文介绍了将 CLI 和 MCP OAuth 凭证保存在 OS Keyring，并把 Codex 登录绑定到指定企业 Workspace 的做法。前者管理凭证的存储位置，后者让使用归属到相应组织控制下；二者不能互相替代。

官方认证文档也区分登录方式、Workspace 权限和凭证存储。将凭证放进系统凭证库，并不等于改变凭证本身在目标服务拥有的权限。[来源：Authentication](https://learn.chatgpt.com/docs/auth)

例如，开发者使用企业 Workspace 登录 Codex，不代表某个 GitHub 连接只拥有读取权限；工具以受限本机用户运行，也不代表它持有的远程凭证只能访问测试环境。**本机执行身份与远程服务授权，需要分别检查。**

从这个区别出发，治理时就能把问题问具体：任务需要哪个账号、哪些资源和哪些操作？凭证由谁保管，工具是否真的需要接触它？不必把凭证正文放进 Prompt、项目文件或调查记录，才能说明某个调用使用了什么授权。

## 四、运行记录怎样支持审计与安全响应

### 7. Agent-native Telemetry：关联任务、审批与执行结果

传统终端记录可以告诉安全团队：哪个进程启动了、哪个文件发生变化、是否出现异常连接。Agent 记录补充的则是任务背景：用户要求什么、工具请求是什么、批准从哪里来，以及调用返回了什么结果。

两者要关联起来看。仅有进程告警，可能不知道动作对应哪个任务；仅有 Agent 的完成总结，又可能忽略实际执行失败或未获准的尝试。

原文介绍了通过 OpenTelemetry 导出相关事件，并与集中安全日志和合规记录配合使用。以一个假设的上传告警为例，调查需要串起下面这些信息，而不是只看“任务最终成功了”：

| 记录 | 帮助回答的问题 |
| --- | --- |
| 用户请求 | 修复 CSV 是否包含外传数据的授权？ |
| 工具请求 | 准备执行什么程序，目标是什么？ |
| 审批决定 | 请求获准还是被拒，决定来自哪里？ |
| 网络决定 | 哪个目的地被允许或阻断？ |
| 工具与终端结果 | 请求停在检查阶段，还是发生了实际传输？ |

这是调查所需信息的示意，不是一套固定事件 Schema，也不意味着每种日志默认保存全部内容。官方 OTel 文档中，用户 Prompt 正文默认不记录，工具结果也可能只是片段。缺失记录时，不能把“没有看到”直接写成“没有发生”。[来源：Observability and telemetry](https://learn.chatgpt.com/docs/config-file/config-advanced#observability-and-telemetry)

因此，日志策略本身也需要治理：记录哪些字段、谁能查、保留多久，以及如何减少敏感数据暴露。审计有用的前提是能关联并核对关键事件，不是把全部对话和文件内容无限保存。

### 8. Security Triage：告警关联与人工判断

Security Triage 是对告警进行初步调查和分流：哪些属于预期工作，哪些是误操作，哪些需要进一步响应。它不是看到 Agent 参与就自动认定攻击，也不是看到用户说过“修复问题”就为所有动作免责。

在 CSV 场景中，同一个外联告警可能有不同解释：获准获取依赖、误把数据发送到错误目标，或受到外部内容诱导而尝试上传。要区分它们，需要核对请求、目标、授权和实际结果。

OpenAI 的案例使用安全分流 Agent 整理相关记录，再由安全团队审阅分析。自动化适合帮助检索和关联证据，但分析结论仍需要与真实执行记录对照，不能把模型生成的解释当作事件本身。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 1 · 安全调查：终端告警与 Agent 记录提供不同证据，关联后再作判断</figcaption>
<div tabindex="0" role="region" aria-label="终端告警和 Agent 执行记录关联后进入安全分流与人工审阅" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="production-security-triage-title production-security-triage-desc" viewBox="0 0 640 474" style="display:block; width:100%; min-width:540px; height:auto; font-family:var(--font-sans); --node:light-dark(#e8f3fc,#142b3e); --condition:light-dark(#f4f9fe,#102333); --ink:light-dark(#235e89,#c0def4); --border:light-dark(#d0e0ed,#355167); --line:light-dark(#8e959d,#8295a6); --success:light-dark(#e5f6eb,#152f26); --success-ink:light-dark(#286447,#a9debf); --success-border:light-dark(#afd3bc,#426c57); --warn:light-dark(#fff3d7,#352918); --warn-ink:light-dark(#8b5b22,#f3ce8d); --warn-border:light-dark(#e8c98e,#80663a);">
<title id="production-security-triage-title">关联 Agent 任务记录与终端安全告警</title>
<desc id="production-security-triage-desc">终端告警提供进程、文件或网络的异常事件。Agent 记录提供用户请求、工具请求、审批和执行结果。将两类证据按任务与时间关联，辅助分流 Agent 整理分析，再由安全团队审阅，决定是否升级响应或调整策略。</desc>
<defs><marker id="production-security-triage-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<g fill="none" stroke="var(--line)" stroke-width="1.2" marker-end="url(#production-security-triage-arrow)"><path d="M164 106 V130 Q164 140 174 140 H310 Q320 140 320 150 V172"/><path d="M476 106 V130 Q476 140 466 140 H330 Q320 140 320 150 V172"/><path d="M320 240 V284"/><path d="M320 352 V396"/></g>
<rect x="36" y="24" width="256" height="82" rx="20" fill="var(--warn)" stroke="var(--warn-border)"/>
<text x="164" y="57" text-anchor="middle" fill="var(--warn-ink)" font-size="18" font-weight="500">终端安全告警</text><text x="164" y="83" text-anchor="middle" fill="var(--warn-ink)" font-size="14">进程、文件、网络事件</text>
<rect x="348" y="24" width="256" height="82" rx="20" fill="var(--node)" stroke="var(--border)"/>
<text x="476" y="57" text-anchor="middle" fill="var(--ink)" font-size="18" font-weight="500">Agent 执行记录</text><text x="476" y="83" text-anchor="middle" fill="var(--ink)" font-size="14">请求、工具、审批、结果</text>
<rect x="170" y="172" width="300" height="68" rx="20" fill="var(--condition)" stroke="var(--border)" stroke-dasharray="4 4"/>
<text x="320" y="200" text-anchor="middle" fill="var(--ink)" font-size="18" font-weight="500">关联与核对证据</text><text x="320" y="224" text-anchor="middle" fill="var(--ink)" font-size="14">对齐任务、时间与执行对象</text>
<rect x="170" y="284" width="300" height="68" rx="20" fill="var(--node)" stroke="var(--border)"/>
<text x="320" y="312" text-anchor="middle" fill="var(--ink)" font-size="18" font-weight="500">辅助分流 Agent</text><text x="320" y="336" text-anchor="middle" fill="var(--ink)" font-size="14">整理经过与待核实问题</text>
<rect x="170" y="396" width="300" height="62" rx="20" fill="var(--success)" stroke="var(--success-border)"/>
<text x="320" y="422" text-anchor="middle" fill="var(--success-ink)" font-size="18" font-weight="500">安全团队审阅</text><text x="320" y="446" text-anchor="middle" fill="var(--success-ink)" font-size="14">事件响应与策略反馈</text>
</svg>
</div>
</figure>

假如日志显示上传被网络策略阻断，这说明该次尝试没有沿这条路径完成，不说明尝试本身符合授权，也不能证明其他路径没有传输。调查要同时回答“动作是否合适”和“实际造成了什么影响”。

### 9. Rollout Feedback：从执行记录调整治理策略

同一批记录也可以服务于日常改进。某个目的地频繁触发审批，可能是正常开发依赖没有配置完整；也可能是工具请求超出了任务需要。两者都表现为“审批很多”，但处理方式不同。

前者适合核实用途后补充明确、有限的规则；后者需要收紧工具行为、修正任务指导，或继续保留阻断。不能为了降低打断次数，一律扩大允许范围。

同样，拦截次数少也不能单独证明策略有效：可能任务本来没有碰到边界，也可能相关通道没有被覆盖。更有价值的验证，是把正常任务、明确禁止的动作和需要审批的例外一起检查，确认三者确实进入预期处理路径。

从这个角度看，治理形成的是一条反馈链：**配置规定边界，执行落实边界，记录解释执行，再根据证据调整配置。** 日志不是安全控制的替代品，却能帮助发现控制没有覆盖到的位置，以及真正妨碍正常工作的地方。

## 几个关键问题，串起权限、审计与响应

**给每个人发同一份配置文件，就算统一治理了吗？**

不一定。先看它是可覆盖的默认值，还是强制要求，再看实际客户端与执行环境是否读取并落实。统一文件内容解决分发问题；禁止行为确实被拒绝，才说明相应约束生效。

**动作获得批准，为什么还可能不能执行？**

审批只能在允许的机制中处理具体请求，不能自动覆盖组织禁令、操作系统权限或目标服务授权。如果目标本来不可访问，或者组织禁止申请该权限，用户点一次批准也不构成无限权限。

**常用命令为什么不能直接按程序名放行？**

同一个程序可以读取、修改或删除资源。规则需要覆盖实际参数与作用范围，并处理复合命令；放行 PR 查询，不等于放行合并或仓库删除。规则的质量取决于覆盖了什么，而不是前缀有多短。

**已经限制网络，为什么还要检查 MCP 和其他连接器？**

限制的是具体执行通道，不是抽象的“Agent 整体”。命令代理、托管搜索和外部连接器可能分别受控。数据通过哪个通道出去，就要核对那个通道的策略；普通命令与获准升级后的命令也可能不同。

**凭证保存在 Keyring，是否就解决了身份安全？**

它解决凭证保管的一部分问题，不决定远程账号能访问哪些资源。组织归属、本机进程身份、外部服务授权仍需分别确认。安全存储一个权限过大的凭证，不会让它自动变成最小权限凭证。

**Agent 日志能证明它当时为什么这样想吗？**

日志可以提供请求、动作、审批和结果，用来分析行为与任务的关系，但不是模型内部意图的完整证明。还要考虑记录缺失、脱敏和结果截断，并与终端、网络或服务端记录核对。模型生成的事后解释不能替代证据。

**一次上传被阻断，调查是不是就结束了？**

没有沿已阻断路径完成上传，只回答了这条路径的结果。还要查动作为何出现、是否有其他路径、是否需要响应，以及策略是否确实覆盖同类请求。判断影响与判断授权，是调查中的两个不同问题。

## 参考资料

- [OpenAI — Running Codex safely at OpenAI](https://openai.com/index/running-codex-safely/)
- [OpenAI Docs — Managed configuration](https://learn.chatgpt.com/docs/enterprise/managed-configuration)
- [OpenAI Docs — Rules](https://learn.chatgpt.com/docs/agent-configuration/rules)
- [OpenAI Docs — Agent approvals & security](https://learn.chatgpt.com/docs/agent-approvals-security)
- [OpenAI Docs — Authentication](https://learn.chatgpt.com/docs/auth)
- [OpenAI Docs — Observability and telemetry](https://learn.chatgpt.com/docs/config-file/config-advanced#observability-and-telemetry)
- [上一篇：Agent Sandbox：操作系统怎样强制执行权限边界？](/zh-cn/posts/agent-sandbox/)
