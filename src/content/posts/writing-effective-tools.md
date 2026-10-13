---
title: 'Tool Design：怎样让 Agent 选对工具、用对接口？'
description: '从订单排查案例理解工具粒度、命名、参数与返回值的设计，再通过真实任务、调用记录和独立测试改进工具质量。'
pubDate: 2026-10-12T20:35:00+08:00
category: notes
tags: [Agent, Anthropic, Tool Design, 学习笔记]
draft: false
postType: metaOnly
---

[Agent Loop](/zh-cn/posts/codex-agent-loop/)讲清了工具请求怎样进入执行循环，[Computer Environment](/zh-cn/posts/agent-computer-environment/)解释了动作在哪里发生。这一篇接着看循环中的接口：**同一份软件能力，怎样交给模型，才容易被选对、用对，并产生有用的反馈？**

读 Anthropic 的 [《Writing effective tools for agents — with agents》](https://www.anthropic.com/engineering/writing-tools-for-agents)，我更关注两件相互连接的事：工具如何设计，以及设计是否真的有效。原文将原型、任务评估和持续修改放在一起，而不是把一份工具说明写完就当作结束。

- **能力怎么划分：** 从用户任务出发，确定值得暴露的工具与操作边界。
- **接口怎么表达：** 让名称、参数和返回值共同解释工具的用途。
- **质量怎么判断：** 通过任务结果与调用记录，找出设计中需要修改的地方。

下面用一个假设的订单排查任务贯穿这些问题：客服想查清一位客户最近两周的订单里，是否存在重复扣款，并列出需要跟进的订单。工具、数据和测试任务都是围绕这个场景设计的示例。

## 一、API 能被调用，不等于 Agent 容易用对

假设订单系统已经提供三个 API：查订单、查支付流水、查退款记录。后端程序可以按照写好的逻辑调用它们：订单 ID 从哪里来，支付状态如何解释，哪些字段要继续传给下一个接口，都由代码明确安排。

换成 Agent，模型需要先从任务中判断该选哪个工具，再组织参数，并根据结果决定是否继续。于是，接口除了要满足程序执行，还多了一层要求：**它必须让调用者理解，自己提供的能力适合解决什么问题。**

比如一个工具叫 `query`，只有 `id` 和 `type` 两个参数。开发者知道 `type=2` 表示支付流水，但模型看到的只是两个缺少业务含义的字段。即使参数类型完全合法，也可能查错对象。

我会把这里的质量分成两个层面：

| 层面 | 要检查的问题 |
| --- | --- |
| 实现正确性 | 给定合法参数，工具是否查询了正确资源，返回了正确数据？ |
| 使用有效性 | 给定用户任务，Agent 是否选对工具、填对参数，并正确使用返回结果？ |

前者仍然需要普通的软件测试；后者要把模型放进调用过程才能观察。接口单元测试通过，不能替代 Agent 使用测试。

这也不意味着传统 API 必须全部重做。已有 API 可以继续作为底层能力，Agent Tool 则在上面重新组织名称、参数、数据和操作边界。需要改变的是对模型暴露的使用方式，不一定是业务系统本身。

## 二、工具粒度：围绕任务组织能力，而不是照着端点逐个包装

订单排查至少需要两种动作：先找到相关订单，再检查某笔订单的付款与退款情况。如果只给一个 `list_all_orders`，Agent 就得先接收大量无关订单，再逐条筛选；如果把每张表都拆成一个工具，它又需要自己拼接内部数据关系。

针对这个场景，我会先提供两项能力：

```text
orders_search
按客户、时间范围等条件查找订单，返回摘要与可继续查询的 ID

orders_get_payment_context
按订单 ID 返回付款、退款及关联关系，供重复扣款排查使用
```

第二个工具可以在内部调用多个 API，但从 Agent 的视角看，它完成的是一个连贯的取证步骤。支付流水和退款记录经常需要一起解释，把它们放在同一份结果中，可以减少模型反复获取、关联数据的工作。

反过来，我不会把它继续扩大成 `handle_customer_problem`，让工具同时排查、决定补偿并执行退款。这几件事不是同一个操作边界：查询证据与改变订单状态，应当在接口上明确区分。

因此，工具粒度不是“越细越灵活”，也不是“越粗越省调用”。我更看重三个判断：

- **结果是否连贯：** 合并后的操作，是否共同服务于一个明确任务步骤？
- **输入是否可获得：** Agent 能否从用户信息或前一个结果中拿到所需参数？
- **行为是否可预期：** 调用工具之前，是否清楚它只读取信息，还是会修改状态？

如果一次查询就能得到完整付款证据，没必要强迫模型拼接多份流水；如果一次调用悄悄完成了退款，就把本该独立判断的动作藏进了查询。

工具的价值不是多包一层函数，而是把底层软件能力整理成模型可以理解和组合的任务步骤。

## 三、Tool Definition：名称、说明与 Schema 要表达同一个接口

工具定义不是只有 JSON Schema。名称影响模型如何区分能力，说明解释适用场景，Schema 则给参数建立结构约束。三者如果说的是不同的事，模型就需要在矛盾信息里猜测。

### 名称先交代资源，再交代动作

`search`、`get_data`、`process` 很难与其他工具区分。订单工具采用 `orders_search`、`orders_get_payment_context`，至少让模型先看到资源范围，再看到操作。

如果还有客服工单搜索，可以叫 `tickets_search`。这种 Namespace 不是为了名字整齐，而是让“搜订单”和“搜工单”在选择时就有区别。名称规则是否有效，仍要通过调用记录判断；没有必要先假设某种前缀或后缀对所有模型都最优。

### 说明写清用途，也写清不做什么

“搜索订单”解释得太少。我会把这个示例工具的说明写成：

> 按客户 ID 和创建时间范围查询订单，适用于订单定位和售后排查。时间范围为左闭右开，使用带时区的时间戳。返回订单摘要、稳定的订单 ID 和下一页游标；不返回完整支付流水，也不会退款或修改订单。排查扣款明细时，使用返回的订单 ID 调用 `orders_get_payment_context`。

这段说明既解释当前工具，也交代下一步怎样接上其他能力。它不是替模型写死整个任务流程，而是让能力边界可见。

### Schema 约束形状，字段语义还要明确

下面使用 Anthropic 自定义工具的 `name`、`description`、`input_schema` 结构。日期、分页和默认值是这个示例自己的约定，不是平台统一规定：

```json
{
  "name": "orders_search",
  "description": "按客户与创建时间查询订单摘要，不修改订单。支付明细请用返回的 order_id 调用 orders_get_payment_context。时间范围为左闭右开，须含时区。",
  "input_schema": {
    "type": "object",
    "properties": {
      "customer_id": { "type": "string", "minLength": 1, "description": "客户系统的稳定 ID，不是姓名或订单 ID" },
      "created_from": { "type": "string", "format": "date-time", "description": "包含此时间，必须带时区" },
      "created_before": { "type": "string", "format": "date-time", "description": "不包含此时间，必须晚于 created_from" },
      "page_size": { "type": "integer", "minimum": 1, "maximum": 50, "description": "每页条数；省略时工具实现使用 20" },
      "cursor": { "type": "string", "minLength": 1, "description": "原样传入上一页 next_cursor；首轮省略，翻页保持其他查询条件不变" }
    },
    "required": ["customer_id", "created_from", "created_before"],
    "additionalProperties": false
  }
}
```

`required` 表示必填，`additionalProperties: false` 拒绝未声明字段。字段出现在 `properties` 中，并不自动成为必填项；这点在 [JSON Schema 的对象说明](https://json-schema.org/understanding-json-schema/reference/object)中有明确区分。

但结构合法仍不等于业务正确。一个合法字符串可能是不存在的客户 ID；两个合法时间戳也可能前后颠倒。`format` 是否被严格校验还取决于校验器配置，工具实现仍应验证时间格式、时区、范围顺序和游标与查询条件的匹配关系。

默认值也需要代码落实。“省略时使用 20”不是写在说明里就会自动发生。这里工具实现负责补默认值、检查输入，再调用底层 API。

假设任务明确指定查询区间，一次调用可以是：

```json
{
  "customer_id": "cus_demo_42",
  "created_from": "2026-09-28T00:00:00+08:00",
  "created_before": "2026-10-12T00:00:00+08:00",
  "page_size": 20
}
```

如果用户只说“最近两周”，运行时还需要提供当前日期及业务时区，让这个相对范围能够被解释。参数要求明确，输入信息也要足够，不能把缺少依据的问题全归给模型。

## 四、Tool Result：让下一步判断有依据，也有继续查询的入口

工具返回值可以看作下一轮判断的材料。订单搜索不需要把数据库整行原样返回，但也不能只剩一句“找到了一些订单”。

下面是一页示例结果。`payment_status` 描述付款状态，不直接宣称存在重复扣款；是否重复，需要继续核对支付流水。

```json
{
  "orders": [
    {
      "order_id": "ord_demo_104",
      "order_number": "DEMO-104",
      "created_at": "2026-10-03T10:20:00+08:00",
      "amount_minor": 12900,
      "currency": "CNY",
      "payment_status": "paid"
    }
  ],
  "next_cursor": "cursor_demo_page2",
  "has_more": true
}
```

这里每个字段都有作用：订单号方便向用户解释，`order_id` 供后续工具调用，金额与币种帮助核对交易，分页信息说明这一页不是全部结果。示例约定 `amount_minor` 使用最小货币单位，12900 对应人民币 129 元；这个约定需要在工具输出说明中写清。

**减少返回内容，不等于删除下一步所需的标识。** 只返回易读的订单号，却让后续工具要求另一种未提供的内部 ID，调用链就会断开。同样，只返回“不透明 ID”而没有可解释的业务信息，模型也难以组织可靠回答。

### 分页、筛选与截断解决的是不同问题

在这个示例里，客户与时间条件先缩小查询范围；分页再控制每次返回多少订单。只有一笔订单出现疑点时，可以进一步查询它的付款上下文，而不是给每笔订单附上完整流水。

如果结果因长度限制被截断，需要明确告诉 Agent：哪些内容没有返回，以及怎样继续获取。无声地丢掉后半部分，再让模型回答“全部检查完了”，就是接口制造的信息缺口。

这里也不追求返回越短越好。只有一个总数，可能节省了当前调用的 token，却迫使模型不断补查。应当比较完成整个任务所需的调用和信息，而不是只看某一份响应的长度。

### 错误结果也应该支持下一步行动

假设 Agent 把查询结束时间写在开始时间之前，只有 `INVALID_ARGUMENT` 不够定位问题。这个示例可以返回：

```json
{
  "error": {
    "code": "INVALID_TIME_RANGE",
    "field": "created_before",
    "message": "created_before 必须晚于 created_from；两个时间都必须包含时区。",
    "hint": "保留查询目标，修正时间范围后重试。"
  }
}
```

这是工具的业务错误示例，不是某个协议的完整错误包。若通过 MCP 暴露，还需要按协议区分工具执行错误与协议错误；[MCP Tools 规范](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)定义了对应机制。

错误反馈应指向可以修正的地方，但不能暗示所有错误都值得重试。时间范围写错可以修改参数；服务不可用可能需要等待或报告；没有访问条件也不能靠反复换参数绕过去。

“没有匹配订单”则是一次成功查询的空结果，不应混同为执行失败。这会影响 Agent 是向用户说明查无记录，还是继续修正一条失败请求。

## 五、Tool Evaluation：把设计判断放进完整任务里检验

接口写清楚以后，仍有一个不能靠阅读说明回答的问题：Agent 实际使用时，会不会按照预期理解它？

我会先把工具实现跑通，确认查询、参数校验和分页本身正确，再给 Agent 自然表达的任务。前者检查软件行为，后者检查工具定义与模型之间的配合。

### 测试任务要有目标，不要提前把解法塞给模型

“调用 `orders_search`，再调用付款工具”更像操作指令，不能充分检验模型是否理解两项能力的区别。对于这个场景，可以准备这样的任务与检查点：

| 任务 | 可以核对的结果 |
| --- | --- |
| 查客户在指定两周内有没有重复扣款，列出需跟进订单 | 与测试数据中的有效支付、退款关系核对，既不能漏报，也不能把失败支付算成重复扣款 |
| 同一范围跨多页，疑似订单在最后一页 | 最终检查覆盖全部目标订单，而不是只回答第一页 |
| 用户只提供客户姓名，存在重名客户 | 先澄清或使用已提供的客户定位能力，不编造 `customer_id` |
| 支付查询返回服务暂时不可用 | 说明核对受阻，不把失败响应解释成“没有重复扣款” |

测试数据需要预先确定。比如同一订单的两笔扣款中，一笔已全额退款，是否仍列为“需要跟进”，就要按任务中的业务口径定义。否则模型和检查器可能讨论的是两个不同问题。

检查器也不应只接受某一句固定文案。这里真正要核对的是订单集合、证据和结论是否一致。先查全部订单再逐笔取证，或先利用已有筛选缩小范围，都可能得到正确结果，不必强制只有一条调用路径。

### 调用记录解释哪里出了问题

只看最终回答，会漏掉工具设计的问题。一条结论即使碰巧正确，过程也可能反复查询、漏掉分页，或者用了不属于目标客户的数据。

可以记录工具名、输入参数、返回内容、错误、耗时、调用次数，以及整个任务的 token 消耗。把这些记录与预期结果对照，才能区分不同原因：

| 调用中的现象 | 优先检查的设计点 |
| --- | --- |
| 经常选择工单搜索，而不是订单搜索 | 名称、资源范围和适用场景是否容易混淆 |
| 反复提交姓名作为 `customer_id` | 字段含义与客户定位能力是否明确 |
| 同一页被重复读取 | 游标、翻页条件和结束信号是否清楚 |
| 每笔订单都先查大量无关字段 | 返回值是否遗漏关键证据，或工具粒度不合适 |
| 查到记录却无法继续获取支付明细 | 前后工具需要的 ID 是否连贯 |

这些是排查方向，不是看到一种现象就能断定一种原因。比如调用次数增加，可能是分页太小，也可能是数据规模本来更大；需要结合任务和返回记录判断。

模型对工具的反馈可以帮助归纳问题，但它的解释不能替代实际记录。模型说“数据不够”，要继续检查到底缺了哪个字段；说“已经查完”，则要看最后是否仍有 `has_more`。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 1 · 用任务结果与调用记录，推动工具设计迭代</figcaption>
<div tabindex="0" role="region" aria-label="工具设计与评估的迭代流程" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="tool-design-title tool-design-desc" viewBox="0 0 640 420" style="display:block; width:100%; min-width:540px; height:auto; font-family:var(--font-sans); --node:light-dark(#e8f3fc,#142b3e); --ink:light-dark(#235e89,#c0def4); --border:light-dark(#d0e0ed,#355167); --line:light-dark(#8e959d,#8295a6); --success:light-dark(#e5f6eb,#152f26); --success-ink:light-dark(#286447,#a9debf); --success-border:light-dark(#afd3bc,#426c57);">
<title id="tool-design-title">工具设计、执行与评估的闭环</title>
<desc id="tool-design-desc">准备工具原型，执行任务集，检查结果与调用轨迹，修改工具设计，再更新原型重测。独立任务用于复核效果。</desc>
<defs><marker id="tool-design-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M1 1L7 4L1 7" fill="none" stroke="var(--line)" stroke-width="1.3"/></marker></defs>
<g fill="none" stroke="var(--line)" stroke-width="1.5" marker-end="url(#tool-design-arrow)"><path d="M280 96H360"/><path d="M480 142V242"/><path d="M360 288H280"/><path d="M160 242V142"/></g>
<g fill="var(--node)" stroke="var(--border)" stroke-width="1.2"><rect x="40" y="50" width="240" height="92" rx="20"/><rect x="360" y="50" width="240" height="92" rx="20"/><rect x="360" y="242" width="240" height="92" rx="20"/></g>
<rect x="40" y="242" width="240" height="92" rx="20" fill="var(--success)" stroke="var(--success-border)" stroke-width="1.2"/>
<g text-anchor="middle" fill="var(--ink)"><text x="160" y="87" font-size="18" font-weight="600">准备工具原型</text><text x="160" y="114" font-size="14">接口定义与可运行实现</text><text x="480" y="87" font-size="18" font-weight="600">执行任务集</text><text x="480" y="114" font-size="14">固定条件，记录调用</text><text x="480" y="279" font-size="18" font-weight="600">检查结果与调用轨迹</text><text x="480" y="306" font-size="14">定位误选、误用与冗余</text></g>
<g text-anchor="middle" fill="var(--success-ink)"><text x="160" y="279" font-size="18" font-weight="600">修改工具设计</text><text x="160" y="306" font-size="14">用独立任务复核效果</text></g>
<g text-anchor="middle" fill="var(--line)" font-size="13"><text x="320" y="79">交给 Agent</text><text x="530" y="197">核对证据</text><text x="320" y="315">形成改动</text><text x="103" y="197">更新并重测</text></g>
<text x="320" y="389" text-anchor="middle" fill="var(--ink)" font-size="14">比较任务正确性，也比较完成任务所需的代价</text>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">迭代依据是任务证据，不是模型对工具的主观评分。窄屏可在图内左右滑动查看。</div>
</figure>

### 修改后重测，也要检查是否只适应了熟悉题目

如果调用记录显示模型一直混淆客户 ID 与订单 ID，可以先改字段名称与说明，再保持任务、数据和模型设置一致，比较修改前后的表现。一次改动同时换模型、换数据、改接口，就很难判断改善来自哪里。

模型的调用行为可能波动，同样的条件也值得重复运行。比较一组任务的完成情况、常见错误与调用代价，比用单次成功宣称“设计已经改好”更有依据。

用于修改工具的任务之外，还要保留一组独立任务：换客户、换时间表达、改变分页数量，加入空结果与服务错误。它们检验的是设计能否迁移，而不是是否记住了一批熟悉问题。

评估也可以请 Agent 辅助分析：把失败记录、工具定义和预期结果放在一起，让它归类问题、提出修改建议，再由测试验证。这里的 Agent 是帮助发现和修改问题的协作者，不是工具质量的最终裁判。

我更看重的结论是：**工具质量不是说明写得像不像文档，而是 Agent 能否借助这份接口，稳定地完成有明确检查标准的任务。** 名称、Schema、输出和错误处理，最终都要回到这个标准上。

## 几个关键问题，串起接口设计与质量验证

**参数已经符合 Schema，为什么仍可能用错工具？**

Schema 主要约束输入结构。客户 ID 写成另一个存在的客户 ID，可能通过校验，却不符合用户目标；选中一个不相关的工具，也不会因为参数合法就变成正确选择。需要把任务理解、工具选择与输入校验分开检查。

**减少工具数量，就一定能提高完成率吗？**

不一定。合并经常一起取用的信息，可以减少关联工作；把不相干的查询和写入挤进一个万能工具，则会扩大使用歧义。应该比较任务步骤是否更清楚，而不是单纯减少工具数。

**返回值越短，是否代表工具越高效？**

不是。少了关键 ID、分页信号或付款证据，模型可能需要更多调用，甚至得出错误结论。高效应当按整个任务衡量：在结果可靠的前提下，减少无关信息和可避免的往返。

**为什么评估不能只检查最终回答？**

最终回答说明结果是否正确，调用记录则解释工具怎样被使用。漏掉最后一页却碰巧得出正确结论，与完整核对后的正确结论，不是同样可靠的使用过程。两者一起看，才容易定位接口问题。

**怎样区分工具改好了，还是只适应了测试题？**

保留没有用于修改设计的独立任务，并维持可比较的运行条件。改进若只发生在熟悉任务上，遇到换名、跨页或错误场景就失效，还不足以说明工具具有更好的通用可用性。

这一篇关注的是接口质量：让一个能力的用途、输入和反馈都清楚。工具库扩大后，怎样按需发现工具、组织频繁调用和处理大量中间结果，是另一层机制问题；它不能替代这里的设计，也不只是把工具数量继续往上加。

## 参考资料

- [Anthropic — Writing effective tools for agents — with agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [Claude Platform Docs — Define tools](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools)
- [Claude Cookbook — Tool evaluation](https://platform.claude.com/cookbook/evals-tool-evaluation)
- [JSON Schema — Object](https://json-schema.org/understanding-json-schema/reference/object)
- [Model Context Protocol — Tools（2025-06-18）](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
- [配套阅读：Computer Environment](/zh-cn/posts/agent-computer-environment/)
