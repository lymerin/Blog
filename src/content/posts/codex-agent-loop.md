---
title: 'Agent Loop：模型判断、工具执行与结果回传怎样连成循环'
description: '从一段循环伪代码出发，拆解一次模型推理、Tool Call 与 Tool Execution 的区别、工具结果如何回到下一次输入，以及 Agent 何时停止。'
pubDate: 2026-10-12T08:20:00+08:00
category: notes
tags: [Agent, OpenAI, Codex, LLM, 学习笔记]
draft: false
postType: metaOnly
---

[上一篇](/zh-cn/posts/practical-guide-building-agents/)把 Model、Tools、Instructions 和编排方式放在了一起。这一篇继续往执行过程里看：模型提出“读取一个文件”以后，谁去读取？文件内容回来以后，又怎样影响下一步？

OpenAI 的 [《Unrolling the Codex agent loop》](https://openai.com/index/unrolling-the-codex-agent-loop/)沿着模型输入、工具调用和后续请求，展开了 Codex 的运行过程。我更关注其中这条连接：**模型产生行动请求，外部程序执行，再把实际结果交回模型。** Agent 的连续行动，正是在这几步之间形成的。

- **一次推理：** 当前信息怎样交给 Model，模型这一次输出了什么。
- **一次循环：** Tool Call 怎样变成执行，Tool Result 怎样进入下一次输入。
- **一次结束：** 什么时候继续调用模型，什么时候停止并交还控制权。

下面用一个假设的 Java 代码排查任务贯穿说明：“看看 `UserService.java` 为什么会返回空值。”

## 一、先看循环：一次任务可以包含多次模型调用

模型第一次收到请求时，可能还没有文件内容。它可以先提出读取文件的请求；文件读出后，才有条件判断是实现本身返回了空值，还是需要继续查看调用的方法。

这里并不是让同一次推理一直运行到任务完成，而是由模型外面的程序，把多次调用连接起来。先把这个过程压成一段 JavaScript 风格的伪代码：

```js
const input = [userMessage];

while (!shouldStop()) {
  const output = await infer({ instructions, tools, input });

  // 保留本次模型输出，包括工具调用记录。
  input.push(...output.items);

  if (output.toolCalls.length === 0) {
    return output.finalAnswer ?? "无法继续，需要补充信息";
  }

  for (const call of output.toolCalls) {
    const result = await runTool(call);
    input.push({
      type: "function_call_output",
      call_id: call.call_id,
      output: result,
    });
  }
}

return "达到停止条件，结束当前执行";
```

这里的 `infer()` 是为了说明控制流程而抽象出的接口，不是 SDK 的原始返回结构。它把完整输出保留在 `items` 中，再提取出待执行的 `toolCalls` 和当前轮次的最终答复；`runTool()` 返回可传回模型的结果，也可以是工具执行失败的信息。

读这段代码，可以抓住三个位置：

1. **`infer()`：** 用当前信息调用一次模型。
2. **`runTool()`：** 模型之外的程序真正执行动作。
3. **`input.push()`：** 保留行动请求与实际结果，供下一次调用使用。

循环的外层结构由程序实现，但下一次调用什么工具、使用什么参数，可以由模型根据新结果决定。**固定的是“判断—执行—反馈”的机制，不是每项任务具体要走的路线。**

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 1 · Agent Loop：外部结果进入下一次模型判断</figcaption>
<div tabindex="0" role="region" aria-label="Agent Loop 的模型判断与工具执行循环" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="agent-loop-title agent-loop-desc" viewBox="0 0 640 510" style="display:block; width:100%; min-width:540px; height:auto; font-family:var(--font-sans); --node:light-dark(#e8f3fc,#142b3e); --condition:light-dark(#f4f9fe,#102333); --ink:light-dark(#235e89,#c0def4); --border:light-dark(#d0e0ed,#355167); --line:light-dark(#8e959d,#8295a6); --success:light-dark(#e5f6eb,#152f26); --success-ink:light-dark(#286447,#a9debf); --success-border:light-dark(#afd3bc,#426c57);">
<title id="agent-loop-title">Agent Loop 的一次循环</title>
<desc id="agent-loop-desc">Harness 准备当前输入，调用模型推理。模型提出 Tool Call 后，Harness 执行工具，再把调用记录和 Tool Result 接回输入，重新调用模型。没有待执行工具且可结束时，向用户答复或请求补充。达到停止条件也会结束执行。</desc>
<defs><marker id="agent-loop-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<g fill="none" stroke="var(--line)" stroke-width="1.2" marker-end="url(#agent-loop-arrow)"><path d="M255 76 V116"/><path d="M255 190 V238"/><path d="M255 302 V350"/><path d="M255 416 V448"/><path d="M140 478 H78 Q66 478 66 466 V60 Q66 48 78 48 H140"/><path d="M370 150 H422 Q434 150 434 162 V230 Q434 242 446 242 H452"/></g>
<rect x="140" y="18" width="230" height="58" rx="20" fill="var(--node)" stroke="var(--border)"/>
<text x="255" y="43" text-anchor="middle" fill="var(--ink)" font-size="17" font-weight="500">Harness 准备当前输入</text><text x="255" y="64" text-anchor="middle" fill="var(--ink)" font-size="12">指令 · 工具定义 · 当前交互</text>
<rect x="140" y="118" width="230" height="72" rx="20" fill="var(--node)" stroke="var(--border)"/>
<text x="255" y="148" text-anchor="middle" fill="var(--ink)" font-size="18" font-weight="500">Model inference</text><text x="255" y="175" text-anchor="middle" fill="var(--ink)" font-size="13">依据当前信息，产生本次输出</text>
<text x="275" y="222" fill="var(--ink)" font-size="13">需要工具</text>
<rect x="140" y="240" width="230" height="62" rx="18" fill="var(--condition)" stroke="var(--border)" stroke-dasharray="3 3"/>
<text x="255" y="266" text-anchor="middle" fill="var(--ink)" font-size="18" font-weight="500">Tool Call</text><text x="255" y="289" text-anchor="middle" fill="var(--ink)" font-size="13">提出请求，还没有执行动作</text>
<rect x="140" y="352" width="230" height="64" rx="20" fill="var(--node)" stroke="var(--border)"/>
<text x="255" y="379" text-anchor="middle" fill="var(--ink)" font-size="17" font-weight="500">Harness 执行工具</text><text x="255" y="403" text-anchor="middle" fill="var(--ink)" font-size="13">由外部程序读取文件或运行命令</text>
<rect x="140" y="450" width="230" height="54" rx="18" fill="var(--node)" stroke="var(--border)"/>
<text x="255" y="472" text-anchor="middle" fill="var(--ink)" font-size="16" font-weight="500">接回 Tool Result</text><text x="255" y="494" text-anchor="middle" fill="var(--ink)" font-size="12">保留调用记录，加入实际结果</text>
<text x="43" y="300" text-anchor="middle" fill="var(--ink)" font-size="13" transform="rotate(-90 43 300)">新结果 → 新输入 → 再次推理</text>
<text x="438" y="118" text-anchor="start" fill="var(--ink)" font-size="12">无待执行工具</text><text x="438" y="139" text-anchor="start" fill="var(--ink)" font-size="12">且可结束</text>
<rect x="454" y="210" width="172" height="82" rx="20" fill="var(--success)" stroke="var(--success-border)"/>
<text x="540" y="241" text-anchor="middle" fill="var(--success-ink)" font-size="16" font-weight="500">答复 / 请求补充</text><text x="540" y="267" text-anchor="middle" fill="var(--success-ink)" font-size="12">结束当前轮次，交还用户</text>
<text x="540" y="357" text-anchor="middle" fill="var(--ink)" font-size="12">程序达到停止条件时</text><text x="540" y="378" text-anchor="middle" fill="var(--ink)" font-size="12">也会退出循环</text>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">图中展示基本控制流；窄屏可在图内左右滑动查看。</div>
</figure>

## 二、Model inference：模型这一次拿到了什么？

**一次模型推理，是根据本次输入生成本次输出，不是执行整个任务。** 从请求到响应，可以把它看作一次调用边界：程序准备信息，模型处理这些信息，然后返回输出。

输入也不只是用户刚刚打出的一句话。以本文的排查任务为例，模型需要知道：要解决什么问题，有哪些工具可以调用，以及已经获得了什么结果。

在原文讨论的 Responses API 请求中，可以用三个字段理解这几类信息：

| 字段 | 作用 | 放到排查任务中 |
| --- | --- | --- |
| `instructions` | 处理任务的指导 | 依据代码和执行结果说明问题 |
| `tools` | 可调用工具的定义 | 提供读取文件等能力的名称和参数说明 |
| `input` | 当前交互中的输入项 | 用户任务、已有消息、工具调用及其结果 |

`tools` 告诉模型“可以怎样请求读取文件”，并不会自动把整个项目的文件内容交给模型。第一次输入里没有 `UserService.java`，模型就不能把某一段具体实现当作已经读到的事实。

此时，一次推理可以输出一个 `read_file` 请求；拿到内容后的下一次推理，才根据实际代码决定是否继续读取别的文件。

这里也能分清**推理与训练**：循环把新信息送入下一次调用，不是在每次读取文件后重新训练模型。模型的判断发生变化，是因为这次可用的信息变了。

## 三、Tool Call：模型提出动作，不是亲自执行动作

假设模型提出下面的调用。`read_file` 是本文为说明过程使用的假设工具名，不代表 Codex 必须通过这个名称读取文件。

```json
{
  "type": "function_call",
  "name": "read_file",
  "arguments": "{\"path\":\"UserService.java\"}",
  "call_id": "call_read_user_service"
}
```

这条记录说明了三件事：要调用哪个工具、传什么参数，以及用什么标识关联后续结果。它本身不包含已经读出的文件内容。

真正的执行发生在模型之外。Harness 收到请求后，把它交给对应的工具实现；工具读取文件，并把内容或错误信息返回。

因此，这里有两个不同的事件：

- **Tool Call：** 模型提出“请读取这个文件”。
- **Tool Execution：** 外部程序真的进行读取，并产生结果。

在自定义工具场景里，执行程序可以在应用进程中；具体运行在哪台机器，不改变这个区别。**模型生成了调用参数，不等于它已经直接访问了磁盘。**

这也解释了为什么工具执行失败是有意义的反馈。路径不存在、文件无法读取，都属于实际执行结果，而不是模型在输出请求时就能保证的事情。

## 四、Tool Result：下一次判断为什么能接上上一次行动？

假设工具成功读到了文件。返回给模型的不是一句脱离来源的“找到了”，而是与那次请求对应的结果项：

```json
{
  "type": "function_call_output",
  "call_id": "call_read_user_service",
  "output": "public User findById(Long id) { return repository.find(id); }"
}
```

这里的代码内容只是缩小后的示例。关键是相同的 `call_id`：它把“这次读取请求”与“这次读取结果”连接起来。[Function calling 文档](https://developers.openai.com/api/docs/guides/function-calling)也以“接收调用 → 应用执行 → 回传结果 → 再次请求模型”组织这个过程。

回看伪代码，有两次追加：先保留 `output.items`，再加入工具结果。**只保留结果，而丢掉模型提出过什么请求，会缺少这段交互的关联信息。** 使用需要回传推理项的接口时，也应按接口要求保留对应输出，而不是把响应随意压成一段文本。

下一次调用获得的是更新后的交互，不是模型凭空知道外部程序刚刚做了什么。沿着这个例子，执行过程可以是：

| 模型调用 | 本次已有的信息 | 本次可能产生的输出 |
| --- | --- | --- |
| 第一次 | 用户要求排查，尚未读取实现 | 请求读取 `UserService.java` |
| 第二次 | 已有读取请求与文件内容，看到方法委派给 Repository | 请求读取 Repository 的实现 |
| 第三次 | 两个文件的内容都已返回 | 说明哪个分支会返回空值，以及判断依据 |

如果第一次读取返回“文件不存在”，第二次判断就应该围绕这个新事实展开，例如确认路径，而不是沿着一段并不存在的代码继续分析。

**动态决定下一步，具体就体现在这里：相同的任务入口，因为工具返回的信息不同，后续行动可以不同。**

工具结果也不是绝对正确的保证：读到的内容是否完整、结果是否足以支持结论，仍需要判断。循环提供的是获取新证据的机会，不是自动正确的保证。

## 五、Exit Condition：循环结束，不一定等于任务成功

前面的示例可能调用模型三次，也可能第一次就能答复。调用次数不是目标；需要新信息时继续，已经能够结束时退出，才是这个循环的意义。

最基本的退出情况可以分成三类：

| 情况 | 当前执行怎样结束 |
| --- | --- |
| 已有足够信息，可以给出最终答复 | 返回结果，结束当前轮次 |
| 缺少关键条件，无法可靠继续 | 说明阻塞原因，请求用户补充或帮助 |
| 达到程序设定的停止条件 | 停止继续调用，并交代当前状态 |

第二类里，模型可以回复“请提供正确的项目路径”。这是一条结束当前轮次的消息，但不是宣称排查已经完成。用户补充路径后，可以开始下一轮处理。

第三类对应伪代码中的 `shouldStop()`，例如达到最大迭代次数或用户中断。它提醒我们：**循环是否继续，不能完全依赖模型总会在恰当的时候主动结束。**

还需要分清三个尺度：

- **一次 inference：** 一次模型输入与输出。
- **一个 turn：** 从用户提出本轮请求，到系统结束本轮处理；中间可以包含多次 inference 和工具执行。
- **一段 conversation：** 可以包含多个 turn，用户还可以继续补充信息。

所以，某次模型响应生成完毕，只能说明这一次响应结束了。如果其中还有工具调用，外部执行和后续推理仍可能继续；反过来，系统已经退出本轮循环，也不代表用户的最终目标一定完成了。[Running agents](https://developers.openai.com/api/docs/guides/agents/running-agents)中的运行循环同样区分了工具执行后继续与最终答复后返回。

## 六、回看整段循环：Model、Harness 与 Agent 各负责什么？

把三者放回同一段代码，职责就比较清楚了：

| 概念 | 在这里关注的职责 |
| --- | --- |
| Model | 依据当前输入进行一次推理，产生答复或行动请求 |
| Harness / Runtime | 准备输入、调用模型、对接工具、接回结果并控制循环 |
| Agent | 由模型与外部执行机制协作，根据反馈持续推进任务的整体系统 |

这里是为了分清执行职责而划分层次，不是要求所有产品都采用同一套命名。重点在于：**模型输出的是下一步，Harness 把下一步变成实际执行，再把结果带回模型。**

这也回答了开头的问题。Agent 不只是一次 LLM 调用，因为一次输出之后，还可以接上外部行动和新一轮判断；但一个具体任务也可能无需工具，一次推理就结束。Agent Loop 描述的是系统如何组织执行，而不是要求每个任务都必须绕很多圈。

循环里还有一个很具体的边界：`runTool(call)`。模型提出读取文件、修改代码或执行命令后，这个函数究竟把动作送到了哪里？**哪些文件被修改，命令在哪个进程里运行，程序又在哪个环境中启动？** 这已经从“下一步怎样决定”，走到了“动作真正在哪里发生”。

## 几个关键问题，串起这段循环

**一次推理生成了很长的分析，等于执行了很多轮 Agent Loop 吗？**

不等于。输出长短描述的是一次推理产生了多少内容；循环轮次描述的是调用之间是否接上了外部结果。只有提出请求、执行、接回结果并再次调用，才形成这里讨论的反馈过程。

**为什么不能只把工具结果交回去，省掉工具调用记录？**

结果需要对应它所回答的请求。保留工具名、参数和调用标识，才能知道哪次行动得到了什么反馈。具体接口还可能要求保留其他输出项，不能把所有历史都替换成最后一条结果。

**Harness 写了固定的 `while`，为什么 Agent 仍能动态行动？**

循环规定的是调用与反馈的连接方式，不是业务步骤表。读取实现后，是继续追调用链、检查另一份文件，还是已经能够说明原因，要依据当时拿到的信息决定。执行框架固定，与具体路线固定，是两件不同的事。

**模型说“已经修好”，能作为退出依据吗？**

它可以是当前轮次的一条结束消息，但不是修复正确的独立证据。是否真的满足任务，需要结合实际修改和检查结果判断。应当区分“系统不再继续调用”与“任务结果已经得到验证”。

**工具失败以后，Loop 一定要再试一次吗？**

不一定。失败信息可以进入下一次判断，但重试不是唯一行动。路径明确错误时，可以查找位置或请求补充；无法继续时可以结束；达到程序停止条件时则不应继续。反馈的价值在于改变下一步，而不是强制重复上一步。

## 参考资料

- [OpenAI — Unrolling the Codex agent loop](https://openai.com/index/unrolling-the-codex-agent-loop/)
- [OpenAI Docs — Function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [OpenAI Docs — Conversation state](https://developers.openai.com/api/docs/guides/conversation-state)
- [OpenAI Docs — Running agents](https://developers.openai.com/api/docs/guides/agents/running-agents)
- [上一篇：从架构到一个真正的 Agent](/zh-cn/posts/practical-guide-building-agents/)
- [配套阅读：Computer Environment——Agent 的动作在哪里真正执行？](/zh-cn/posts/agent-computer-environment/)
