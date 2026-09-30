---
title: '从 refresh() 追到 TCP Server：第一次参与 Apache ShenYu 的 Bug 修复'
description: '记录我第一次在 Apache ShenYu 中完整处理一个 Issue 的过程，以及读代码、修复问题时的一些收获。'
pubDate: 2026-10-01T01:29:33+08:00
tags:
  - Apache ShenYu
  - Java
  - 数据同步
  - 资源生命周期
  - 并发安全
draft: false
postType: metaOnly
---

这是我第一次比较完整地在 Apache ShenYu 这样规模的开源仓库里处理一个 Issue。这次遇到的是 [Issue #6781](https://github.com/apache/shenyu/issues/6781)：HTTP 同步收到空的 ProxySelector（代理选择器）列表后，Gateway 没有及时清理原有状态，可能留下已经不再需要的 TCP 服务。

刚看到空列表分支直接 `return` 时，我以为补一次 `refresh()` 调用就能解决。但顺着代码往下读，才发现事情没有这么简单：**刷新请求经过 Subscriber 后，并没有继续传到真正负责关闭 TCP Server 的 Handler。** 要修复这个问题，我还得弄清楚这几个模块是怎么配合的。

最后，修复通过 [PR #6909](https://github.com/apache/shenyu/pull/6909) 合并。这篇文章想记下从“一行调用”继续往下追的过程，也聊聊第一次在不熟悉的开源项目里改代码时，我学到了什么。

## 配置删空，TCP Server 为什么还在？

先看一下这次问题涉及的配置和运行状态。Apache ShenYu 是一个基于 Java 的 API 网关，支持多种协议代理和动态配置。

其中，TCP 插件可以通过 ProxySelector（代理选择器）配置监听端口、负载均衡策略及上游服务等信息。管理员在 Admin 中修改相关配置后，这些配置可以同步到 Gateway，并反映到实际运行的 TCP 代理服务中。

正常情况下，我们希望配置和运行状态保持一致。例如，Admin 中删除某个代理选择器后，Gateway 应当不再保留对应的 TCP 服务。

问题发生在配置同步返回**空列表**的时候。

假设最初存在两个代理选择器：

```text
Admin:
  ProxySelector A
  ProxySelector B

Gateway:
  TCP Server A
  TCP Server B
```

随后，管理员删除了全部代理选择器。下一次 HTTP 全量同步返回的 ProxySelector 数据变成空列表（下面只是简化示意，不是原始响应的完整格式）：

```json
{
  "PROXY_SELECTOR": {
    "data": []
  }
}
```

按照预期，Gateway 应当识别到这组配置已经为空，并清理原有运行状态。

但原来的 `ProxySelectorRefresh` 在检测到空列表后，只记录了一条日志，然后直接 `return`。**同步入口知道配置已经为空，却没有把清理动作传递给真正保存运行时状态的组件。**

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; text-align:left; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 1 · 空快照处理：修复前后对比</figcaption>
<div tabindex="0" role="region" aria-label="空快照处理：修复前后对比" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg class="shenyu-flow" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="shenyu-refresh-title shenyu-refresh-desc" viewBox="0 0 640 648" style="display:block; width:100%; min-width:520px; height:auto; font-family:var(--font-sans); --flow-node:light-dark(#e8f3fc,#142b3e); --flow-condition:light-dark(#f4f9fe,#102333); --flow-ink:light-dark(#235e89,#c0def4); --flow-border:light-dark(#d0e0ed,#355167); --flow-line:light-dark(#8e959d,#8295a6); --flow-warn:light-dark(#fff3d7,#352918); --flow-warn-ink:light-dark(#8b5b22,#f3ce8d); --flow-warn-border:light-dark(#e8c98e,#80663a); --flow-success:light-dark(#e5f6eb,#152f26); --flow-success-ink:light-dark(#286447,#a9debf); --flow-success-border:light-dark(#afd3bc,#426c57);">
<title id="shenyu-refresh-title">空快照处理：修复前后对比</title>
<desc id="shenyu-refresh-desc">HTTP 空快照进入 ProxySelectorRefresh；修复前直接返回，旧服务残留；修复后沿 Subscriber 和 Handler 转发，清理缓存并尝试关闭服务。</desc>
<defs><marker id="shenyu-refresh-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<path d="M320 90 V122" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu-refresh-arrow)"/>
<path d="M320 180 V194 Q320 206 308 206 H172 Q160 206 160 218 V270" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu-refresh-arrow)"/>
<path d="M320 194 Q320 206 332 206 H468 Q480 206 480 218 V270" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu-refresh-arrow)"/>
<path d="M160 334 V372" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu-refresh-arrow)"/>
<path d="M480 334 V372" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu-refresh-arrow)"/>
<path d="M480 436 V474" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu-refresh-arrow)"/>
<path d="M480 542 V580" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu-refresh-arrow)"/>
<g class="flow-node"><rect x="170" y="20" width="300" height="70" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)" stroke-width="1.2"/><text x="320" y="51" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">HTTP 同步收到空快照</text><text x="320" y="75" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5" opacity=".8">ProxySelector 列表为空</text></g>
<g class="flow-node"><rect x="170" y="124" width="300" height="56" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)" stroke-width="1.2"/><text x="320" y="157.5" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">ProxySelectorRefresh</text></g>
<g class="flow-branch"><rect x="125" y="226" width="70" height="28" rx="14" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-width="1.1"/><text x="160" y="245" text-anchor="middle" fill="var(--flow-ink)" font-size="14" font-weight="500">修复前</text></g>
<g class="flow-branch"><rect x="445" y="226" width="70" height="28" rx="14" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-width="1.1"/><text x="480" y="245" text-anchor="middle" fill="var(--flow-ink)" font-size="14" font-weight="500">修复后</text></g>
<g class="flow-node"><rect x="25" y="272" width="270" height="62" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)" stroke-width="1.2"/><text x="160" y="308.5" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">直接 return</text></g>
<g class="flow-warn"><rect x="25" y="374" width="270" height="70" rx="20" fill="var(--flow-warn)" stroke="var(--flow-warn-border)" stroke-width="1.2"/><text x="160" y="405" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="16" font-weight="500">旧 TCP Server 残留</text><text x="160" y="429" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="12.5" opacity=".8">清理事件没有传到资源管理层</text></g>
<g class="flow-node"><rect x="345" y="272" width="270" height="62" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)" stroke-width="1.2"/><text x="480" y="299" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">通知 Subscriber</text><text x="480" y="323" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5" opacity=".8">refresh()</text></g>
<g class="flow-node"><rect x="345" y="374" width="270" height="62" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)" stroke-width="1.2"/><text x="480" y="401" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">分发到 Handler</text><text x="480" y="425" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5" opacity=".8">refresh()</text></g>
<g class="flow-node"><rect x="345" y="476" width="270" height="66" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)" stroke-width="1.2"/><text x="480" y="505" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">清理 TCP 服务缓存</text><text x="480" y="529" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5" opacity=".8">TcpBootstrapFactory.clearCache()</text></g>
<g class="flow-success"><rect x="345" y="582" width="270" height="54" rx="20" fill="var(--flow-success)" stroke="var(--flow-success-border)" stroke-width="1.2"/><text x="480" y="614.5" text-anchor="middle" fill="var(--flow-success-ink)" font-size="16" font-weight="500">移除缓存 · 尝试 shutdown()</text></g>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem;">小屏可在图内左右滑动查看。</div>
</figure>

看到这里，我意识到，**空列表也有它的含义**。如果这次全量同步是成功的，那么返回空列表就表示当前已经没有任何代理选择器，而不是“不需要处理”。

如果程序把空列表理解成“不需要处理”，运行状态就可能与 Admin 的配置出现偏差。

## 追踪 refresh()：调用链在哪里断开？

明确问题后，我主要沿着这条调用链检查：

```text
ProxySelectorRefresh
        ↓
ProxySelectorDataSubscriber
        ↓
CommonProxySelectorDataSubscriber
        ↓
ProxySelectorDataHandler
        ↓
TcpProxySelectorDataHandler
        ↓
TcpBootstrapFactory
        ↓
BootstrapServer
```

这里涉及两个不同的层次。

第一个层次是**数据同步**。`ProxySelectorRefresh` 负责接收同步数据，并通知订阅者。

第二个层次是**插件的运行时状态**。具体插件的 Handler 负责管理对应的代理服务，而 TCP 插件通过 `TcpBootstrapFactory` 缓存实际的 `BootstrapServer`。

问题是，这两层之间的清理行为并没有完全连接起来。

### 第一处问题：空列表没有触发刷新

原本 `ProxySelectorRefresh` 的空列表分支会直接返回。修复这部分只需要在返回之前通知所有订阅者：

```java
proxySelectorDataSubscribers.forEach(
    ProxySelectorDataSubscriber::refresh
);
```

但如果修改只停留在这里，问题仍然没有完全解决。

### 第二处问题：refresh 是空实现

继续查看 `ProxySelectorDataSubscriber`，我发现它虽然定义了 `refresh()`，但默认实现没有任何操作。而 `CommonProxySelectorDataSubscriber` 原本也没有把刷新请求传给实际负责资源管理的 Handler。

换句话说，即使 HTTP 层触发了刷新，插件内部也不会自动清除已有的 TCP 服务。

因此，真正需要解决的问题不只是“有没有调用 `refresh()`”，而是：

> 这个清理事件能否沿着完整的调用链，最终到达负责管理资源的组件？

追到这里，我才明白，不能只看入口有没有调用这个方法，还得继续看它最后做了什么。

## 修复设计：沿原有架构传递清理事件

确认调用链后，我没有选择让 HTTP 同步模块直接操作 TCP Server，而是继续使用 ShenYu 原有的 Subscriber 和 Handler 结构。

这样，数据同步模块只需要表达“当前配置需要清空”，至于如何清理，则交给对应的插件。

### 给 Handler 增加统一的刷新入口

首先，在 `ProxySelectorDataHandler` 接口中增加一个默认的 `refresh()` 方法。

这里使用 `default` 方法，是为了不让现有 Handler 都跟着改。需要清理资源的实现，比如 TCP Handler，再覆盖这个方法。

写到这里，我开始意识到，在已有项目里补一个接口方法，不能只看自己的代码能不能用，还要看看其他实现会不会受影响。当然，空默认实现不会自动清理资源，有状态的 Handler 仍然需要实现自己的清理逻辑。

### 由 CommonSubscriber 负责分发

接下来，修改 `CommonProxySelectorDataSubscriber.refresh()`，让它遍历 `handlerMap`，调用对应的 Handler：

```java
handlerMap.values().forEach(
    ProxySelectorDataHandler::refresh
);
```

这样，清理逻辑就不再固定于 HTTP 同步模块，而是被放到了已有的插件处理结构中。

这样，HTTP 层不需要知道 TCP 服务该怎么关闭，只需要把刷新请求传下去，具体清理由插件负责。这次我主要处理的，还是 Issue 中的 HTTP 空快照场景。

## 缓存清理：移除引用不等于释放资源

接下来就是 TCP 插件的资源释放。

在 `TcpBootstrapFactory` 中，项目使用 `ConcurrentHashMap` 保存代理选择器与 TCP 服务实例之间的对应关系：

```text
selectorName → BootstrapServer

tcp-proxy-a → BootstrapServer A
tcp-proxy-b → BootstrapServer B
```

最简单的做法似乎是直接调用 `cache.clear()`。但这里有一个问题：**从 Map 中删除引用，并不等于真正停止 TCP 服务。**

`BootstrapServer` 是运行中的服务实例，可能涉及监听端口以及其他网络资源。仅清空容器，并不会自动调用它的 `shutdown()`。

如果想确保 TCP 代理选择器被清理，就需要完成两个动作：

1. 将实例从缓存中移除。
2. 对移除的实例执行关闭操作。

因此，我在 `TcpBootstrapFactory` 中增加了 `clearCache()` 方法，统一处理这两件事。

### 为什么使用条件删除？

这里没有采用单纯的遍历再按 key 删除，而是使用类似下面的逻辑：

```java
if (cache.remove(selectorName, bootstrapServer)) {
    // 关闭当前移除成功的实例
}
```

`ConcurrentHashMap.remove(key, value)` 的意义是：只有当前 key 对应的值仍然是这个实例时，才执行删除。

考虑一个并发场景：线程 A 正在执行全量清理；与此同时，线程 B 更新了某个代理选择器，把旧服务替换成新服务。

如果线程 A 直接按照遍历时拿到的 key 删除，就可能误删线程 B 刚刚更新的实例。条件删除可以避免这种特定情况：发现当前值已经改变时，线程 A 不再删除新值。

同时，只有成功移除缓存项的线程才继续关闭对应实例，也减少了并发清理时重复关闭同一对象的风险。

不过，条件删除保护的是当前这条缓存项，并没有把整个全量刷新变成原子操作。

### 如果一个 TCP Server 关闭失败呢？

假设当前存在三个服务：

```text
Server A
Server B
Server C
```

如果在关闭 Server B 时抛出异常，直接让异常中断整个遍历，就可能导致 Server C 没有机会执行清理。

因此，`clearCache()` 会在每个实例的 `shutdown()` 外捕获 `RuntimeException`，记录错误并继续处理其他实例。这样可以避免单个实例的关闭异常阻断其他实例的清理。

关闭失败的实例仍可能有资源没有释放。这次先记录异常，让其他服务继续清理，没有再把重试和资源恢复一起加进来。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; text-align:left; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 2 · TCP 缓存清理及异常处理</figcaption>
<div tabindex="0" role="region" aria-label="TCP 缓存清理与异常处理" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg class="shenyu-flow" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="shenyu-cleanup-title shenyu-cleanup-desc" viewBox="0 0 640 850" style="display:block; width:100%; min-width:520px; height:auto; font-family:var(--font-sans); --flow-node:light-dark(#e8f3fc,#142b3e); --flow-condition:light-dark(#f4f9fe,#102333); --flow-ink:light-dark(#235e89,#c0def4); --flow-border:light-dark(#d0e0ed,#355167); --flow-line:light-dark(#8e959d,#8295a6); --flow-warn:light-dark(#fff3d7,#352918); --flow-warn-ink:light-dark(#8b5b22,#f3ce8d); --flow-warn-border:light-dark(#e8c98e,#80663a); --flow-success:light-dark(#e5f6eb,#152f26); --flow-success-ink:light-dark(#286447,#a9debf); --flow-success-border:light-dark(#afd3bc,#426c57);">
<title id="shenyu-cleanup-title">TCP 缓存清理与异常处理</title>
<desc id="shenyu-cleanup-desc">遍历缓存；条件删除失败则跳过，成功则调用 shutdown；RuntimeException 记录后继续遍历，未抛出异常也继续遍历。关闭失败不代表资源已释放，全量清理也不具备严格原子性。</desc>
<defs><marker id="shenyu-cleanup-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<path d="M330 90 V138" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu-cleanup-arrow)"/>
<path d="M285 210 V232 Q285 246 271 246 H139 Q125 246 125 260 V420" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu-cleanup-arrow)"/>
<path d="M375 210 V232 Q375 246 389 246 H406 Q420 246 420 260 V298" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu-cleanup-arrow)"/>
<path d="M420 370 V420" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu-cleanup-arrow)"/>
<path d="M370 492 V514 Q370 528 356 528 H314 Q300 528 300 542 V622" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu-cleanup-arrow)"/>
<path d="M470 492 V514 Q470 528 484 528 H526 Q540 528 540 542 V622" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu-cleanup-arrow)"/>
<path d="M125 490 V712 Q125 728 141 728 H306 Q322 728 322 744 V766" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu-cleanup-arrow)"/>
<path d="M300 694 V726 Q300 742 316 742 H354 Q370 742 370 756 V766" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu-cleanup-arrow)"/>
<path d="M540 694 V712 Q540 728 524 728 H434 Q418 728 418 744 V766" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu-cleanup-arrow)"/>
<g class="flow-node"><rect x="200" y="20" width="260" height="70" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)" stroke-width="1.2"/><text x="330" y="51" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">遍历 TCP Server 缓存</text><text x="330" y="75" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5" opacity=".8">selectorName / BootstrapServer</text></g>
<g class="flow-condition"><rect x="215" y="140" width="230" height="70" rx="20" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-width="1.2" stroke-dasharray="3 4"/><text x="330" y="171" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">条件删除成功？</text><text x="330" y="195" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5" opacity=".8">remove(key, value)</text></g>
<g class="flow-branch"><rect x="102" y="264" width="46" height="28" rx="14" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-width="1.1"/><text x="125" y="283" text-anchor="middle" fill="var(--flow-ink)" font-size="14" font-weight="500">否</text></g>
<g class="flow-branch"><rect x="397" y="264" width="46" height="28" rx="14" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-width="1.1"/><text x="420" y="283" text-anchor="middle" fill="var(--flow-ink)" font-size="14" font-weight="500">是</text></g>
<g class="flow-node"><rect x="290" y="300" width="260" height="70" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)" stroke-width="1.2"/><text x="420" y="340.5" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">调用 shutdown()</text></g>
<g class="flow-node"><rect x="35" y="422" width="180" height="68" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)" stroke-width="1.2"/><text x="125" y="461.5" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">跳过该条目</text></g>
<g class="flow-condition"><rect x="265" y="422" width="310" height="70" rx="20" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-width="1.2" stroke-dasharray="3 4"/><text x="420" y="462.5" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">抛出 RuntimeException？</text></g>
<g class="flow-branch"><rect x="277" y="552" width="46" height="28" rx="14" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-width="1.1"/><text x="300" y="571" text-anchor="middle" fill="var(--flow-ink)" font-size="14" font-weight="500">是</text></g>
<g class="flow-branch"><rect x="517" y="552" width="46" height="28" rx="14" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-width="1.1"/><text x="540" y="571" text-anchor="middle" fill="var(--flow-ink)" font-size="14" font-weight="500">否</text></g>
<g class="flow-warn"><rect x="210" y="624" width="180" height="70" rx="20" fill="var(--flow-warn)" stroke="var(--flow-warn-border)" stroke-width="1.2"/><text x="300" y="664.5" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="16" font-weight="500">记录异常</text></g>
<g class="flow-success"><rect x="450" y="624" width="180" height="70" rx="20" fill="var(--flow-success)" stroke="var(--flow-success-border)" stroke-width="1.2"/><text x="540" y="664.5" text-anchor="middle" fill="var(--flow-success-ink)" font-size="16" font-weight="500">未抛出异常</text></g>
<g class="flow-node"><rect x="270" y="768" width="200" height="66" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)" stroke-width="1.2"/><text x="370" y="806.5" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">继续遍历</text></g>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem;">小屏可在图内左右滑动查看。</div>
</figure>

## 单条删除：check-then-act 的竞态

除了全量清理，这次还修改了 `TcpProxySelectorDataHandler.removeProxySelector()`。

原来的实现会先调用 `inCache()` 判断某个选择器是否存在，再调用 `removeCache()` 获取实例并关闭。乍一看没有问题，但并发情况下，这两个操作不是原子的。

例如：

```text
线程 A：检查 selector 是否存在 → true
线程 B：清理并移除 selector
线程 A：再次 removeCache() → null
线程 A：调用 shutdown() → NullPointerException
```

这里就是典型的 *check-then-act* 问题。

`ConcurrentHashMap` 能保证单次操作的线程安全，但无法自动保证两个独立操作之间的状态不变。

修复思路也比较直接：不再依赖之前的存在性判断，而是直接尝试移除，随后判断返回值是否为空。只有确实取得 `BootstrapServer` 实例时才调用 `shutdown()`。

这样既处理了并发移除导致的空指针风险，也让重复删除不存在的选择器成为安全的空操作。

这是修复过程中顺带发现的问题。改动不大，却让我意识到，不能因为用了 `ConcurrentHashMap` 就觉得这段逻辑一定安全。单次操作是线程安全的，但把“先判断、再删除”放在一起，中间还是可能被其他线程插进来。

## 回归测试：验证事件传递与关闭调用

这次 PR 增加了多层测试，而不是只检查 `ProxySelectorRefresh` 有没有调用订阅者。

| 测试位置 | 验证内容 |
| --- | --- |
| `ProxySelectorRefreshTest` | 空列表触发刷新，非空列表仍执行订阅 |
| `CommonProxySelectorDataSubscriberTest` | 刷新事件能传递到各 Handler |
| `TcpProxySelectorDataHandlerTest` | 验证 shutdown() 调用、缓存移除和关闭异常隔离 |
| `HttpSyncDataServiceTest` | HTTP 同步路径能触发 ProxySelector 刷新 |

其中，我觉得比较有意义的是关闭异常测试。

测试中放入两个模拟的 `BootstrapServer`，让其中一个在 `shutdown()` 时主动抛出异常，然后检查另一个是否仍然收到关闭调用，以及两个缓存项是否都已移除。

这样验证的不只是正常路径，还包括清理失败时的处理行为。

## 第一次参与之后，我学到了什么？

这次修复的代码改动不算多，但读代码和确定修改范围的过程，比我一开始想的复杂。最初觉得补一个 `refresh()` 就够了，后来才发现，要让这次调用真的起作用，还得跨过几个模块，一直追到缓存和 TCP Server。

对我来说，最大的收获不是多认识了几个类，而是开始找到阅读大型代码库的方法。刚接触 ShenYu 时，很容易觉得要先把整个项目弄懂，才有把握动手。但这次做下来，我发现可以先从一个具体问题开始：找到入口，顺着调用往下看，遇到模块边界时，再确认数据和操作有没有继续传下去。这样一点点缩小范围，比一开始就试图读完整个仓库更容易入手。

另一个感受是，修改已有代码和自己从头写项目不太一样。自己写的时候，很多接口和结构都能按自己的想法来；但在 ShenYu 里，改一个方法之前，还需要看看谁在调用它、哪些类实现了它。比如这次给 Handler 增加刷新入口，我不仅要考虑 TCP 插件怎么用，还要尽量不影响其他已有实现。这让我更具体地理解了“兼容性”为什么重要。

并发问题也是类似的。以前看到 `ConcurrentHashMap`，我更多关注的是这个容器本身是否线程安全。这次把两个线程的执行顺序拆开看，才发现判断和删除之间也会出问题。这个场景让我对“线程安全”有了更具体的认识，而不只是记住一个类的特点。

回头看，我还没有因此就熟悉整个 ShenYu，但至少更清楚该怎么面对一段不熟悉的代码了：不急着改，也不用等到理解所有模块才开始。先把问题相关的那条路径弄清楚，再确认自己的修改会影响哪里。对还在学习的我来说，这就是这次参与开源最实在的收获。

---

## 相关链接

- [Issue #6781](https://github.com/apache/shenyu/issues/6781)
- [PR #6909](https://github.com/apache/shenyu/pull/6909)
- [Apache ShenYu TCP 插件文档](https://shenyu.apache.org/zh/docs/2.7.0/plugin-center/proxy/tcp-plugin/)
