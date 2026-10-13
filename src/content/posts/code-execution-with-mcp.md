---
title: 'Code Execution with MCP：工具调用与中间数据怎样绕开模型中转？'
description: '从 Google Drive 到 Salesforce 的数据流理解 MCP 代码执行：工具定义按需发现，中间数据在运行时传递与处理，再把必要结果交给模型，同时权衡执行、安全和状态管理成本。'
pubDate: 2026-10-12T23:30:00+08:00
category: notes
tags: [Agent, Anthropic, MCP, Context Engineering, 学习笔记]
draft: false
postType: metaOnly
---

[上一篇](/zh-cn/posts/effective-context-engineering/)讨论了每轮推理需要什么信息。这一篇把问题落到工具调用上：**一份资料需要从系统 A 送到系统 B，是否一定要先让模型读完整份内容，再由模型把它写进下一次调用？**

Anthropic 的 [《Code execution with MCP》](https://www.anthropic.com/engineering/code-execution-with-mcp)给出的方向，是让模型编写调用程序，由执行环境组合 MCP 工具。工具仍然被真实调用，但部分数据传递和处理不再经过模型上下文。

- **先看连接：** MCP 统一了什么，应用又负责什么。
- **再看数据流：** 直接调用与代码执行，分别让哪些内容进入模型。
- **最后看边界：** 怎样发现工具、处理结果，以及少用 token 后仍要承担的执行成本。

下面沿用原文 Google Drive → Salesforce 的任务背景，重新设计一个小例子：把指定会议文档的原文，保存到已经确认的 Salesforce Lead 备注中。这里讨论的是调用结构，不会连接真实账户；接口、记录 ID 和代码都是教学示例。

## 一、MCP 工具怎样接入 Agent

先明确连接角色，再看工具以什么方式交给模型，才能区分协议职责与数据流设计。

### 1. MCP：连接 Host、Client 与 Server

先把三个角色分开。Agent 所在的应用是 Host，它组织模型交互并管理连接；MCP Client 与对应 Server 通信；Server 暴露工具等能力，再连接文档系统、CRM 或其他资源。一个 Host 可以管理多个 Client，各自连接不同的 Server。 [MCP 架构规范](https://modelcontextprotocol.io/specification/2025-11-25/architecture)

在会议文档任务里，Google Drive Server 提供读取能力，Salesforce Server 提供修改记录的能力。模型不用直接掌握两套服务的底层通信细节，应用可以通过 MCP 发现并调用这些能力。

但“通过统一协议接上了工具”和“怎样把工具呈现给模型”，是两件事。应用既可以向模型提供逐个工具的定义，也可以在执行环境中提供可调用的代码接口。**MCP 是连接与能力交换的一层，不是代码执行引擎，也不是模型上下文的强制路由规则。**

具体到工具，协议中的 `tools/list` 用于取得定义，`tools/call` 用于发起调用。应用如何选择定义、怎样包装结果、哪些内容交给模型，仍然需要设计。不能把“连接了 MCP Server”直接理解为“必须把它的全部定义和结果都塞进模型”。 [MCP Tools 规范](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)

这一点也解释了为什么代码执行没有让 MCP 失去价值：程序接管了部分调用组织，底下仍然需要统一的能力入口、参数约定和连接管理。

### 2. Direct Tool Calling：模型参与逐步调用与参数传递

这里的 Direct Tool Calling，指应用把业务工具暴露给模型，模型生成参数，应用执行工具，再把结果送回模型的常见交互方式。所谓“直接”，不是模型绕过程序亲自访问 Google Drive。

对于这个例子，如果读取工具返回全文，而写入工具要求内联提供备注文本，过程可以展开成：

```text
模型请求读取指定文档
    ↓ 应用执行读取工具
文档全文作为 Tool Result 进入模型
    ↓ 模型生成下一次工具参数
同一份全文被写进更新 Lead 的请求
    ↓ 应用执行写入工具
写入确认返回模型
```

用户要求的是复制原文，不是分析原文。但在这条路径中，模型不仅要决定“读取后写入”，还要重新生成已经取得的长文本。假设全文包含会议中的客户编号、报价与换行格式，重新生成时遗漏一行或改变一个数字，都可能让搬运结果偏离原始资料。

这里有两笔不同的上下文开销：

| 开销 | 进入模型的是什么 | 会议任务中的问题 |
| --- | --- | --- |
| 能力描述 | 工具名称、说明、参数结构等定义 | 只读文档和写备注，却可能加载整个业务工具库 |
| 中间数据 | 已取得的资料，以及下一次调用中生成的参数 | 同一篇全文先被读取，再被重新写进参数 |

这不是说每种直接调用都必然重复全文。如果系统支持文件引用、句柄或服务端复制接口，应用也能避免内联搬运。需要诊断的是实际数据路径，而不是看到 Direct Tool Calling 就断言它低效。

同样，定义和数据也不能混为一谈：只做工具搜索，可以减少无关定义；但如果后续仍把全文交给模型，再让它原样输出，数据中转的开销依然存在。

## 二、代码执行怎样改变工具调用与数据流

连接到相同的外部服务，也可以采用不同的调用组织方式。下面分别看代码接口、工具发现和执行状态。

### 3. Code Execution：用程序组合 MCP 工具

**代码适配接口与调用链**

代码执行模式增加了一层适配：把可用 MCP 工具包装成程序能够调用的函数。模型读懂接口后编写代码，Runtime 执行代码；函数再通过应用管理的 MCP Client，调用对应 Server。

Cloudflare 的 [Code Mode](https://blog.cloudflare.com/code-mode/)也采用了类似分层：工具被转换成代码接口，执行环境通过受控调用与外部系统通信。代码接口不必意味着脚本持有服务凭证，或者可以任意访问网络；实际能力由应用授予。

对这个例子，可以用下面的简化类型表达运行时提供的两个适配器：

```ts
type Bindings = {
  drive: {
    readDocument(input: { id: string }): Promise<{ text: string }>;
  };
  crm: {
    replaceLeadNotes(input: {
      leadId: string;
      notes: string;
    }): Promise<{ updated: boolean }>;
  };
};

async function copyMeetingNotes(bindings: Bindings) {
  const document = await bindings.drive.readDocument({
    id: "meeting-demo-08",
  });

  const result = await bindings.crm.replaceLeadNotes({
    leadId: "lead-demo-08",
    notes: document.text,
  });

  if (!result.updated) {
    throw new Error("Lead notes update was not confirmed");
  }

  return { leadId: "lead-demo-08", updated: true };
}
```

这里的 `Bindings` 不是 Google Drive 或 Salesforce SDK 的真实签名，而是为解释数据流定义的适配接口。假设用户已确认目标记录并授权替换备注；“替换”不是追加，也不能在真实系统里默默覆盖已有内容。

适配器还要负责把实际 MCP 返回值解析成约定结构，检查协议错误、工具执行错误及字段有效性。TypeScript 的类型标注不会自动验证远端响应，`updated: true` 也必须有真实服务结果作依据，而不能由包装层无条件填入。

**运行时中的数据传递**

这行赋值发生在执行环境里。文档内容从读取结果进入变量，再作为参数传给 CRM，模型不必重新生成其中的每个字符。最后返回的只是足以说明执行状态的对象。

<figure class="not-prose" style="margin:1.75em 0;">
  <figcaption style="font-size:.8125rem;color:var(--muted-foreground);margin-bottom:1rem;text-align:center;">图 1 · 同一份文档，区别在于中间内容由谁传递</figcaption>
  <div role="region" aria-label="MCP 两种调用模式对比图，可横向滚动" tabindex="0" style="overflow-x:auto;max-width:100%;border-radius:16px;padding:8px 0;background:hsl(0 0% 50% / .025);">
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 475" role="img" aria-labelledby="mcp-data-title mcp-data-desc" style="display:block;width:100%;min-width:620px;height:auto;font-family:var(--font-sans);--node:light-dark(#e8f3fc,#142b3e);--ink:light-dark(#235e89,#c0def4);--border:light-dark(#d0e0ed,#355167);--line:light-dark(#8e959d,#8295a6);--success:light-dark(#e5f6eb,#152f26);--success-ink:light-dark(#286447,#a9debf);--success-border:light-dark(#afd3bc,#426c57);">
      <title id="mcp-data-title">直接调用与 MCP 代码执行的数据流对比</title>
      <desc id="mcp-data-desc">直接调用路径中，读取的全文进入模型，再生成写入参数。代码执行路径中，模型先生成程序，Runtime 通过 MCP 读取和写入全文，只将必要执行结果交回模型。图中省略具体 Client 和 Server。</desc>
      <defs><marker id="mcp-data-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M1 1L8 5L1 9" fill="none" stroke="var(--line)" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
      <g fill="var(--ink)" font-size="17" font-weight="600"><text x="30" y="31">直接调用 · 全文经过模型中转</text><text x="30" y="216">代码执行 · 全文在 Runtime 中传递</text></g>
      <g fill="none" stroke="var(--line)" stroke-width="1.5" marker-end="url(#mcp-data-arrow)"><path d="M190 99H277"/><path d="M443 99H530"/><path d="M190 282H277"/><path d="M443 282H530"/><path d="M610 324V387H443"/></g>
      <g fill="var(--line)" font-size="13" text-anchor="middle"><text x="233" y="82">读取全文</text><text x="487" y="82">生成全文参数</text><text x="233" y="265">读取结果</text><text x="487" y="265">变量传递</text><text x="513" y="374">经 Runtime 汇总状态</text></g>
      <g fill="var(--node)" stroke="var(--border)" stroke-width="1.5"><rect x="30" y="57" width="160" height="84" rx="18"/><rect x="277" y="57" width="166" height="84" rx="18"/><rect x="530" y="57" width="160" height="84" rx="18"/><rect x="30" y="240" width="160" height="84" rx="18"/><rect x="530" y="240" width="160" height="84" rx="18"/><rect x="277" y="345" width="166" height="84" rx="18"/></g>
      <rect x="277" y="240" width="166" height="84" rx="18" fill="var(--success)" stroke="var(--success-border)" stroke-width="1.5"/>
      <g fill="var(--ink)" text-anchor="middle"><g font-size="17" font-weight="600"><text x="110" y="92">Google Drive</text><text x="360" y="92">Model</text><text x="610" y="92">Salesforce</text><text x="110" y="275">Google Drive</text><text x="610" y="275">Salesforce</text><text x="360" y="380">Model</text></g><g font-size="13"><text x="110" y="117">指定会议文档</text><text x="360" y="117">读全文，再输出全文</text><text x="610" y="117">接收备注内容</text><text x="110" y="300">指定会议文档</text><text x="610" y="300">接收备注内容</text><text x="360" y="405">取得必要执行结果</text></g></g>
      <g fill="var(--success-ink)" text-anchor="middle"><text x="360" y="275" font-size="17" font-weight="600">Code Runtime</text><text x="360" y="300" font-size="13">执行模型生成的程序</text></g>
      <text x="30" y="461" fill="var(--line)" font-size="12">工具调用均经 MCP；仅展示资料路径，模型请求与具体连接层已省略。</text>
    </svg>
  </div>
</figure>

**减少的是模型输入、输出和往返，不是业务调用本身。** 读取一次、写入一次，仍然是两个真实操作；网络耗时、服务限流与失败处理都不会消失。

这里的“绕开模型”也有条件：运行时不能同时把每次底层响应全文自动回显给模型，脚本也不能顺手 `console.log(document)`。否则虽然用了代码，中间数据还是回到了上下文。

更重要的是任务语义。如果要求变成“判断会议里哪些承诺需要跟进”，模型就需要看到相关内容，或获得保留足够证据的摘录。复制资料与理解资料不是同一种任务，不能为了减少 token 把判断必需的信息一起藏掉。

### 4. Tool Discovery 与数据处理：按需读定义，在运行时处理结果

**工具目录、接口说明与按需加载**

一种代码接口组织方式，是按服务保存工具文件：

```text
tool-api/
├── drive/
│   ├── readDocument.ts
│   └── searchDocuments.ts
└── crm/
    ├── findLead.ts
    └── replaceLeadNotes.ts
```

模型先看目录，确定涉及文档与 CRM，再读取需要的函数说明。工具多时，也可以增加搜索入口，先返回候选名称或简短说明，再取得完整参数定义。这是把第七篇的渐进加载应用到工具目录。

但把定义写成文件，不等于完成了按需加载。如果应用随后把整个目录下的所有文件拼进提示词，开销只是换了表示形式。反过来，**运行时导入模块不等于模型读懂接口**：模型在写调用代码前，仍需取得足以理解参数、返回值和副作用的信息。

因此需要分别确认两个时刻：接口何时对模型可见，代码何时在运行时可调用。发现成功也不等于有执行权限，目录中出现一个函数并不能代替调用检查。

**中间数据筛选与结果返回**

当任务变成“找出这批会议记录里尚未同步到 CRM 的条目”，处理对象就可能是大量结构化记录。若“尚未同步”已有可靠字段，不必让模型逐行筛选，可以在代码中处理：

```ts
type MeetingRow = { documentId: string; synced: boolean };

function summarizePending(rows: MeetingRow[]) {
  const pending = rows.filter(row => !row.synced);
  return {
    total: rows.length,
    pendingCount: pending.length,
    sampleDocumentIds: pending.slice(0, 3).map(row => row.documentId),
  };
}
```

这里返回的是总数、待同步数量与少量样本，不是整批记录。样本只是帮助检查结果形态，不能代表完整清单；如果任务要求逐条跟进，就应保存完整清单并提供可读取的入口。

同理，结构化字段的筛选、连接与统计适合程序处理；“客户是否已经明确接受报价”如果只存在自然语言讨论中，就不能随意用一个关键词匹配替代语义判断。

我更关注的是过滤规则的责任：**模型决定了错误的规则，代码只会更稳定地执行这个错误。** 所以需要核对字段含义、数据范围和异常记录，不能把“程序算出来的”当作业务结论天然正确。

### 5. Control Flow 与 State：组织循环、错误处理和恢复

代码还可以组织翻页、循环、条件和错误处理。如果下一页游标已经给出，就可以按约定继续取页；不需要让模型在每页之后重新决定一次“现在取下一页”。

但模型往返减少，并不保证每个任务都更快。串行服务请求仍然是串行等待；执行环境启动、代码生成和修复也需要时间。只有被省下的模型往返与数据处理成本，大于新增开销，整体才可能获益。

对于写入操作，控制流尤其不能只追求紧凑。假设更新 Lead 的请求超时，服务端可能已经完成写入，也可能尚未处理。程序不能仅凭超时就无条件重跑整段任务，特别是后续接口改成“追加备注”时，重试可能产生重复内容。

一个更清楚的结果约定，是区分已确认成功、明确失败和状态未知，再由应用核对或请求进一步判断。循环有边界、请求有超时、失败可追踪，才能避免“一次执行”变成无法解释的长任务。

外部文件则承接另一个问题：运行过程中的结果放在哪里。批量同步可以保存待处理记录与完成清单，供后续操作读取，不必每轮把它们全文放回模型。这与第七篇的外部状态是一致的。

不过，文件持久性取决于存储是否保留；保存了进度也不等于业务操作与进度写入具有原子性。如果 CRM 写入成功，但保存完成清单失败，恢复时仍需核对真实状态。外部文件是恢复依据之一，不是“恰好执行一次”的自动保证。

保存经过验证的处理函数，也能减少重复编写。**代码复用和任务知识组织有关，但不是同一层设计**：一个函数提供可执行逻辑，何时使用它、需要什么前提，仍需额外说明，不能只靠文件存在。

## 三、代码执行的收益与代价怎样判断

把中间数据留在代码环境中，可以减少模型接触资料的范围，但不是“用了代码就自动保密”。日志、异常堆栈、调试输出和文件回读，都是数据重新进入模型的入口。

在会议文档例子里，即使模型不见原文，原文仍被送往 Salesforce。**不进入模型，不等于没有对外传输，也不等于目标系统获得数据的行为已经被授权。** 必须同时检查目标记录、写入字段和允许的数据流向。

若使用占位符替代敏感字段，还需要应用维护映射，并在允许的调用边界还原；不能假定 MCP 自带透明脱敏。隐藏值也不会消除风险：模型如果可以把整份资料送到任意目的地，仍然可能触发不合适的数据流。

执行模型生成的程序，还增加了直接业务工具调用未必需要承担的运行时管理工作：代码能够使用哪些能力，最长运行多久，最多占用多少资源，输出是否被检查，失败后怎样清理和诊断。服务本身的权限与输入检查也仍然要保留。

所以我会用任务特征判断是否值得引入代码执行，而不是把它当作默认升级：

| 任务特征 | 更值得关注的设计 |
| --- | --- |
| 工具少、结果小，每一步都需要语义判断 | 直接调用通常更清楚，未必值得增加运行时 |
| 大量无关定义占据输入，但调用链很短 | 优先考虑工具发现与选择性加载 |
| 大块数据需要搬运，或有固定的多步处理 | 代码执行更可能减少模型中转 |
| 每次取得结果都会改变业务判断 | 保留必要的模型反馈点，不强行塞进一段程序 |
| 涉及敏感写入或状态不明的重试 | 先明确授权、结果检查与恢复边界 |

[第六篇](/zh-cn/posts/advanced-tool-use/)讲的是工具发现与程序化调用等机制；这一篇进一步追踪它们落在 MCP 系统中的位置。读完后，我更倾向于沿数据路径检查系统：哪些信息帮助模型判断，哪些只是被模型搬运，哪些应该留在外部执行与存储层。

**模型需要对下一步有足够理解，但不必成为所有数据的必经通道。** 代码执行的价值，在于把明确的数据操作交回程序，同时保留需要判断的反馈点；它优化的是分工，而不只是上下文长度。

## 几个关键问题，串起连接、数据流与执行边界

**已经用代码调用接口，为什么还需要 MCP？**

代码负责组织执行，MCP 提供统一的能力发现与调用连接。否则程序可能需要分别适配每个系统的接口与通信方式。两者可以配合，也不是所有代码执行都必须依赖 MCP。

**代码执行为什么能减少中间数据进入 Context？**

因为读取结果可以留在运行时变量里，再直接传给下一工具，模型只接收必要输出。收益来自数据路由的变化，不是函数改了名字；如果全文仍被自动回显或打印，开销仍会回来。

**工具定义按需加载，能否同时解决大结果问题？**

不能。前者减少模型了解能力的成本，后者涉及执行结果流向。一个工具的定义很短，也可能返回巨量数据；需要分别检查定义加载和结果处理。

**不把原始资料给模型，会不会影响判断？**

会，取决于任务是否需要理解原始内容。机械复制通常不需要模型重写全文；语义分析则需要相关证据。不能用不透明摘要替代必要资料，更不能把被过滤掉的信息当作模型已经检查过。

**代码环境里的数据是否天然更安全、更持久？**

不是。安全取决于能力、输出和流向限制，持久性取决于实际存储生命周期。代码环境可以帮助隔离中间数据，但日志泄露、错误目标、临时磁盘丢失等问题仍需处理。

**一段程序完成多个工具调用，是否只剩一次调用成本？**

只可能减少模型交互，不会把多次业务调用变成一次。各服务的网络、限流和错误仍然存在；程序还增加执行与诊断成本。衡量收益应看端到端任务是否可靠完成，而不只看模型请求次数。

## 参考资料

- [Anthropic · Code execution with MCP: Building more efficient agents](https://www.anthropic.com/engineering/code-execution-with-mcp)
- [MCP · Architecture（2025-11-25）](https://modelcontextprotocol.io/specification/2025-11-25/architecture)
- [MCP · Tools（2025-11-25）](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
- [Cloudflare · Code Mode: the better way to use MCP](https://blog.cloudflare.com/code-mode/)
