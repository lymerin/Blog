---
title: 'Agent Sandbox：操作系统怎样强制执行权限边界？'
description: '以 Codex 的 Windows Sandbox 设计为例，理解 SID、ACL 与 Restricted Token 怎样限制写入，专用身份和 Firewall 怎样约束联网，以及初始化、Runner 和进程树之间的关系。'
pubDate: 2026-10-14T18:32:41+08:00
category: notes
tags: [Agent, OpenAI, Security, Windows, 学习笔记]
draft: false
postType: metaOnly
---

[上一篇](/zh-cn/posts/agent-guardrails/)讨论了怎样判断一个动作应不应该执行。这一篇把问题交给操作系统：**即使 Agent 已经提出了越界动作，怎样让执行环境直接拒绝它？**

对于 Coding Agent，限制不能只停在工具名称或提示词里。它会启动 Shell，Shell 再运行 Git、Python、测试程序和子进程。真正的边界需要覆盖这些程序访问文件和网络的过程。

本文以 OpenAI 于 2026 年 5 月发布的[《Building a safe, effective sandbox to enable Codex on Windows》](https://openai.com/index/building-codex-windows-sandbox/)为案例，按进程、文件权限、网络身份和启动架构展开。当前[官方文档](https://learn.chatgpt.com/docs/windows/windows-sandbox)已列出 MXC 等实现，下面研究的是原文中的 Restricted Token、专用用户与 Firewall 组合，不把它当作当前唯一方案。

仍用一个假设任务贯穿说明：Agent 修复项目中的 CSV 解析问题，并运行本地测试。它需要读项目、修改源码和启动开发工具，但不应随意修改项目外文件，或向外部发送资料。以下权限例子用于解释机制，不会修改当前电脑的 ACL、账号或防火墙。

## 一、Sandbox 约束的是哪些执行对象

Sandbox 是受约束的执行环境，不是让模型“更谨慎”的另一份提示词。要建立这种环境，先要找到动作真正落地的位置。

### 1. Process Tree：从工具入口覆盖到子进程

模型提出一个执行请求，Harness 在本机启动程序，程序再访问文件、创建进程或连接服务。操作系统看到的是进程和访问请求，不是“这次推理的意图”。

因此，限制的对象不应只有 Agent 的主程序。假设它启动 Shell，Shell 再启动 Python，Python 又运行测试子进程，如果只有最上面的程序受限，真正处理数据的程序仍然可能拥有过大的权限。

**进程树是执行边界的覆盖范围，而不是后台实现细节。** 一次命令改用不同的解释器，不能因此获得原先没有的写入或联网能力。

这里也要区分 Agent 主程序与它执行的命令。主程序负责会话、模型交互和调度；受限工具进程负责实际工作。两者不一定使用同一个身份或拥有相同权限。

### 2. 隔离方案：原生进程、AppContainer 与 VM 的取舍

Windows 有多种安全原语，但“存在隔离机制”不等于“直接适合任意开发工作流”。原文比较过 AppContainer、Windows Sandbox VM 和 MIC 完整性级别，最终选择组合其他机制。[来源：OpenAI 设计案例](https://openai.com/index/building-codex-windows-sandbox/)

AppContainer 更适合预先明确能力的应用；Coding Agent 却需要驱动多种现成工具。VM 能提供较强环境隔离，但要处理工具准备、真实工作区访问和宿主机衔接。MIC 可以限制低完整性进程写入更高完整性的对象，但改变工作区标签，也会改变其他低完整性进程访问它的条件。

这些不是对某种机制“不安全”的简单评价，而是不同安全模型与产品需要之间的匹配问题。只给某个 Sandbox 身份增加定向权限，与改变整个目录的通用信任级别，影响范围并不相同。

对 CSV 修复任务来说，设计目标是让已有工具正常运行，同时限制它们的真实访问。关键不在于隔离功能的名称，而在于：**能够准确约束哪些动作，又需要改变宿主环境的哪些条件。**

## 二、Windows 怎样判断文件写入权限

文件限制需要把“进程以谁的身份运行”和“对象允许谁访问”连接起来。Windows 中的 SID、Token 与 ACL 分别承担不同角色。

### 3. SID 与 ACL：身份标识和对象权限

SID（Security Identifier）是 Windows 安全主体的标识。用户、组等可以有 SID；它不是模型生成的访问理由，也不是路径字符串。

ACL 是访问控制项的集合。其中 DACL 决定哪些主体被允许或拒绝访问对象，条目会描述对应主体及读、写等权利。进程访问文件时，系统依据 Token 中的身份信息与对象权限进行检查。具体语义见 [Microsoft 的 ACL 文档](https://learn.microsoft.com/en-us/windows/win32/secauthz/access-control-lists)。

可以把三者的关系理解为：

- **SID：** 权限规则在识别谁。
- **Token：** 当前进程携带什么身份与权限信息。
- **DACL：** 目标对象允许或拒绝哪些访问。

合成 SID 则提供了一种定向标记：它可以出现在访问控制规则中，而不必对应一个真实登录用户。这样能表达 Sandbox 特有的权限，不必把整个工作区变成“任何低权限程序都能写”的目录。

但“创建了 SID”本身没有隔离效果。只有把它接入对象权限和进程的访问检查，身份标记才成为可执行的约束。

### 4. Write-restricted Token：对写入增加一层检查

Restricted Token 可以减少权限，或加入 restricting SIDs。系统进行相应访问检查时，既检查通常的身份权限，也检查限制列表；两边都通过才允许访问。`WRITE_RESTRICTED` 则让 restricting SIDs 的额外检查用于写访问。见 [Microsoft 的 CreateRestrictedToken 文档](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-createrestrictedtoken)。

对写入请求，可以用下面的关系理解，而不是把额外 SID 当成新的管理员权限：

```text
允许写入
  = 通常的身份权限检查通过
    AND
    restricting SID 检查通过
```

假设一套教学权限只允许在项目源码目录写入，项目外目录没有通过第二项检查的授权：

| 写入目标 | 通常的身份检查 | 限制检查 | 结果 |
| --- | --- | --- | --- |
| 项目源码文件 | 通过 | 通过 | 可以写入 |
| 用户可写的另一个目录 | 通过 | 不通过 | 拒绝写入 |
| 普通身份无权修改的系统文件 | 不通过 | 无论如何 | 不能写入 |

这解释了为什么“开发者能改这个文件”不等于“受限工具进程也能改”。额外检查是在缩小能力，而不是绕过原来的权限。

实际结果仍取决于完整的 SID 列表和对象 ACL。如果某个广泛主体已有过宽的授权，不能只看合成 SID 的配置就断言边界正确。当前[官方文档](https://learn.chatgpt.com/docs/windows/windows-sandbox)也提示，`Everyone` 可写目录可能影响保护效果。

另一个区别同样重要：**限制写入不等于限制读取。** 在 `WRITE_RESTRICTED` 下，不能仅凭这项额外检查就推导“项目外文件全部不可读”。机密性需要另外核对读取权限和数据出口。

## 三、网络限制为什么需要独立身份

文件系统能阻止越界写入，并不意味着资料无法发送出去。网络访问需要自己的强制机制，也需要准确识别受限进程。

### 5. Network Enforcement：环境约定与系统强制

让常用工具使用一个不可用代理，能够阻止部分联网；让命令搜索路径优先命中禁用脚本，也能影响某些工具行为。但这些办法依赖程序遵守约定。

一个程序可能不读取代理变量，直接使用网络接口。它不必怀有攻击意图，也可能因为自己的实现方式没有采用这些设置。**工具恰好无法联网，与系统不允许它联网，是两种保证。**

这也是为什么网络限制不能只靠 Shell 包装。与提示词相比，环境变量更靠近执行，但仍不是所有程序都必须经过的检查点。

同样，仅针对 Agent 主程序设置规则，不能覆盖它启动的其他工具；把某个常用解释器整体禁网，又可能影响用户平常的开发。需要的是识别这次受限工作，而不是粗略禁止整个机器上的某个程序名称。

### 6. Principal 与 Firewall：区分受限工作和用户日常操作

Principal 可以理解为系统识别并施加权限的安全主体。合成 SID 可以帮助文件访问检查，但不等于它在所有策略系统里都能直接作为独立用户使用。

原文从当前用户的受限 Token，演进到专用的 Online / Offline 用户，并把网络规则施加到 Offline 身份。目的就是让规则覆盖这类受限命令，而不影响开发者所有同名程序。[来源：原文的网络与身份设计](https://openai.com/index/building-codex-windows-sandbox/)

例如，同一台机器上的两个 Python 进程，一个属于开发者的正常工作，另一个属于离线 Sandbox。按身份区分之后，才能针对后者限制出站访问，而不是把所有 Python 一起禁网。

Online 与 Offline 也不是“完全放权”和“完全隔离”的同义词。是否联网是一项策略，文件写入是否受限又是另一项策略；改变网络条件，不应被理解为自动取消所有文件约束。

专用用户在这里首先是本机执行身份，不是模型账号，也不自动代表对云服务的授权。远程服务仍会依据各自的凭证和权限判断操作。

## 四、初始化与命令执行怎样连接起来

当文件规则、网络规则和专用身份分属不同机制，就需要一个明确启动过程，把它们应用到真实命令，而不是只保存为配置。

### 7. Setup 与 Runner：初始化权限和受限执行

初始化阶段负责准备账号和系统策略，运行阶段负责在这些条件下启动命令。二者的权限需求不同。

原文将需要管理员权限的准备工作放入独立 Setup 程序，再由普通用户 Harness 启动专用用户身份下的 Runner，Runner 创建受限 Token 后启动工具。这个拆分解决了跨用户启动与受限 Token 创建之间的衔接。[来源：原文的启动架构](https://openai.com/index/building-codex-windows-sandbox/)

为什么不能由 Harness 一步完成？直接使用另一个用户的 Token 启动受限进程，会遇到 Windows 的权限要求。先让 Runner 以目标用户身份运行，再使用自身 Token 的受限版本创建工具进程，就把最后一步放到了目标身份一侧。微软的 [Restricted Tokens 文档](https://learn.microsoft.com/en-us/windows/win32/secauthz/restricted-tokens)也说明了使用自身受限 Token 创建进程时的权限条件。

理解这条链时，要分清两件事：**管理员初始化是在建立约束，不是在给每次 Agent 命令提供管理员权限。** Runner 也不是让模型获得一个高权限 Shell，而是把最终工具进程放进受限安全上下文。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 1 · 原文方案的运行链：初始化准备策略，Runner 在专用身份下启动受限工具与后代进程</figcaption>
<div tabindex="0" role="region" aria-label="Windows Sandbox 中 Harness、Runner 与受限进程树的关系" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="agent-sandbox-runtime-title agent-sandbox-runtime-desc" viewBox="0 0 640 474" style="display:block; width:100%; min-width:540px; height:auto; font-family:var(--font-sans); --node:light-dark(#e8f3fc,#142b3e); --condition:light-dark(#f4f9fe,#102333); --ink:light-dark(#235e89,#c0def4); --border:light-dark(#d0e0ed,#355167); --line:light-dark(#8e959d,#8295a6); --success:light-dark(#e5f6eb,#152f26); --success-ink:light-dark(#286447,#a9debf); --success-border:light-dark(#afd3bc,#426c57); --warn:light-dark(#fff3d7,#352918); --warn-ink:light-dark(#8b5b22,#f3ce8d); --warn-border:light-dark(#e8c98e,#80663a);">
<title id="agent-sandbox-runtime-title">Harness 通过 Runner 启动受限工具进程</title>
<desc id="agent-sandbox-runtime-desc">管理员初始化已准备身份、ACL 和网络策略。普通用户 Harness 启动专用 Sandbox 用户身份的 Runner；Runner 创建受限 Token 并启动 Shell。Shell 派生的 Python、测试或 Git 等工具仍需处在同一权限边界。图中描述的是原文架构，不是所有 Windows Sandbox 实现。</desc>
<defs><marker id="agent-sandbox-runtime-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<rect x="16" y="226" width="608" height="236" rx="22" fill="var(--condition)" stroke="var(--border)" stroke-dasharray="4 4"/>
<text x="42" y="253" fill="var(--ink)" font-size="13">受限执行域</text>
<g fill="none" stroke="var(--line)" stroke-width="1.2" marker-end="url(#agent-sandbox-runtime-arrow)"><path d="M320 84 V128"/><path d="M320 200 V266"/><path d="M320 338 V350 Q320 360 310 360 H174 Q164 360 164 370 V390"/><path d="M320 338 V350 Q320 360 330 360 H466 Q476 360 476 370 V390"/></g>
<rect x="170" y="20" width="300" height="64" rx="20" fill="var(--node)" stroke="var(--border)"/>
<text x="320" y="47" text-anchor="middle" fill="var(--ink)" font-size="18" font-weight="500">Harness</text><text x="320" y="71" text-anchor="middle" fill="var(--ink)" font-size="14">普通用户 · 组织执行请求</text>
<rect x="170" y="128" width="300" height="72" rx="20" fill="var(--node)" stroke="var(--border)"/>
<text x="320" y="158" text-anchor="middle" fill="var(--ink)" font-size="18" font-weight="500">Command Runner</text><text x="320" y="185" text-anchor="middle" fill="var(--ink)" font-size="14">专用 Sandbox 用户身份</text>
<text x="332" y="237" fill="var(--ink)" font-size="13">创建受限 Token 并启动</text>
<rect x="170" y="266" width="300" height="72" rx="20" fill="var(--success)" stroke="var(--success-border)"/>
<text x="320" y="296" text-anchor="middle" fill="var(--success-ink)" font-size="18" font-weight="500">Shell 工具进程</text><text x="320" y="322" text-anchor="middle" fill="var(--success-ink)" font-size="14">使用受限 Token</text>
<g fill="var(--success)" stroke="var(--success-border)"><rect x="40" y="390" width="248" height="56" rx="18"/><rect x="352" y="390" width="248" height="56" rx="18"/></g>
<text x="164" y="424" text-anchor="middle" fill="var(--success-ink)" font-size="17" font-weight="500">Python / 测试进程</text><text x="476" y="424" text-anchor="middle" fill="var(--success-ink)" font-size="17" font-weight="500">Git / 其他开发工具</text>
</svg>
</div>
</figure>

这条链的价值在于职责分离：Setup 建立系统条件，Harness 组织动作，Runner 负责受限启动，工具实际完成任务。初始化成功不等于每个命令都已受限，还要检查最终进程是否真的使用了正确 Token、身份与策略。

### 8. 兼容性与剩余风险：读取、宿主环境和边界覆盖

换成专用用户以后，原本能读取的开发工具、项目路径和用户配置，可能因为身份变化而不可访问。为了可用性补充读取权限，又需要确认没有无意扩大敏感资料的暴露范围。

这说明兼容性不是与安全无关的体验细节。边界过窄会让正常开发失败；边界过宽会让隔离失去意义。需要把缺失能力定位到具体资源，而不是遇到一次失败就取消整个 Sandbox。

ACL 方案还会改变真实宿主文件的权限状态。配置可写目录、处理继承或迁移项目时，需要考虑已有规则是否仍然正确。它不是一个与宿主机无关、销毁后自动清除一切影响的临时空间。

最后，进程约束也有覆盖范围。一个在边界外运行的高权限连接器，不会仅因为它由同一个 Agent 使用，就自动受 Shell Sandbox 保护；一个已经获得远程服务凭证的工具，也需要单独检查它能操作什么。

因此，评价 Hard Containment 应当具体到：限制哪些进程，检查哪些访问，使用什么身份，以及是否存在其他执行入口。**模型解释可以改变动作选择，但不应改变这些资源规则；规则本身的正确性和覆盖范围，则仍然需要工程验证。**

## 几个关键问题，串起身份、权限与执行边界

**为什么只给 Agent 主程序加限制还不够？**

实际文件和网络操作常由 Shell、解释器或测试子进程完成。边界需要覆盖受限工作产生的进程树，而不是只覆盖会话入口的程序名称。

**SID、Token 与 ACL 分别负责什么？**

SID 标识主体，Token 携带进程的安全上下文，ACL 描述对象允许或拒绝的访问。三者要在操作系统检查中配合，单独创建一个身份标记不会自动形成 Sandbox。

**Write-restricted Token 为什么能限制用户原本可写的目录？**

写入不仅要通过通常的身份检查，还要通过 restricting SID 检查。用户可写只说明第一项可能通过，不能替代第二项。实际授权仍要核对完整 Token 与 ACL。

**限制写入是否意味着项目外文件不可读？**

不是。`WRITE_RESTRICTED` 的额外检查针对写访问，读取范围需要另外确认。只保护数据不被修改，不能自动保护数据不被读取或发送。

**把代理指向不可用地址，为什么不是强网络隔离？**

因为程序可以不采用代理设置，直接进行网络访问。真正的强制策略需要在程序无法凭自身选择绕开的检查点执行，并准确覆盖受限进程。

**为什么引入专用用户，而不是只靠合成 SID？**

不同策略机制识别身份的方式不同。原文用合成 SID 参与文件检查，再用专用 Principal 将网络规则关联到受限工作，从而区别于开发者的普通进程。

**管理员初始化是否意味着 Agent 命令以管理员运行？**

不意味着。初始化用较高权限准备账号和策略，日常工具则以受限身份执行。两者分离，正是为了不把配置边界所需的权限交给任务命令。

**Sandbox 能保证项目修改正确吗？**

不能。它限制的是操作能力和影响范围。允许目录内仍可能出现错误修改，因此测试、Review 与恢复机制仍然有必要。

## 参考资料

- [OpenAI — Building a safe, effective sandbox to enable Codex on Windows](https://openai.com/index/building-codex-windows-sandbox/)
- [OpenAI 官方文档 — Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox)
- [Microsoft — Access Control Lists](https://learn.microsoft.com/en-us/windows/win32/secauthz/access-control-lists)
- [Microsoft — CreateRestrictedToken](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-createrestrictedtoken)
- [Microsoft — Restricted Tokens](https://learn.microsoft.com/en-us/windows/win32/secauthz/restricted-tokens)
