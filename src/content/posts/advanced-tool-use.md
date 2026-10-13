---
title: 'Advanced Tool Use：Agent 怎样高效发现和调用工具？'
description: '理解 Tool Search、Programmatic Tool Calling 与 Tool Use Examples：按需加载工具定义，用代码组织调用和处理数据，再用示例说明复杂参数的用法。'
pubDate: 2026-10-12T20:50:00+08:00
category: notes
tags: [Agent, Anthropic, Tool Use, 学习笔记]
draft: false
postType: metaOnly
---

[上一篇](/zh-cn/posts/writing-effective-tools/)关注工具接口的质量：怎样划分能力，怎样写名称、参数和返回值，以及怎样验证 Agent 能否用对。工具本身设计清楚后，还有另一组问题：**工具定义要不要一次全部交给模型？连续查询得到的大量数据，要不要每次都经过模型？复杂参数的正确用法，又怎样让模型看得更直观？**

Anthropic 的 [《Introducing advanced tool use》](https://www.anthropic.com/engineering/advanced-tool-use)介绍了三个机制。它们改变的不是同一个环节：

- **Tool Search Tool：** 先发现相关能力，再按需加载工具定义。
- **Programmatic Tool Calling：** 让代码组织调用、处理中间数据，再把必要结果交给模型。
- **Tool Use Examples：** 用有效调用样例，补充参数组合与使用惯例。

下面继续用一个假设的订单排查场景：查清某位客户最近两周的订单是否存在重复扣款，并列出需要跟进的订单。已有 `orders_search` 和 `orders_get_payment_context` 两个查询工具；现在把它们放进更大的工具库，也让排查涉及更多订单。例子用于解释机制，不对应一套已上线的订单系统。

## 一、工具规模扩大后有哪些问题

假设 Agent 接入订单、支付、物流、客服和内部知识库。工具定义不只有名称，还包含说明、参数 Schema 和示例。如果把整个目录一次交给模型，即使任务只涉及付款排查，物流和知识库的定义也会占据输入空间。

找到工具以后，问题还没有结束。一次订单查询可能返回多页，每笔订单又需要补查支付记录。如果模型每看到一批数据就再决定一次“取下一页”“查下一笔”，大量工作其实只是重复执行已经确定的步骤。

还有一种错误与规模无关：模型选对了工具，参数也满足类型约束，却没有遵守正确的调用约定。例如翻页时沿用了游标，却改了原来的客户或时间范围。

我把这三种开销分别理解为：**发现能力的开销、组织执行的开销，以及理解用法的开销。** 因而，解决方案也不只是继续改工具名称，或把工具合并得更大。

| 发生问题的环节 | 订单排查中的表现 | 对应机制 |
| --- | --- | --- |
| 定义进入模型之前 | 无关服务的工具说明占据输入 | Tool Search Tool |
| 调用与数据处理过程中 | 翻页、补查和筛选反复经过模型 | Programmatic Tool Calling |
| 模型组织参数时 | 参数合法，但组合或续查方式不合适 | Tool Use Examples |

## 二、Agent 怎样发现、调用和理解工具

三个机制分别作用于定义加载、调用执行和参数使用，可以沿着同一条订单排查路径理解。

### 1. Tool Search：按需发现和加载工具定义

**工具目录与定义加载**

在订单排查任务里，模型首先需要的是“按客户和时间查订单”“取得订单的付款证据”，而不是所有服务的完整接口说明。

Tool Search 在这里增加了一次发现过程：

```text
用户提出付款排查任务
        ↓
模型搜索相关工具
        ↓
搜索结果给出工具引用
        ↓
加载匹配工具的完整定义
        ↓
模型按照定义调用订单与支付工具
```

**搜索工具返回的是可调用能力的引用，不是订单数据。** 找到 `orders_search` 并不等于执行了订单查询；模型仍然需要读懂它的输入要求，组织参数，再发出业务工具调用。

Anthropic 的实现通过 `defer_loading` 延后向模型呈现工具定义。工具库仍由应用提供，模型起初只看到搜索入口以及没有延后加载的工具；找到的引用随后展开成完整定义。这区分了两件容易混在一起的事：**应用知道有哪些工具，不代表模型当前已经读过它们。** [Tool Search 文档](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)

例如，订单工具可以被设为延后加载，而少量高频入口直接保留。无需把所有能力一视同仁：每次任务都需要的工具，再搜索一次反而增加步骤。

发现过程也不意味着模型偷偷读完了整个目录。平台提供正则匹配和 BM25 检索等搜索入口，在工具名称、说明及参数描述中寻找匹配能力。前者适合明确的文本模式，后者可以接收自然语言查询；应用也可以提供自己的搜索实现。目录如何检索，与模型拿到定义后如何调用，是两层工作。

**定义维护、适用条件与执行授权**

`defer_loading` 改变的是定义何时进入模型上下文，不是让应用不再维护 Schema，也不保证整个 API 请求只发送一个小目录。对 Anthropic 的工具搜索接口，完整工具定义仍需随请求提供；被推迟的是模型侧的加载。

工具是否能被找到，也继续依赖上一篇讨论的名称与说明。一个叫 `query`、描述只有“查询信息”的接口，即使进入搜索系统，也很难准确表达它能按客户检索订单。

因此，Tool Search 不会替代 Tool Design。它只是把清晰的能力描述变成可检索目录，让当前任务先接触相关的那部分。

搜索还增加了一次交互，也可能漏掉需要的能力。如果工具很少、定义很短，或者任务本来就要使用其中大多数工具，直接加载可能更简单。判断收益时，应同时看加载量、发现成功率和额外耗时，而不是只看工具总数。

最后，**“被搜索出来”不等于“被允许执行”。** 搜索负责发现能力，实际调用仍应经过应用原有的执行检查。

### 2. Programmatic Tool Calling：用代码组织调用与处理数据

**工具桥接与执行流程**

订单排查有一段可以明确写成程序的过程：按固定条件翻完订单页，逐笔取得付款证据，筛选需要跟进的记录，汇总失败项。这些步骤不必每次都让模型重新判断。

Programmatic Tool Calling（PTC）允许模型先写出调用程序，再由代码执行环境运行。程序可以使用循环、条件和数据处理逻辑，把业务工具当作可调用能力组合起来。

这里也要接上 [Agent Loop](/zh-cn/posts/codex-agent-loop/) 的边界：**模型写出调用代码，仍不等于模型亲自查询了数据库。** 在 Anthropic 的 PTC 流程中，代码运行到客户端工具调用时会等待；应用收到请求，执行真正的业务工具并返回结果，程序再继续。中间结果交给运行中的代码处理，程序输出才回到模型。 [PTC 文档](https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling)

<figure class="not-prose" style="margin:1.75em 0;">
  <figcaption style="font-size:.8125rem;color:var(--muted-foreground);margin-bottom:1rem;text-align:center;">图 1 · 程序化调用：工具结果先回到代码，再把必要输出交给模型</figcaption>
  <div role="region" aria-label="程序化工具调用流程图，可横向滚动" tabindex="0" style="overflow-x:auto;max-width:100%;border-radius:16px;padding:8px 0;background:hsl(0 0% 50% / .025);">
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 420" role="img" aria-labelledby="ptc-title ptc-desc" style="display:block;width:100%;min-width:650px;height:auto;font-family:var(--font-sans);--node:light-dark(#e8f3fc,#142b3e);--ink:light-dark(#235e89,#c0def4);--border:light-dark(#d0e0ed,#355167);--line:light-dark(#8e959d,#8295a6);--success:light-dark(#e5f6eb,#152f26);--success-ink:light-dark(#286447,#a9debf);--success-border:light-dark(#afd3bc,#426c57);">
      <title id="ptc-title">代码组织工具调用，模型接收程序输出</title>
      <desc id="ptc-desc">模型生成程序。代码请求客户端执行业务工具，结果回到代码进行处理；需要继续时再次调用，完成后汇总输出交给模型。</desc>
      <defs><marker id="ptc-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 1 1 L 8 5 L 1 9" fill="none" stroke="var(--line)" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
      <g fill="none" stroke="var(--line)" stroke-width="1.5" marker-end="url(#ptc-arrow)">
        <path d="M130 115V270"/>
        <path d="M230 295H250V75H280"/>
        <path d="M380 115V270"/>
        <path d="M280 335H230" stroke-dasharray="4 4"/>
        <path d="M480 310H530"/>
        <path d="M630 270V115"/>
      </g>
      <g font-size="12" fill="var(--line)" text-anchor="middle">
        <text x="142" y="197" text-anchor="start">提交程序</text>
        <text x="230" y="195" transform="rotate(-90 230 195)">请求执行</text>
        <text x="392" y="197" text-anchor="start">结果回到代码</text>
        <text x="255" y="365">继续调用</text>
        <text x="505" y="297">完成</text>
        <text x="642" y="197" text-anchor="start">输出回到模型</text>
      </g>
      <g fill="var(--node)" stroke="var(--border)" stroke-width="1.5">
        <rect x="30" y="35" width="200" height="80" rx="20"/>
        <rect x="280" y="35" width="200" height="80" rx="20"/>
        <rect x="30" y="270" width="200" height="80" rx="20"/>
        <rect x="280" y="270" width="200" height="80" rx="20"/>
      </g>
      <g fill="var(--success)" stroke="var(--success-border)" stroke-width="1.5">
        <rect x="530" y="35" width="200" height="80" rx="20"/>
        <rect x="530" y="270" width="200" height="80" rx="20"/>
      </g>
      <g text-anchor="middle" fill="var(--ink)">
        <g font-size="17" font-weight="600"><text x="130" y="68">模型生成程序</text><text x="380" y="68">客户端执行工具</text><text x="130" y="303">运行调用代码</text><text x="380" y="303">处理工具结果</text></g>
        <g font-size="13"><text x="130" y="94">确定调用与处理逻辑</text><text x="380" y="94">查询真实业务数据</text><text x="130" y="329">发出请求，等待返回</text><text x="380" y="329">分页、过滤与汇总</text></g>
      </g>
      <g text-anchor="middle" fill="var(--success-ink)">
        <g font-size="17" font-weight="600"><text x="630" y="68">模型继续判断</text><text x="630" y="303">输出必要证据</text></g>
        <g font-size="13"><text x="630" y="94">解释结果与回应用户</text><text x="630" y="329">范围、候选与失败项</text></g>
      </g>
    </svg>
  </div>
</figure>

这不是“一次模型调用，所有工作就免费完成了”。业务查询次数、执行时间以及客户端处理请求的往返仍然存在。减少的是部分中间模型推理，以及把大量原始数据反复放进模型上下文的需要。

普通工具调用也可以在一次模型输出中提出多个独立请求，并不天然等于“一次只能调用一个工具”。PTC 更进一步：**把可程序化的循环、分支和数据加工，放进一段持续执行的代码中。**

**订单排查中的模型与代码分工**

先约定一个简单筛选条件：订单存在两个及以上不同的成功扣款记录，且每笔金额都等于订单金额，就列为需要跟进的候选。它只是排查入口，不直接证明重复扣款，更不自动决定退款。

下面是机制伪代码。`tools.call` 表示执行环境提供的工具桥接，`find_candidates` 是本地筛选函数；它们不是 Anthropic SDK 的实际方法。

```python
query = {
    "customer_id": "cus_demo_42",
    "created_from": "2026-09-28T00:00:00+08:00",
    "created_before": "2026-10-12T00:00:00+08:00",
    "page_size": 20,
}

candidates = []
failed_order_ids = []
checked_orders = 0
seen_cursors = set()

while True:
    page = await tools.call("orders_search", query)
    checked_orders += len(page["orders"])

    for order in page["orders"]:
        try:
            evidence = await tools.call(
                "orders_get_payment_context",
                {"order_id": order["order_id"]},
            )
        except ToolExecutionError:
            failed_order_ids.append(order["order_id"])
            continue

        candidates.extend(find_candidates(order, evidence))

    if not page["has_more"]:
        break

    cursor = page["next_cursor"]
    if not cursor or cursor in seen_cursors:
        raise IncompleteScanError("无效或重复的分页游标")
    seen_cursors.add(cursor)
    query = {**query, "cursor": cursor}

print({
    "checked_orders": checked_orders,
    "candidates": candidates,
    "failed_order_ids": failed_order_ids,
    "complete": not failed_order_ids,
})
```

这里值得关注的不是代码长短，而是数据流：付款记录先进入程序，程序完成明确的筛选，模型接收候选证据与扫描范围，而不是逐笔阅读全部流水。发生查询失败时，也把未核对的订单带回来，不能悄悄当成“没有异常”。

`find_candidates` 应保留订单 ID、付款记录 ID、金额与币种、退款状态等后续判断依据。模型据此解释哪些订单需要进一步核对；只返回一个 `true`，虽然短，却把判断依据一起丢掉了。

这个分工同样说明了 PTC 的适用边界。固定条件的筛选、分页、关联和统计适合交给代码；证据不足、业务含义不明确时，应把问题交回模型或人工判断。若任务只是查一笔订单，生成并运行程序可能比直接调用更绕。

**执行结果与完整性检查**

PTC 省去的是不必要的数据中转，不是正确性检查。模型生成的代码仍可能漏掉最后一页、错误处理退款，或者把不同币种金额直接相加。

返回格式也因此更重要。模型有时能从一段文字里理解付款状态，代码却需要知道结果是数组还是对象、金额单位是什么、失败怎样表示。让程序处理工具结果，必须先提供稳定且有说明的输出约定，而不是把一段随意变化的自然语言当作接口。

同样，如果程序最后把所有原始结果全部打印出来，大量数据还是会回到模型，原本的收益也就减弱了。**合理输出应同时满足两件事：比原始数据更聚焦，又足以支撑结论。**

我会保留扫描范围、候选证据、失败项和完成状态，而不只保留一句“发现三笔异常”。这样，模型既能组织回应，也能看见结论的边界。

### 3. Tool Use Examples：用示例说明参数组合

**Schema 与调用示例**

`orders_search` 的 Schema 已经说明 `customer_id` 是字符串，`page_size` 是有范围的整数，`cursor` 是可选参数。说明文字还规定：第一页省略游标；续查时沿用返回的游标，并保持查询条件一致。

这些要求可以写清楚，但模型面对实际调用时，仍要把它们组合成一个输入对象。Tool Use Examples 用少量有效样例，把这种组合直接呈现出来。

在 Anthropic 的工具定义中，`input_examples` 与 `input_schema` 同级，每个样例都必须符合 Schema。以下只是加到上一篇工具定义上的字段片段，不是完整请求： [Tool Use Examples 文档](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools#providing-tool-use-examples)

```json
{
  "input_examples": [
    {
      "customer_id": "cus_demo_42",
      "created_from": "2026-09-28T00:00:00+08:00",
      "created_before": "2026-10-12T00:00:00+08:00"
    },
    {
      "customer_id": "cus_demo_42",
      "created_from": "2026-09-28T00:00:00+08:00",
      "created_before": "2026-10-12T00:00:00+08:00",
      "page_size": 20,
      "cursor": "cursor_demo_page2"
    }
  ]
}
```

第一项展示最小查询：没有 `cursor`，`page_size` 省略时由工具实现使用默认值 20。第二项展示续查：假设上一页返回了 `cursor_demo_page2`，就保留原来的客户、时间范围和实际页大小，再带上这个游标。样例中的 ID 和游标只是演示值，实际调用必须使用查询得到的真实值。

这比堆十个只有客户 ID 不同的样例更有价值，因为它展示的是两种不同使用方式，而不是同一种结构的重复。

**规则校验与示例选择**

不能简单地说“JSON Schema 只能约束类型，表达不了参数关系”。Schema 也能描述枚举、条件和依赖；工具实现则能校验更具体的业务规则。示例的作用，是把正确调用长什么样展示给模型，不是替代这些机制。

例如，“结束时间晚于开始时间”应该在说明中明确，并由执行端检查，不能只在样例里默默出现。游标是否属于当前查询，也不能因为模型见过示例就不再验证。

更复杂的工具可能有嵌套过滤条件、几组可选参数，或不同操作对应不同字段。此时，最小输入、常用组合和容易误用的边界样例，能够帮助模型理解调用惯例。即使工具库只有几个接口，这个机制也有用。

示例本身也会占用输入空间。因此，重点不是给每个工具配一大串样例，而是为真正有歧义的组合提供少量有区分度的示范，并保证它们与当前定义一致。

## 三、三种机制怎样组合与验证

把三个机制放回同一个订单任务，可以看到一条完整但不必每次都走满的路径：

1. **发现能力：** 在大目录中找到订单查询与付款证据工具，加载相关定义。
2. **理解用法：** 依据说明、Schema 和样例，确定时间范围、客户 ID 与分页方式。
3. **组织执行：** 若涉及多页和大量补查，用代码承接重复调用与筛选。
4. **返回证据：** 将扫描范围、候选订单与未完成项交给模型，形成可解释的回应。

它们不是必须绑在一起的套餐。工具很多、每次只调用一两次，可能主要需要搜索；工具不多但数据量很大，可能主要需要程序化调用；只有一个接口但参数组合复杂，也可能值得加示例。

这也把第五篇和第六篇的边界区分开了：**前者改善模型面对的接口，后者改善模型接触接口和处理调用的过程。** 如果工具说明本来就模糊，或者结果字段缺少业务含义，换成搜索或代码执行仍然会遇到问题。

是否更高效，还要回到任务中比较。可以沿用同一份订单数据与目标，分别观察：

| 机制 | 不只看什么 | 还要检查什么 |
| --- | --- | --- |
| Tool Search | 初始定义是否变少 | 必需工具是否被找到，额外发现步骤是否值得 |
| PTC | 中间数据是否减少 | 总耗时、真实调用次数、分页完整性与筛选结果 |
| Examples | 参数格式是否正确 | 复杂组合是否用对，样例增加的输入是否有收益 |

对于这个案例，候选订单是否正确、失败项是否被保留，比单看某次 token 消耗更重要。更少的输入与模型轮次应服务于任务完成，而不是掩盖漏查。

从这里看 Context Engineering，也有了具体入口：**哪些定义值得现在加载，哪些中间数据需要让模型看到，哪些证据不能在压缩结果时丢掉？** 工具使用机制已经在影响上下文的内容，但上下文质量还包括任务历史和其他信息的组织，并不等于把工具输出一律缩短。

## 几个关键问题，串起发现、调用与参数用法

**工具越多，就越应该使用 Tool Search 吗？**

工具总数只是一个信号。更重要的是定义占用多少输入、当前任务通常需要多少能力，以及搜索能否稳定找到它们。大量工具中每次只用很少一部分，按需加载更有价值；如果大多数工具每次都需要，搜索反而可能增加步骤。高频工具直接保留，也可以和延后加载组合。

**搜索到工具后，模型是不是已经拿到了业务数据？**

不是。发现阶段得到的是工具引用及随后加载的定义，回答“有什么能力可以使用”。订单、付款等业务数据，要在模型按定义发出实际调用、业务工具执行之后才能获得。发现成功与执行成功是两个不同检查点。

**PTC 和普通并行工具调用有什么不同？**

普通调用可以让模型一次提出多个独立工具请求，再把结果交回模型。PTC 则让代码表达连续调用、循环、条件和数据处理，结果先回到程序，模型不必介入每个中间步骤。两者都可能并行执行独立查询；区别不只在并发，而在谁组织后续步骤、谁先处理返回数据。

**为什么 PTC 不能简单理解成“一次调用替代很多次调用”？**

程序内部仍会发出真实工具请求，客户端仍要执行并返回结果。可能减少的是模型推理轮次与进入上下文的中间数据，不一定减少业务调用次数。重复查询、错误循环和低效算法甚至会增加工作量，所以需要同时检查代码行为与任务结果。

**有了调用示例，Schema 和参数校验还重要吗？**

重要。Schema 提供结构约束，说明明确语义，执行端检查实际条件，示例帮助模型看懂有效组合。示例不是强制规则：它既不能保证模型照做，也不能阻止无效输入被执行。几者要表达一致的接口，而不是互相替代。

**只把最终汇总交给模型，会不会漏掉重要信息？**

会，因此输出设计不能只追求短。订单排查至少需要保留核对范围、候选的付款证据、查询失败项和完成状态。把无关流水留在代码里，与把支撑判断的证据删掉，是两回事。模型需要的是足够得出可靠结论的信息，不是最多或最少的信息。

## 参考资料

- [Anthropic · Introducing advanced tool use on the Claude Developer Platform](https://www.anthropic.com/engineering/advanced-tool-use)
- [Claude Platform Docs · Tool search tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)
- [Claude Platform Docs · Programmatic tool calling](https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling)
- [Claude Platform Docs · Providing tool use examples](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools#providing-tool-use-examples)
