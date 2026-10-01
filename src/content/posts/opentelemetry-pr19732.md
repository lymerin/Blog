---
title: '代码能跑还不够：一次 OpenTelemetry Review 教会我的事'
description: '从 Spring Rabbit 重复遥测到反复修改方案，记录我在 OpenTelemetry PR #19732 中遇到的 review、版本兼容问题，以及进入大型仓库时想法的变化。'
pubDate: 2026-10-01T11:26:38+08:00
tags:
  - OpenTelemetry
  - Java Agent
  - Spring Rabbit
  - RabbitMQ
  - Code Review
  - 版本兼容
draft: false
postType: metaOnly
---

这是我到目前为止做过最折磨的一次开源修改。

一开始，问题看起来很明确：Spring `@RabbitListener` 消费 RabbitMQ 消息时，一次处理会产生两个 `process` Span，`messaging.process.duration` 也被记录了两次。问题能复现，原因也不算特别难找。我当时更多在想，既然已经知道哪里重复了，把其中一层关掉，应该就差不多了吧。

真正开始改以后，我才发现，难的不是让重复的 Span 消失，而是让这次修改和项目原来的架构、历史版本以及遥测语义都能对上。好几次我觉得方案已经能工作，review 又指出了我没看到的地方。

[PR #19732](https://github.com/open-telemetry/opentelemetry-java-instrumentation/pull/19732) 从 8 月 20 日提交，到 9 月 2 日合并，来回改了不少。但回头看，最值得记录的不是改了多少行，而是这段过程中我怎么从“这段代码应该能跑”，慢慢开始问：**这个项目希望我怎样解决这类问题？**

## 一条消息，为什么会出现两个 process Span？

[Issue #19588](https://github.com/open-telemetry/opentelemetry-java-instrumentation/issues/19588) 涉及 RabbitMQ 和 Spring Rabbit 两套 instrumentation 同时启用的情况。

以 `SimpleMessageListenerContainer` 为例，RabbitMQ 的 dispatch thread 先执行 consumer 的 `handleDelivery()`。但 Spring 的这个 consumer 并不在这里直接调用用户的 listener，而是先把消息放进 `BlockingQueue`，再由另一个线程取出来处理。

RabbitMQ instrumentation 在第一段回调外面创建了一个 `process` Span；Spring Rabbit instrumentation 在实际调用 listener 时，又创建了一个。线程切换以后，第一段的当前上下文不会自动覆盖第二段，于是原本想描述一次处理的两层 instrumentation，都留下了自己的遥测。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; text-align:left; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 1 · Simple Container 中，两段不同的工作都被标成了 process</figcaption>
<div tabindex="0" role="region" aria-label="图 1 · Spring Rabbit 重复 process 遥测路径" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg class="otel-flow" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="otel19732-path-title otel19732-path-desc" viewBox="0 0 640 558" style="display:block; width:100%; min-width:520px; height:auto; font-family:var(--font-sans); --flow-node:light-dark(#e8f3fc,#142b3e); --flow-condition:light-dark(#f4f9fe,#102333); --flow-ink:light-dark(#235e89,#c0def4); --flow-border:light-dark(#d0e0ed,#355167); --flow-line:light-dark(#8e959d,#8295a6); --flow-warn:light-dark(#fff3d7,#352918); --flow-warn-ink:light-dark(#8b5b22,#f3ce8d); --flow-warn-border:light-dark(#e8c98e,#80663a);">
<title id="otel19732-path-title">Spring Rabbit 重复 process 遥测路径</title>
<desc id="otel19732-path-desc">修复前，Simple Container 的 RabbitMQ 分发线程把消息放进队列，这段回调产生 RabbitMQ process 遥测。Spring listener 线程取出消息并执行用户代码，又产生 Spring process 遥测。示意是执行路径，不表示 Span 的父子关系。</desc>
<defs><marker id="otel19732-path-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<path d="M200 104 V146 M200 224 V266 M200 324 V372 M200 446 V478" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" marker-end="url(#otel19732-path-arrow)"/>
<path d="M350 185 H384 M350 409 H384" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-dasharray="4 5" marker-end="url(#otel19732-path-arrow)"/>
<rect x="50" y="30" width="300" height="74" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="200" y="61" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">RabbitMQ dispatch thread</text>
<text x="200" y="87" text-anchor="middle" fill="var(--flow-ink)" font-size="13">TracedDelegatingConsumer</text>
<rect x="50" y="148" width="300" height="76" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="200" y="181" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">handleDelivery()</text>
<text x="200" y="206" text-anchor="middle" fill="var(--flow-ink)" font-size="13">Spring consumer 把消息放进队列</text>
<rect x="386" y="148" width="234" height="76" rx="18" fill="var(--flow-warn)" stroke="var(--flow-warn-border)"/>
<text x="503" y="181" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="15" font-weight="500">RabbitMQ process</text>
<text x="503" y="206" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="12.5">Span + duration</text>
<rect x="80" y="268" width="240" height="56" rx="18" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-dasharray="3 4"/>
<text x="200" y="302" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">BlockingQueue</text>
<text x="332" y="303" fill="var(--flow-ink)" font-size="13" opacity=".8">线程切换</text>
<rect x="50" y="374" width="300" height="72" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="200" y="405" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">Spring listener thread</text>
<text x="200" y="430" text-anchor="middle" fill="var(--flow-ink)" font-size="13">invokeListener() → 用户代码</text>
<rect x="386" y="374" width="234" height="72" rx="18" fill="var(--flow-warn)" stroke="var(--flow-warn-border)"/>
<text x="503" y="405" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="15" font-weight="500">Spring Rabbit process</text>
<text x="503" y="430" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="12.5">Span + duration</text>
<rect x="50" y="480" width="300" height="56" rx="18" fill="var(--flow-condition)" stroke="var(--flow-border)"/>
<text x="200" y="514" text-anchor="middle" fill="var(--flow-ink)" font-size="15">同一次消息处理，留下两份 process 遥测</text>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">修复前的执行路径示意，不是 Span 父子关系图。小屏可在图内左右滑动。</div>
</figure>

这不只是“多一个 Span 不好看”。第一段主要是在入队，真正执行用户 `@RabbitListener` 的是第二段，两段工作的语义也不同。

`DirectMessageListenerContainer` 又是另一种情况：没有同样的线程交接，Spring 的 process instrumentation 可能因为已有 RabbitMQ process 上下文的 suppression 被抑制。也就是说，换一种 container，实际留下的遥测归属就变了。

所以我要解决的并不是随便删掉一个 Span，而是让两边对**谁负责这次消息处理**达成一致。

## 我的实现能工作，但仓库已经有自己的表达方式

为了让两套 instrumentation 协调，我最初加了一套状态控制，其中一个版本用了 depth counter。进入 Spring 管理的 consumer 注册时增加深度，退出时再减回来，我担心的是调用嵌套以后状态恢复不对。

但 [trask 的 review](https://github.com/open-telemetry/opentelemetry-java-instrumentation/pull/19732#discussion_r3833600069) 指出了两个我没考虑到的地方：这里的注册路径并没有我担心的那种嵌套；仓库也已经有类似问题的处理方式，比如 `KafkaClientsConsumerProcessTracing` 和 `SpringSchedulingTaskTracing`。

它们保存的是进入前的值，退出时恢复，而不是再引入一套计数规则。可以把这种思路简化成：

```java
// 状态保存与恢复的概念示意，不是完整的 Advice 实现
boolean previous = isWrappingEnabled();
setWrappingEnabled(false);
try {
    registerConsumer();
} finally {
    setWrappingEnabled(previous);
}
```

当时我有一点挫败：我确实考虑了状态恢复，为什么还是要改？继续看已有实现以后，我才意识到，我关注的是“自己这套逻辑能不能工作”，维护者还在考虑“这个项目一直怎么表达同类问题”。

depth counter 并不是在所有场景下都不对。但这里已经有够用的模式，我再写另一种，就让以后读代码的人多理解一套规则。

这让我第一次很具体地感觉到，成熟项目里的修改，不只是把功能做出来，还得尽量接得上它原来的语言。

## 我以为只是在记录一个指标，其实绕过了 Instrumenter

另一个印象很深的地方，是我为了保留 consumed-message 指标，曾经自己组织 `AttributesExtractor`、`OperationListener` 和指标的开始、结束流程。

我的想法是，RabbitMQ 的 process Span 不需要了，但计数还要保留，那就把需要的部分单独拿出来。当时看起来只是多写一个小 helper。

但 [review 指出](https://github.com/open-telemetry/opentelemetry-java-instrumentation/pull/19732#discussion_r3833600076)，这等于在 `Instrumenter` 之外维护一条完整的生命周期。它原本负责的 instrumentation scope、版本、schema URL、全局 customizer、异常原因解包和 start/end extractor 分工，都要由这条手写路径自己跟进。

我这才意识到，`Instrumenter` 不是单纯为了少写几行代码。看起来像包装层的东西，后面可能背着很多我还没看到的责任。

最终实现沿用了 spring-kafka 的思路：在 Spring 负责的 listener 路径中，关闭 RabbitMQ 的 process 遥测，把 consumed-message 指标注册到 Spring Rabbit 的 Instrumenter 上。合并代码里的关键部分是：

```java
// SpringRabbitSingletons 中注册 operation metrics 的片段
.addOperationMetrics(MessagingProcessMetrics.get())
.addOperationMetrics(MessagingConsumerMetrics.getConsumedMessages());
```

### 指标数值一样，也不代表语义没变

回看这段讨论时，我发现，自己还需要把“指标有没有记录”和“指标属于谁”分开看。

这次迁移**确实改变了 Spring listener 路径中 consumed-message 指标的 scope**：它从 `io.opentelemetry.rabbitmq-2.7` 转到 `io.opentelemetry.spring-rabbit-1.0`。最终测试也相应检查 Spring scope 下的计数，并确认 RabbitMQ scope 不再重复记录这条指标。

讨论里也出现过不同意见。Copilot 曾[建议保留 RabbitMQ 原来的指标归属](https://github.com/open-telemetry/opentelemetry-java-instrumentation/pull/19732#discussion_r3836045259)，维护者给出的方向则是迁移到 Spring Instrumenter。把这些意见和最终代码放在一起看，我才分清：这里不是不能迁移，而是要让指标跟着实际负责处理消息的 Instrumenter 走，并把相应的测试一起调整。

对我来说，这里的收获不是“scope 永远不能改变”，而是：**一个指标属于谁，本身就是需要明确决定和验证的行为。** 不能只看 dashboard 上的数字仍然是一次，就觉得其他地方都没有变化。

迁移时还要补上原来 RabbitMQ 路径能拿到的信息。Spring 原来的 request 只有 `Message`，这次把 `Channel` 也带进 `SpringRabbitRequest`，再通过已有的属性提取方式补齐服务器和网络信息，而不是只把计数搬过去就结束。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; text-align:left; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 2 · 最终方案明确了 process 遥测的归属，而不是全局关闭 RabbitMQ</figcaption>
<div tabindex="0" role="region" aria-label="图 2 · 最终遥测归属" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg class="otel-flow" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="otel19732-owner-title otel19732-owner-desc" viewBox="0 0 640 408" style="display:block; width:100%; min-width:520px; height:auto; font-family:var(--font-sans); --flow-node:light-dark(#e8f3fc,#142b3e); --flow-condition:light-dark(#f4f9fe,#102333); --flow-ink:light-dark(#235e89,#c0def4); --flow-border:light-dark(#d0e0ed,#355167); --flow-line:light-dark(#8e959d,#8295a6); --flow-success:light-dark(#e5f6eb,#152f26); --flow-success-ink:light-dark(#286447,#a9debf); --flow-success-border:light-dark(#afd3bc,#426c57);">
<title id="otel19732-owner-title">最终遥测归属</title>
<desc id="otel19732-owner-desc">Spring 接管的 listener 路径由 Spring Rabbit Instrumenter 记录 process Span、duration 和 consumed-message 指标，RabbitMQ 不重复记录 process 遥测。原生 basicConsume、consumer-batch 和 RabbitTemplate.receive 的相关 process 路径保留 RabbitMQ instrumentation。生产端 batch 的处理仍归 Spring，不能仅凭 listener 类型分组。</desc>
<defs><marker id="otel19732-owner-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<path d="M160 112 V150 M480 112 V150 M160 224 V264 M480 224 V264" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" marker-end="url(#otel19732-owner-arrow)"/>
<rect x="20" y="22" width="280" height="90" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="160" y="54" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">Spring 接管的 listener 处理</text>
<text x="160" y="80" text-anchor="middle" fill="var(--flow-ink)" font-size="13">单条消息 / producer batch</text>
<text x="160" y="100" text-anchor="middle" fill="var(--flow-ink)" font-size="12" opacity=".8">Simple 与 Direct 使用一致的归属</text>
<rect x="340" y="22" width="280" height="90" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="480" y="54" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">保留 RabbitMQ 的相关路径</text>
<text x="480" y="80" text-anchor="middle" fill="var(--flow-ink)" font-size="13">raw basicConsume / consumer batch</text>
<text x="480" y="100" text-anchor="middle" fill="var(--flow-ink)" font-size="12" opacity=".8">以及 RabbitTemplate.receive</text>
<rect x="20" y="152" width="280" height="72" rx="20" fill="var(--flow-condition)" stroke="var(--flow-border)"/>
<text x="160" y="184" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">Spring Rabbit Instrumenter</text>
<text x="160" y="209" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5">spring-rabbit-1.0 scope</text>
<rect x="340" y="152" width="280" height="72" rx="20" fill="var(--flow-condition)" stroke="var(--flow-border)"/>
<text x="480" y="184" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">RabbitMQ instrumentation</text>
<text x="480" y="209" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5">rabbitmq-2.7 scope</text>
<rect x="20" y="266" width="280" height="114" rx="20" fill="var(--flow-success)" stroke="var(--flow-success-border)"/>
<text x="160" y="297" text-anchor="middle" fill="var(--flow-success-ink)" font-size="16" font-weight="500">由 Spring 记录一次</text>
<text x="160" y="323" text-anchor="middle" fill="var(--flow-success-ink)" font-size="13">process Span + duration</text>
<text x="160" y="347" text-anchor="middle" fill="var(--flow-success-ink)" font-size="13">consumed-message 指标</text>
<text x="160" y="368" text-anchor="middle" fill="var(--flow-success-ink)" font-size="12" opacity=".8">不再手动拼接 metrics 生命周期</text>
<rect x="340" y="266" width="280" height="114" rx="20" fill="var(--flow-success)" stroke="var(--flow-success-border)"/>
<text x="480" y="306" text-anchor="middle" fill="var(--flow-success-ink)" font-size="16" font-weight="500">保留原有相关 process 遥测</text>
<text x="480" y="334" text-anchor="middle" fill="var(--flow-success-ink)" font-size="13">不因修复 Spring 重复问题</text>
<text x="480" y="358" text-anchor="middle" fill="var(--flow-success-ink)" font-size="13">把其他 RabbitMQ 路径一起关掉</text>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">归属示意；duration 和 consumed-message 指标按相应 messaging semconv 配置启用。</div>
</figure>

## Listener 类型，不一定等于实际的消息形态

我后来又遇到了一个看起来很合理、实际却不够可靠的判断：根据 listener 是不是 batch listener，决定 Spring 要不要接管。

问题是，**listener 类型和真正传给 `invokeListener()` 的数据，不完全是一回事**。一个 batch-typed listener，在 consumer batching 没开启的时候，也可能按单条 `Message` 进入调用路径。如果 Spring 按实际消息处理，RabbitMQ 却按 listener 类型决定是否保留 process，两边就可能再次同时记录，或者互相 suppression。

[这条 review](https://github.com/open-telemetry/opentelemetry-java-instrumentation/pull/19732#discussion_r3833600064) 让我记住了一个很实际的问题：跨模块协作的时候，两边的判断依据，真的是同一个事实吗？

这里也不能把所有“batch”都混为一谈。consumer batching 和 producer-created batch 是不同路径。最终实现不只补了注册时的判断，也让 Spring Advice 能处理接收到的 `Message` 或非空 `List<Message>`，测试分别检查 consumer batching 开关、producer batch 以及 Simple / Direct 的行为。

对我来说，这比一句“不要重复打点”具体得多。要让两个模块配合好，得先把它们到底在处理什么说清楚。

## 当前版本测试通过，旧版本可能连 Advice 都没触发

这次最让我头疼的，还是版本兼容。

我最开始在当前源码里找到了 `BlockingQueueConsumer.consumeFromQueue(...)`，就把 Advice 放到这里。当前版本能工作，很容易让我以为已经覆盖了 consumer 注册。

但 [自动 review 提醒](https://github.com/open-telemetry/opentelemetry-java-instrumentation/pull/19732#discussion_r3836073980)，模块支持的 Spring Rabbit 1.0.0 根本没有这个方法。旧版本在 `start()` 里直接调用 `basicConsume`。Advice 挂载点没匹配到，修复就不会触发，却不一定像普通 API 不兼容那样直接报编译错误。

Direct Container 也有类似问题。[维护者指出](https://github.com/open-telemetry/opentelemetry-java-instrumentation/pull/19732#discussion_r3883578967)，2.0.0–2.1.2 没有我选的 `consume()` 路径，`doConsumeFromQueue(String)` 才包住了那里的注册过程。

| 路径 | 最初忽略的地方 | 合并版本里的处理 |
| --- | --- | --- |
| BlockingQueueConsumer | 1.0.0 没有 `consumeFromQueue(String)` | 同时覆盖无参 `start()` 和 `consumeFromQueue(String)` |
| Direct Container | 2.0.0–2.1.2 不走选中的 `consume()` | 匹配 `doConsumeFromQueue` 的一参、两参形式 |

我以前想到兼容性，更多是在检查“有没有调用旧版本不存在的 API”。这次才发现，在 instrumentation 项目里，还得问：**我选的挂载点，在那些版本里真的存在吗？执行路径真的会经过它吗？**

维护者能很快指出旧版本里的这些差异时，我对项目经验的感受特别直接。不是他写 Java 比我快，而是他知道这个类以前长什么样、后来又在哪里改过。

## 连测试里的“先启动，再清空”都需要多想一步

补 container 测试时，我一开始的思路很普通：先启动，然后清掉初始化阶段的遥测，再发消息做断言。

```java
container.start();
testing.clearData();
```

但 consumer registration 是异步完成的。`start()` 返回，不代表相关 startup Span 都已经产生。如果清空得太早，稍后才到的初始化遥测，就会混进后面的 exact trace assertion。

[Copilot 的这条 review](https://github.com/open-telemetry/opentelemetry-java-instrumentation/pull/19732#discussion_r3836045254) 建议先等确定会产生的 setup traces，再清空。最终测试里的顺序是：

```java
// 对应这里预期的三条 setup traces，不是通用的固定等待数量
container.start();
testing.waitForTraces(3);
testing.clearData();
```

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; text-align:left; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 3 · start() 返回了，不代表初始化遥测已经到齐</figcaption>
<div tabindex="0" role="region" aria-label="图 3 · 异步初始化测试的等待与清理顺序" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg class="otel-flow" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="otel19732-test-title otel19732-test-desc" viewBox="0 0 640 442" style="display:block; width:100%; min-width:520px; height:auto; font-family:var(--font-sans); --flow-node:light-dark(#e8f3fc,#142b3e); --flow-condition:light-dark(#f4f9fe,#102333); --flow-ink:light-dark(#235e89,#c0def4); --flow-border:light-dark(#d0e0ed,#355167); --flow-line:light-dark(#8e959d,#8295a6); --flow-warn:light-dark(#fff3d7,#352918); --flow-warn-ink:light-dark(#8b5b22,#f3ce8d); --flow-warn-border:light-dark(#e8c98e,#80663a); --flow-success:light-dark(#e5f6eb,#152f26); --flow-success-ink:light-dark(#286447,#a9debf); --flow-success-border:light-dark(#afd3bc,#426c57);">
<title id="otel19732-test-title">异步初始化测试的等待与清理顺序</title>
<desc id="otel19732-test-desc">左侧立即清空数据，随后到达的 startup Span 可能污染正式断言。右侧先等待本测试已知的 setup traces，然后清空数据，再发消息验证。图只解释这个异步边界，不表示等待可以消除所有测试不稳定因素。</desc>
<defs><marker id="otel19732-test-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<path d="M160 94 V130 M480 94 V130 M160 190 V226 M480 190 V226 M160 286 V326 M480 286 V326" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" marker-end="url(#otel19732-test-arrow)"/>
<text x="160" y="23" text-anchor="middle" fill="var(--flow-ink)" font-size="13" opacity=".8">最初的顺序</text>
<text x="480" y="23" text-anchor="middle" fill="var(--flow-ink)" font-size="13" opacity=".8">调整后的顺序</text>
<rect x="30" y="38" width="260" height="56" rx="18" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="160" y="72" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">container.start()</text>
<rect x="350" y="38" width="260" height="56" rx="18" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="480" y="72" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">container.start()</text>
<rect x="30" y="132" width="260" height="58" rx="18" fill="var(--flow-condition)" stroke="var(--flow-border)"/>
<text x="160" y="167" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">立即 clearData()</text>
<rect x="350" y="132" width="260" height="58" rx="18" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-dasharray="3 4"/>
<text x="480" y="167" text-anchor="middle" fill="var(--flow-ink)" font-size="15" font-weight="500">等待已知的 setup traces 到齐</text>
<rect x="30" y="228" width="260" height="58" rx="18" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-dasharray="3 4"/>
<text x="160" y="263" text-anchor="middle" fill="var(--flow-ink)" font-size="15" font-weight="500">异步 startup Span 稍后到达</text>
<rect x="350" y="228" width="260" height="58" rx="18" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="480" y="263" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">再 clearData()</text>
<rect x="30" y="328" width="260" height="88" rx="20" fill="var(--flow-warn)" stroke="var(--flow-warn-border)"/>
<text x="160" y="363" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="16" font-weight="500">正式断言可能混入初始化数据</text>
<text x="160" y="391" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="13">出现偶发失败</text>
<rect x="350" y="328" width="260" height="88" rx="20" fill="var(--flow-success)" stroke="var(--flow-success-border)"/>
<text x="480" y="363" text-anchor="middle" fill="var(--flow-success-ink)" font-size="16" font-weight="500">再发消息，验证正式遥测</text>
<text x="480" y="391" text-anchor="middle" fill="var(--flow-success-ink)" font-size="13">先分清初始化与测试阶段</text>
</svg>
</div>
</figure>

这个建议看起来只多了一行等待，但它要求我理解系统实际怎么执行。不是把测试步骤按顺序写下来，异步工作就会按我想的顺序完成。

review 里还有命名、测试注解以及属性 getter 写法这些小建议。有些来自维护者，有些来自自动 review。它们也让我开始注意，仓库惯例不一定都写在一份文档里，很多时候就藏在现有代码中。

## API 名字对得上，还得确认值从哪里来

这次还有一位用户 [leonard2901](https://github.com/open-telemetry/opentelemetry-java-instrumentation/pull/19732#issuecomment-5414756155) 用自己的 Spring 应用验证了分支。他确认重复问题解决了，但发现 `messaging.message.body.size` 看起来总是 `0`。

继续看才发现，Spring Rabbit 原来读取的是消息属性里的 `contentLength`，而不是实际 body 的长度。如果发布者没有显式设置这个属性，收到消息以后它仍然可能是零。

我后来把单条消息的大小提取改为实际字节数组长度，并增加了非空 payload 的回归检查。可以把这个变化理解为：

```java
// 原来的来源：消息属性，不一定由发布者设置
message.getMessageProperties().getContentLength();

// 单条消息改用实际 body 长度，省略完整 request 和 batch 分支
byte[] body = message.getBody();
return body == null ? null : (long) body.length;
```

这件事挺让我印象深刻。一个 API 名字看起来完全符合我要的东西，也不代表它在这个具体场景里一定有值。实际用户带来的配置和使用方式，会让我看到自己的测试和理解之外的地方。

## Review 不是只在帮我找 Bug

最开始被指出这些问题时，我确实有点挫败。有时会想，方案明明能工作，为什么还要再改？历史版本的这些细节，我第一次接触这个仓库，怎么可能一下子全知道？

但后面慢慢发现，review 不是要求我一开始就知道所有东西，而是把我局部的理解，放回整个项目里检查。

“保存旧值再恢复”背后，是已经形成的协作模式；“用 Instrumenter”背后，是统一的生命周期；“这个旧版本没有这个方法”背后，是模块已经承诺支持的范围。这些建议表面上让我改几行代码，实际是在补上我暂时看不到的上下文。

我也开始意识到，review 的不同意见需要继续核对，而不是谁说得更肯定就听谁的。像 consumed-message 指标那段，得把维护者的目标、中间版本和最终代码放在一起看，才能知道这次修改到底选择了什么。

维护者的经验，到这里对我来说变得很具体：不是脑子里比我多一条算法，而是知道一个局部修改，会在项目其他地方留下什么影响。

## 做完以后，我进入大型仓库的方式变了一点

回头看，我当时太急着自己设计方案了。理解 Issue、定位问题，下一步就想开始写。review 却反复把我带回已有实现：去看 Kafka 的状态控制，去看 spring-kafka 的 ownership，再看 RabbitMQ 已经使用的属性 getter。

这些实现一直都在那里，只是我还没有形成先找它们的习惯。

做完这个 PR，我开始留意一些原来没注意到的地方：一个抽象为什么要保留，某个测试为什么要等，某个 Advice 为什么要照顾多年前的调用点。以前读代码时，我更多是在找要改的位置，现在也会想多看一步，弄清楚它为什么写成这样。

但这次至少让我多了一个进入仓库时会问的问题。以前是“这段代码应该怎么改”，现在还会问：**这个仓库以前遇到类似问题时，是怎么做的？**

我想，这比记住某一个类名更有用。代码能跑、测试能过，当然重要；但让一个修改真正适合这个项目，还需要理解它已经积累下来的选择。我还在学这一部分，这次 review 正好让我很直接地看到了差距，也知道下一次可以从哪里开始补。

## 相关链接

- [Issue #19588 · Spring Rabbit 重复 process 遥测](https://github.com/open-telemetry/opentelemetry-java-instrumentation/issues/19588)
- [PR #19732 · 修复 Spring Rabbit listener 的重复 process 遥测](https://github.com/open-telemetry/opentelemetry-java-instrumentation/pull/19732)
- [状态保存与恢复的 review](https://github.com/open-telemetry/opentelemetry-java-instrumentation/pull/19732#discussion_r3833600069)
- [Instrumenter 与指标归属的 review](https://github.com/open-telemetry/opentelemetry-java-instrumentation/pull/19732#discussion_r3833600076)
- [合并版本的 SpringRabbitSingletons](https://github.com/open-telemetry/opentelemetry-java-instrumentation/blob/0c16d7c125b42f310b8e40a82212d4b75b1ca6cd/instrumentation/spring/spring-rabbit-1.0/javaagent/src/main/java/io/opentelemetry/javaagent/instrumentation/spring/rabbit/v1_0/SpringRabbitSingletons.java)
- [合并版本的 Spring Rabbit 测试](https://github.com/open-telemetry/opentelemetry-java-instrumentation/blob/0c16d7c125b42f310b8e40a82212d4b75b1ca6cd/instrumentation/spring/spring-rabbit-1.0/javaagent/src/test/java/io/opentelemetry/javaagent/instrumentation/spring/rabbit/v1_0/SpringRabbitMqTest.java)
