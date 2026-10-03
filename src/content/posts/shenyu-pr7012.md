---
title: '从一把锁的争论到 Single-Flight：Apache ShenYu TCP 并发创建修复'
description: '第二次参与 ShenYu：记录一次 TCP Server 并发问题的方案取舍，以及几个 AI 给出不同答案之后，我是怎么继续判断的。'
pubDate: 2026-10-01T02:15:22+08:00
tags:
  - Apache ShenYu
  - Java
  - 并发控制
  - Single-Flight
  - 资源生命周期
  - AI 协作
draft: false
postType: metaOnly
cover: '../../assets/covers/shenyu-pr7012-light.png'
---

[上一篇](/zh-cn/posts/shenyu-pr6909)记录了我第一次在 ShenYu 中完整处理一个 Issue。那次，我更多是在学习怎么从问题入口出发，沿着调用链往下读。第二次遇到的问题，表面上反而更简单：检查缓存，没有就创建一个 TCP Server，再放进缓存。

单线程下，这段逻辑很好理解。但如果两个同步事件同时处理同一个 selector，它们就可能都看到“还没有”，然后各自启动一个 Server。这正是 [Issue #6735](https://github.com/apache/shenyu/issues/6735) 指出的问题。

我最初以为，把这几个操作保护起来就行。真正开始比较方案之后，才发现麻烦的不是“会不会加锁”，而是**应该保护多大的范围，以及一个 selector 的慢操作会不会把其他 selector 也堵住**。

这次我也让几个 AI 分别分析了问题，得到的答案却不太一样。最后的修复通过 [PR #7012](https://github.com/apache/shenyu/pull/7012) 合并。下面想记下的不只是 single-flight 怎么实现，也包括我在几个看起来都有道理的方案之间，是怎么继续做判断的。

## 看起来只是三个操作，为什么会重复创建？

原来的处理路径可以简化成：

```java
// 原有逻辑的简化示意
if (!cache.containsKey(name)) {
    BootstrapServer server = createBootstrapServer(...);
    cache.put(name, server);
}
```

检查、创建、发布，是三个独立动作。即使用的是 `ConcurrentHashMap`，也不会自动把它们变成一整个原子操作。线程 A 检查完缓存之后，线程 B 完全可能在 A 放入结果之前，也通过同一次检查。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; text-align:left; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 1 · 同一个 selector，两个线程都通过了缓存检查</figcaption>
<div tabindex="0" role="region" aria-label="图 1 · 同一个 selector，两个线程都通过了缓存检查" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg class="shenyu-flow" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="shenyu7012-race-title shenyu7012-race-desc" viewBox="0 0 640 544" style="display:block; width:100%; min-width:520px; height:auto; font-family:var(--font-sans); --flow-node:light-dark(#e8f3fc,#142b3e); --flow-condition:light-dark(#f4f9fe,#102333); --flow-ink:light-dark(#235e89,#c0def4); --flow-border:light-dark(#d0e0ed,#355167); --flow-line:light-dark(#8e959d,#8295a6); --flow-warn:light-dark(#fff3d7,#352918); --flow-warn-ink:light-dark(#8b5b22,#f3ce8d); --flow-warn-border:light-dark(#e8c98e,#80663a); --flow-success:light-dark(#e5f6eb,#152f26); --flow-success-ink:light-dark(#286447,#a9debf); --flow-success-border:light-dark(#afd3bc,#426c57);">
<title id="shenyu7012-race-title">图 1 · 同一个 selector，两个线程都通过了缓存检查</title>
<desc id="shenyu7012-race-desc">按从上到下的顺序，线程 A 和 B 先后检查缓存，都看到不存在，然后各自进入 TCP Server 创建流程，产生重复启动与资源管理风险。</desc>
<defs><marker id="shenyu7012-race-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<path d="M160 56 V408 M480 56 V408" stroke="var(--flow-border)" stroke-width="1.2" stroke-dasharray="4 6" fill="none"/>
<path d="M160 324 V420 Q160 436 176 436 H304 Q320 436 320 450 V460" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu7012-race-arrow)"/>
<path d="M480 408 V420 Q480 436 464 436 H336 Q320 436 320 450 V460" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu7012-race-arrow)"/>
<g class="flow-branch"><rect x="106" y="14" width="108" height="28" rx="14" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-width="1.1"/><text x="160" y="33" text-anchor="middle" fill="var(--flow-ink)" font-size="14" font-weight="500">Thread A</text></g>
<g class="flow-branch"><rect x="426" y="14" width="108" height="28" rx="14" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-width="1.1"/><text x="480" y="33" text-anchor="middle" fill="var(--flow-ink)" font-size="14" font-weight="500">Thread B</text></g>
<g class="flow-node"><rect x="20" y="80" width="280" height="60" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)" stroke-width="1.2"/><text x="160" y="106" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">检查缓存：不存在</text><text x="160" y="130" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5" opacity=".8">inCache(name) → false</text></g>
<g class="flow-node"><rect x="340" y="164" width="280" height="60" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)" stroke-width="1.2"/><text x="480" y="190" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">检查缓存：仍不存在</text><text x="480" y="214" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5" opacity=".8">inCache(name) → false</text></g>
<g class="flow-node"><rect x="20" y="264" width="280" height="60" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)" stroke-width="1.2"/><text x="160" y="290" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">进入 Server 创建</text><text x="160" y="314" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5" opacity=".8">createBootstrapServer(...)</text></g>
<g class="flow-node"><rect x="340" y="348" width="280" height="60" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)" stroke-width="1.2"/><text x="480" y="374" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">也进入 Server 创建</text><text x="480" y="398" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5" opacity=".8">createBootstrapServer(...)</text></g>
<g class="flow-warn"><rect x="110" y="462" width="420" height="70" rx="20" fill="var(--flow-warn)" stroke="var(--flow-warn-border)" stroke-width="1.2"/><text x="320" y="493" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="16" font-weight="500">重复启动与资源管理风险</text><text x="320" y="517" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="12.5" opacity=".8">端口绑定冲突 / 新建资源失去缓存跟踪</text></g>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">线程交错示意，从上往下读。小屏可在图内左右滑动查看。</div>
</figure>

这里的创建还不是普通的 `new`：`createBootstrapServer()` 会调用启动方法，涉及 Event Loop、端口绑定和 TCP Server 启动。因此，重复创建不只是多了一个 Java 对象，还可能遇到端口绑定失败，或者让已经创建的服务和资源失去缓存跟踪。

看到这里，我意识到，需要保护的是**同一个 selector 的这一轮创建**，而不只是某一次 Map 操作。但不同 selector 本来没有这个冲突，没必要一起排队。

## 几个方案都有道理，为什么最后没有选全局锁？

我当时把问题交给了几个 AI 分别分析。它们给出的方向差别挺大：DeepSeek 的回答偏向全局锁，GPT 的回答偏向公平读写锁和更严格的原子边界，Gemini 则更倾向按 selector 保存创建状态，不使用全局生命周期锁。

单独看，每种方案都能解释得通。全局锁最直接，把检查、创建、发布包在同一个临界区里，思路很清楚。读写锁看起来更细，可以区分读写访问；公平模式也试图减少线程长期抢不到锁的情况。

但我继续往下想时，关注点变了：**这把锁会让谁等谁？**

TCP Server 的创建和关闭都可能比较慢。如果在整个 Factory 上使用一把全局锁，让启动、关闭这些操作也进入临界区，selector-a 的慢操作就可能挡住无关的 selector-b。把 `synchronized` 换成公平读写锁，也不会自动改变这个互斥范围。

| 讨论过的方向 | 我当时主要考虑的地方 |
| --- | --- |
| 全局锁 | 容易理解，但不想让无关 selector 的启动和关闭一起排队 |
| 全局公平读写锁 | 能细分读写访问，但仍要判断哪些操作持锁、持多久 |
| 按 selector 的 single-flight | 同一轮创建只交给一个线程，其他 selector 不争同一把全局锁 |

所以后来我给自己定的方向是：只限制真正发生冲突的同一个 selector，让其他 selector 尽可能独立地处理。

这不是说“锁越少越好”。对我来说，更重要的是先弄清楚要保护什么，再决定互斥范围，而不是看到并发问题就先把锁加上。

## Single-flight：给正在创建的 selector 留一个位置

最终的实现是在 `TcpBootstrapFactory` 中增加一个创建状态表：

```java
ConcurrentMap<String, CompletableFuture<BootstrapServer>> creations
```

这里的 `CompletableFuture` 让我觉得很有意思。它不只是“异步编程工具”，也可以用来表示：**这个 selector 已经有人在创建了，后来的请求可以等这一次结果。**

准备创建时，先尝试登记自己的 Future：

```java
CompletableFuture<BootstrapServer> creation =
        new CompletableFuture<>();

CompletableFuture<BootstrapServer> existingCreation =
        creations.putIfAbsent(selectorName, creation);
```

`putIfAbsent()` 是原子的。同一个 selector 同时收到两个请求时，只有一个能成功放入占位符，成为这一轮的创建者；另一个拿到已有 Future，走 `awaitCreation(existingCreation)`，不再自己启动 Server。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; text-align:left; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 2 · 同一轮创建，一个线程执行，另一个等待</figcaption>
<div tabindex="0" role="region" aria-label="图 2 · 同一轮创建，一个线程执行，另一个等待" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg class="shenyu-flow" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="shenyu7012-flight-title shenyu7012-flight-desc" viewBox="0 0 640 730" style="display:block; width:100%; min-width:520px; height:auto; font-family:var(--font-sans); --flow-node:light-dark(#e8f3fc,#142b3e); --flow-condition:light-dark(#f4f9fe,#102333); --flow-ink:light-dark(#235e89,#c0def4); --flow-border:light-dark(#d0e0ed,#355167); --flow-line:light-dark(#8e959d,#8295a6); --flow-warn:light-dark(#fff3d7,#352918); --flow-warn-ink:light-dark(#8b5b22,#f3ce8d); --flow-warn-border:light-dark(#e8c98e,#80663a); --flow-success:light-dark(#e5f6eb,#152f26); --flow-success-ink:light-dark(#286447,#a9debf); --flow-success-border:light-dark(#afd3bc,#426c57);">
<title id="shenyu7012-flight-title">图 2 · 同一轮创建，一个线程执行，另一个等待</title>
<desc id="shenyu7012-flight-desc">缓存未命中时，线程用 creations.putIfAbsent 登记占位符。登记成功者启动并发布服务，然后完成 Future；其他相同 selector 的调用等待这次 Future，不重复创建。示意省略二次缓存检查与发布冲突分支。</desc>
<defs><marker id="shenyu7012-flight-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<path d="M320 88 V116" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu7012-flight-arrow)"/>
<path d="M320 184 V208 Q320 222 306 222 H174 Q160 222 160 236 V278" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu7012-flight-arrow)"/>
<path d="M320 208 Q320 222 334 222 H466 Q480 222 480 236 V278" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu7012-flight-arrow)"/>
<path d="M160 344 V380" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu7012-flight-arrow)"/>
<path d="M160 446 V482" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu7012-flight-arrow)"/>
<path d="M160 548 V640" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu7012-flight-arrow)"/>
<path d="M480 344 V640" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu7012-flight-arrow)"/>
<path d="M300 515 H608 Q624 515 624 499 V326 Q624 312 610 312 H602" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="4 5" marker-end="url(#shenyu7012-flight-arrow)"/>
<g class="flow-node"><rect x="170" y="20" width="300" height="68" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)" stroke-width="1.2"/><text x="320" y="50" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">同一个 selector 的创建请求</text><text x="320" y="74" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5" opacity=".8">缓存未命中</text></g>
<g class="flow-node"><rect x="150" y="118" width="340" height="66" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)" stroke-width="1.2"/><text x="320" y="147" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">原子登记创建占位符</text><text x="320" y="171" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5" opacity=".8">creations.putIfAbsent(name, future)</text></g>
<g class="flow-branch"><rect x="113" y="236" width="94" height="28" rx="14" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-width="1.1"/><text x="160" y="255" text-anchor="middle" fill="var(--flow-ink)" font-size="14" font-weight="500">登记成功</text></g>
<g class="flow-branch"><rect x="433" y="236" width="94" height="28" rx="14" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-width="1.1"/><text x="480" y="255" text-anchor="middle" fill="var(--flow-ink)" font-size="14" font-weight="500">已有占位</text></g>
<g class="flow-node"><rect x="20" y="280" width="280" height="64" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)" stroke-width="1.2"/><text x="160" y="308" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">成为创建者</text><text x="160" y="332" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5" opacity=".8">启动 TCP Server</text></g>
<g class="flow-node"><rect x="360" y="280" width="240" height="64" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)" stroke-width="1.2"/><text x="480" y="308" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">成为等待者</text><text x="480" y="332" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5" opacity=".8">awaitCreation(existingCreation)</text></g>
<g class="flow-node"><rect x="20" y="382" width="280" height="64" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)" stroke-width="1.2"/><text x="160" y="410" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">发布启动成功的 Server</text><text x="160" y="434" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5" opacity=".8">cache.putIfAbsent(name, server)</text></g>
<g class="flow-"><rect x="20" y="484" width="280" height="64" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)" stroke-width="1.2"/><text x="160" y="512" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">完成同一次 Future</text><text x="160" y="536" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5" opacity=".8">creation.complete(server)</text></g>
<g class="flow-node"><rect x="20" y="642" width="280" height="68" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)" stroke-width="1.2"/><text x="160" y="672" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">移除本轮创建占位符</text><text x="160" y="696" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5" opacity=".8">finally: remove(name, creation)</text></g>
<g class="flow-"><rect x="350" y="642" width="260" height="68" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)" stroke-width="1.2"/><text x="480" y="672" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">等待结束，不重复创建</text><text x="480" y="696" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5" opacity=".8">当前调用返回 false</text></g>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">展示成功主路径；虚线表示 Future 完成后等待者得以继续。小屏可在图内左右滑动查看。</div>
</figure>

这就是这里的 single-flight：对同一个 key，同一轮只由一个线程执行创建，其他相同请求等待这一次执行。不同 selector 使用不同的占位符，因此不需要争夺一把 Factory 级别的生命周期锁。

最终实现还有两处缓存检查：进入创建流程前先检查已有缓存，成功登记占位符后再检查一次。真正的 Server 启动放在 Map 的原子操作之外，没有把可能比较慢的启动逻辑塞进 `computeIfAbsent()` 的回调里。

### 有了占位符，为什么发布时还用 putIfAbsent？

方案到这里还没结束。创建完成、准备放入缓存时，也要处理“缓存里已经出现了另一个实例”的情况。原有的公开 Factory 方法仍然保留，不能只因为新入口有 single-flight，就假定其他路径一定不会写入缓存。

所以发布时不是直接 `cache.put()`，而是：

```java
BootstrapServer existingServer =
        cache.putIfAbsent(selectorName, bootstrapServer);

if (existingServer != null) {
    bootstrapServer.shutdown();
}
```

如果已有实例，就关闭这次新建但没有成功发布的实例，而不是覆盖已有值。然后把已有实例完成到 Future 中，让等待者结束等待。

这里我开始意识到，一个主方案讲得通，不代表周围的状态变化就都不用再检查。占位符负责协调这一轮创建，缓存的原子发布负责守住最后一道边界，两者解决的不是同一个问题。

## 创建失败了，等待中的线程怎么办？

再往下推演，就会碰到失败路径。比如创建者在绑定端口时失败了，另一边却还有线程在等它的 Future。

如果只让创建线程抛出异常，却没有完成这个 Future，等待者就没有办法知道这次创建已经结束了。因此，失败也要作为这一轮创建的结果传出去：

```java
creation.completeExceptionally(ex);
throw ex;
```

等待方通过 `join()` 得到失败，`awaitCreation()` 再从 `CompletionException` 中取出原始原因。对于这里处理的运行时异常，会重新抛出原来的异常。

不管成功还是失败，最后都会移除这次创建的占位符：

```java
creations.remove(selectorName, creation);
```

这里使用 `remove(key, value)`，只移除当前这一轮的 Future。失败的占位符清掉之后，后续请求才有机会重新尝试。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; text-align:left; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 3 · 启动失败后，也要让这一轮创建结束</figcaption>
<div tabindex="0" role="region" aria-label="图 3 · 启动失败后，也要让这一轮创建结束" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg class="shenyu-flow" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="shenyu7012-failure-title shenyu7012-failure-desc" viewBox="0 0 640 578" style="display:block; width:100%; min-width:520px; height:auto; font-family:var(--font-sans); --flow-node:light-dark(#e8f3fc,#142b3e); --flow-condition:light-dark(#f4f9fe,#102333); --flow-ink:light-dark(#235e89,#c0def4); --flow-border:light-dark(#d0e0ed,#355167); --flow-line:light-dark(#8e959d,#8295a6); --flow-warn:light-dark(#fff3d7,#352918); --flow-warn-ink:light-dark(#8b5b22,#f3ce8d); --flow-warn-border:light-dark(#e8c98e,#80663a); --flow-success:light-dark(#e5f6eb,#152f26); --flow-success-ink:light-dark(#286447,#a9debf); --flow-success-border:light-dark(#afd3bc,#426c57);">
<title id="shenyu7012-failure-title">图 3 · 启动失败后，也要让这一轮创建结束</title>
<desc id="shenyu7012-failure-desc">TCP Server 启动失败后尝试释放已经创建的 LoopResources，保留原始启动异常；工厂将 Future 完成为失败，等待线程得到异常，finally 移除当前占位符，让后续请求能够重试。</desc>
<defs><marker id="shenyu7012-failure-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<path d="M320 84 V118" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu7012-failure-arrow)"/>
<path d="M320 190 V224" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu7012-failure-arrow)"/>
<path d="M320 292 V316 Q320 330 306 330 H174 Q160 330 160 344 V378" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu7012-failure-arrow)"/>
<path d="M320 316 Q320 330 334 330 H466 Q480 330 480 344 V378" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu7012-failure-arrow)"/>
<path d="M480 450 V488" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu7012-failure-arrow)"/>
<g class="flow-warn"><rect x="170" y="20" width="300" height="64" rx="20" fill="var(--flow-warn)" stroke="var(--flow-warn-border)" stroke-width="1.2"/><text x="320" y="48" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="16" font-weight="500">TCP Server 启动失败</text><text x="320" y="72" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="12.5" opacity=".8">例如端口绑定失败</text></g>
<g class="flow-node"><rect x="120" y="120" width="400" height="70" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)" stroke-width="1.2"/><text x="320" y="151" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">尝试释放已创建的 LoopResources</text><text x="320" y="175" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5" opacity=".8">清理异常通过 addSuppressed 保留</text></g>
<g class="flow-condition"><rect x="130" y="226" width="380" height="66" rx="20" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-width="1.2" stroke-dasharray="3 4"/><text x="320" y="255" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">将创建 Future 标记为失败</text><text x="320" y="279" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5" opacity=".8">creation.completeExceptionally(ex)</text></g>
<g class="flow-warn"><rect x="20" y="380" width="280" height="70" rx="20" fill="var(--flow-warn)" stroke="var(--flow-warn-border)" stroke-width="1.2"/><text x="160" y="411" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="16" font-weight="500">等待者收到创建异常</text><text x="160" y="435" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="12.5" opacity=".8">awaitCreation 解包原始原因</text></g>
<g class="flow-node"><rect x="340" y="380" width="280" height="70" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)" stroke-width="1.2"/><text x="480" y="411" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">清除当前创建占位符</text><text x="480" y="435" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5" opacity=".8">finally: remove(name, creation)</text></g>
<g class="flow-"><rect x="340" y="490" width="280" height="68" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)" stroke-width="1.2"/><text x="480" y="520" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">后续请求可以重新尝试</text><text x="480" y="544" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5" opacity=".8">不会被失败占位符一直挡住</text></g>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">小屏可在图内左右滑动查看。</div>
</figure>

这部分让我意识到，Future 占位符不是登记完就能不管了。成功要通知等待者，失败也要通知，最后还要清掉本轮状态。少了一步，原本用来协调线程的机制，反而可能把后来的请求一直挡住。

## 并发创建之外，还要照顾资源的开始和结束

在这次修复里，我也继续检查了 `TcpBootstrapServer` 的生命周期。Server 启动失败时，创建过程可能已经走了一半；关闭时，也可能被多个清理路径重复调用。

### 启动失败，要释放已经创建的资源

启动过程会先创建 `LoopResources`，再调用 `bindNow()` 绑定端口。如果后一步失败，前面创建的资源不会因为方法抛出异常就自动释放。

因此，这次在启动失败时补了清理逻辑。如果清理本身也抛出异常，就把它作为 suppressed exception 挂到原始启动异常上，再继续抛出原始异常。

这样，排查时能看到最初为什么启动失败，也不会丢掉随后清理失败的信息。

### shutdown() 可以重复调用，但关闭流程不重复执行

这次还给 `shutdown()` 加了实例级别的 `synchronized` 和 `disposed` 标记。同一个服务实例的关闭不会并发执行；关闭流程结束时，在 `finally` 中标记为已处理，后续调用直接返回。

这里不是给整个 Factory 加一把全局锁，只是在同一个 Server 实例上协调关闭。

另外，`server.disposeNow()` 失败后，仍然会尝试释放 `LoopResources`；如果两处都失败，后面的异常通过 `addSuppressed()` 保留下来。即使关闭抛出异常，`disposed` 也会置为 `true`，后续调用不会自动重试。

### 一个 selector 关闭得慢，不要挡住另一个

删除操作通过 `removeAndShutdown(selectorName)` 先从缓存中原子移除实例，再执行关闭。不存在时就直接返回，关闭操作不放在 Factory 的全局生命周期锁里。

这也是我比较在意的一点：修复同一个 selector 的重复创建，不应该顺带把其他 selector 的删除堵住。PR 的测试专门构造了一个服务关闭被卡住、另一个服务仍然可以删除的场景。

## 测试时，我开始更多地关注失败和线程交错

相比上一篇，这次测试更偏向并发与生命周期边界，而不是只看某个方法有没有被调用。

| 场景 | 验证内容 |
| --- | --- |
| 同一 selector 并发创建 | 16 个线程同时请求，只有一次调用真正创建并缓存 Server |
| 创建失败 | 不留下成功缓存，后续可以重新尝试 |
| 等待中的调用 | 接收到原始创建失败 |
| 不同 selector 删除 | 一个 shutdown 卡住，不阻塞另一个 selector 的删除 |
| bind 失败 | 尝试释放已创建的 LoopResources |
| 重复 shutdown | 关闭流程不重复执行 |
| 多处释放失败 | 通过 suppressed exception 保留异常信息 |

我觉得这次测试带来的变化是：不能只顺着“创建成功、正常关闭”这条路看，还要主动想一想，两个线程插在一起时会怎样，操作只完成一半时又会留下什么。

把这些场景拆开之后，我对自己的实现才更有把握，也更容易发现只看正常路径时漏掉的地方。

## 第二次参与开源，我对 AI 协作的理解也变了一点

这次最值得我记下的，其实不只是 single-flight 这个方案，还有几个 AI 给出不同答案之后，我是怎么继续往下想的。

一开始，每种回答都能讲出一套理由，我很难只看解释就判断谁更适合。后来我发现，与其继续问“哪一个更安全”，不如把问题具体化：如果 selector-a 启动很慢，selector-b 会不会等？如果创建失败，正在等 Future 的线程会怎样？如果资源已经分配了一半，这时候谁负责清理？

这些问题更接近代码实际会遇到的情况，也让我不再只盯着某个方案的名字。

最后，我没有直接照搬某一个模型的完整代码。按 selector 保存占位状态的主方向更接近 Gemini 当时的建议，而 GPT 的分析也让我继续注意原子发布、异常传播和资源释放这些细节。我需要做的，是判断它们能不能放进同一套实现里，以及哪些改动确实属于这个 Issue。

这个过程比“AI 帮我写了一段代码”更有价值。模型之间意见不一致，有时会让我更困惑，但也会逼着我把原本模糊的要求说清楚：到底哪些操作需要互斥，哪些等待是不必要的，失败之后资源又归谁管。

上一篇让我开始找到阅读大型仓库的方法。这次则让我意识到，有了 AI，也不能省掉自己理解代码和做取舍的过程。它可以帮我找问题、提方案、补充我没想到的场景，但最后提交的是我的 PR，我还是需要知道里面每一处修改为什么存在。

现在我更愿意把 AI 当作几个可以一起讨论的 reviewer，而不是等它们给出一个标准答案。对还在学习的我来说，能借助这些讨论，把一个原本只想到“加锁”的问题继续想清楚，就是这次参与开源很实在的收获。

---

## 相关链接

- [上一篇：第一次参与 Apache ShenYu 的 Bug 修复](/zh-cn/posts/shenyu-pr6909)
- [Issue #6735](https://github.com/apache/shenyu/issues/6735)
- [PR #7012](https://github.com/apache/shenyu/pull/7012)
