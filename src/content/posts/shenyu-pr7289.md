---
title: '一个 DELETE 为什么改了 31 个文件：Apache ShenYu 删除链路与一次方案澄清'
description: '从 discovery upstream 缓存残留，到第一次面对方案级质疑：记录我如何追查删除链路、对照另一个 PR，并用事件来源和测试讲清 instance 与 selector 的边界。'
pubDate: 2026-10-01T14:50:28+08:00
category: open-source
tags:
  - Apache ShenYu
  - Java
  - 数据同步
  - 缓存一致性
  - Code Review
draft: false
postType: metaOnly
cover: '../../assets/covers/shenyu-pr7289-light.png'
---

刚接下 [Issue #6479](https://github.com/apache/shenyu/issues/6479) 时，我以为自己要补的，只是一次遗漏的缓存删除。

Admin 删除了一个绑定服务发现的 selector，Gateway 侧却还留着它的 discovery upstream 状态。看上去，无非是找到少写的那个 `remove()`，再补一个测试。

但顺着代码往下追，我发现这个“删除”要经过 Admin、同步模块、Subscriber，再交给具体插件。每一层都能收到消息，不代表最后真的有人把状态清掉；不同插件用来找缓存的 key，也不一定是同一个。

最后，[PR #7289](https://github.com/apache/shenyu/pull/7289) 改了 31 个文件。可现在回头看，我最记得的反而不是改动范围，而是后来的一次 Review：维护者认为这条删除链路的设计可能不对，建议重新按快照同步来处理。

那一刻我确实有点慌。我还没有遇到过这种针对整个方案的质疑，第一反应就是：是不是我从一开始就理解错了？后来我重新读另一个 PR、追事件来源，还反复跑了很多遍测试。即使越来越觉得问题出在事件范围的理解上，我也没有马上就敢回应。这篇想记录的，是我怎么一边担心自己漏了什么，一边继续查证，最后才鼓起勇气把自己的判断讲清楚。

## 收到了删除事件，不代表状态真的被清掉了

先说这次要解决的场景。这里的 selector 可以理解为一条选择请求、关联后端服务的配置；discovery upstream 则是它通过服务发现得到的后端实例信息。Admin 侧解绑或删除相关配置后，Gateway 不应该继续保留这份运行时状态。

我一开始只盯着同步入口，后来才把整条调用链连起来看。

在最终对照的代码里，path-based sync 已经能从删除节点的 path 里拿到 `pluginName` 和 `selectorId`，并调用取消订阅。更明确的断点在后面：`CommonDiscoveryUpstreamDataSubscriber#unSubscribe()` 原来只有一行 `//ignore`。

也就是说，删除消息可以传到 Subscriber，却没有继续交给插件清理。HTTP 全量同步还有另一种遗漏：最新快照里不再出现的 selector，也需要被识别出来，而不能只处理这一次还存在的记录。

我这才意识到，排查这类问题不能只问“事件有没有到”。还要继续看：**到了以后，谁负责删？删的是哪一份状态？**

这次沿用了已有的 Subscriber → Handler 分发结构，把 selector 级别的 discovery upstream 删除继续传到拥有状态的插件。没有让同步层去判断“这是 Divide 就删这个，是 gRPC 就删那个”。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; text-align:left; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 1 · 删除消息走到插件，才真正落到状态清理</figcaption>
<div tabindex="0" role="region" aria-label="图 1 · selector 级删除责任链" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg class="shenyu-flow" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="shenyu7289-chain-title shenyu7289-chain-desc" viewBox="0 0 640 516" style="display:block; width:100%; min-width:520px; height:auto; font-family:var(--font-sans); --flow-node:light-dark(#e8f3fc,#142b3e); --flow-condition:light-dark(#f4f9fe,#102333); --flow-ink:light-dark(#235e89,#c0def4); --flow-border:light-dark(#d0e0ed,#355167); --flow-line:light-dark(#8e959d,#8295a6); --flow-success:light-dark(#e5f6eb,#152f26); --flow-success-ink:light-dark(#286447,#a9debf); --flow-success-border:light-dark(#afd3bc,#426c57);">
<title id="shenyu7289-chain-title">selector 级删除责任链</title>
<desc id="shenyu7289-chain-desc">Admin 解绑 selector 级 discovery，发布已有的 DISCOVER_UPSTREAM DELETE。同步模块将资源身份传给 Subscriber，由 Common Subscriber 根据插件名分发给 Handler。Divide 和 WebSocket 清 upstream 缓存，gRPC 清缓存及客户端，TCP 清 upstream 状态并处理 ID 与名称的映射。</desc>
<defs><marker id="shenyu7289-chain-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<g fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu7289-chain-arrow)">
<path d="M320 86 V122"/><path d="M320 192 V228"/><path d="M320 298 V334"/>
<path d="M320 386 V402 Q320 414 308 414 H116 Q106 414 106 424 V438"/>
<path d="M320 414 V438"/><path d="M320 402 Q320 414 332 414 H524 Q534 414 534 424 V438"/>
</g>
<rect x="130" y="18" width="380" height="68" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="320" y="47" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">Admin 解绑 selector 级 discovery</text>
<text x="320" y="71" text-anchor="middle" fill="var(--flow-ink)" font-size="13">发布已有的 DISCOVER_UPSTREAM DELETE</text>
<rect x="130" y="124" width="380" height="68" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="320" y="153" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">同步模块传递删除身份</text>
<text x="320" y="177" text-anchor="middle" fill="var(--flow-ink)" font-size="13">DiscoveryUpstreamKey</text>
<rect x="130" y="230" width="380" height="68" rx="20" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-dasharray="3 4"/>
<text x="320" y="259" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">Subscriber.unSubscribe(key)</text>
<text x="320" y="283" text-anchor="middle" fill="var(--flow-ink)" font-size="13">Common Subscriber 按 pluginName 分发</text>
<rect x="130" y="336" width="380" height="50" rx="18" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="320" y="367" text-anchor="middle" fill="var(--flow-ink)" font-size="15" font-weight="500">Handler.removeDiscoveryUpstreamData(key)</text>
<rect x="14" y="440" width="184" height="62" rx="18" fill="var(--flow-success)" stroke="var(--flow-success-border)"/>
<text x="106" y="466" text-anchor="middle" fill="var(--flow-success-ink)" font-size="14" font-weight="500">Divide / WebSocket</text>
<text x="106" y="488" text-anchor="middle" fill="var(--flow-success-ink)" font-size="12.5">清 upstream 缓存</text>
<rect x="228" y="440" width="184" height="62" rx="18" fill="var(--flow-success)" stroke="var(--flow-success-border)"/>
<text x="320" y="466" text-anchor="middle" fill="var(--flow-success-ink)" font-size="14" font-weight="500">gRPC</text>
<text x="320" y="488" text-anchor="middle" fill="var(--flow-success-ink)" font-size="12.5">清缓存与客户端</text>
<rect x="442" y="440" width="184" height="62" rx="18" fill="var(--flow-success)" stroke="var(--flow-success-border)"/>
<text x="534" y="466" text-anchor="middle" fill="var(--flow-success-ink)" font-size="14" font-weight="500">TCP</text>
<text x="534" y="488" text-anchor="middle" fill="var(--flow-success-ink)" font-size="12.5">清 upstream 与身份映射</text>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">图中是 selector 级 discovery 删除，不是单个实例下线。小屏可在图内左右滑动。</div>
</figure>

Divide、WebSocket 主要清理 `UpstreamCacheManager`；gRPC 还涉及 `ApplicationConfigCache` 和 `GrpcClientCache`；TCP 又有自己的 upstream 状态和名称映射。同步层负责把“谁消失了”传清楚，具体怎么清，还是交给各自的 Handler。

改动范围就是这样一点点变大的。补了接口，就要跟着改调用方和插件实现，再把对应测试补上。我原来以为只要找一个遗漏的删除，最后才发现，得沿着整条责任链把它接起来。

## 删除需要的是身份，不是一份填不全的数据

原来的接口是 `unSubscribe(DiscoverySyncData data)`。可真正删除时，需要的往往只是 `pluginName`、`selectorId`，以及部分插件要用的 `selectorName`。

`DiscoverySyncData` 表达的是一份同步数据。为了删一个资源，却要构造一个很多字段都为空的 DTO，我写着写着就觉得不太顺：到底是在传一份数据，还是只想告诉对方“删掉谁”？

所以这次引入了 `DiscoveryUpstreamKey`，专门表达删除身份：

```java
public record DiscoveryUpstreamKey(
        String pluginName,
        String selectorId,
        String selectorName) {
}
```

这是字段结构的摘录，省略了从同步数据提取 key 的方法。`selectorName` 可以为空，具体 Handler 再根据自己保存的状态解析。

这也让我第一次比较具体地理解了“接口语义”。不只是给类起一个更好听的名字，而是让调用方不用拿“更新内容”来勉强表达“删除身份”。这个方向后来也得到了 Reviewer 的认可。

### TCP 让我多追了一步：收到的 key 和保存的 key 一样吗？

TCP 的问题不在删除方法本身有多复杂，而是同步事件主要带着 `selectorId`，部分 upstream 状态却按 `selectorName` 保存。

拿到 ID，不代表就能找到按名称存的缓存。于是我补了 `selectorId → selectorName` 的映射；删除时先查本地映射，找不到再用 key 里带的名称。

这份映射也不能只等普通 selector event 来建立。Gateway 重启后，discovery upstream 数据可能先恢复，所以 `TcpUpstreamDataHandler` 处理这份数据、确认缓存存在时，也会注册映射。清理 upstream 时，再把对应映射一起移除。

如果我只看 `removeDiscoveryUpstreamData()` 的几行实现，很容易以为删除已经完整了。继续问“这个 key 从哪里来，重启以后还找不找得到”，才会看到另一个问题。

## 同样叫同步，删除信息却不一定长得一样

沿着各条同步路径排查时，我发现不能要求它们都带着一份完整的“删除数据”。节点都已经删了，payload 很可能也不在了。

ZooKeeper 的 `NODE_DELETED` 事件里，`newData` 可以是 `null`，需要从 `oldData` 取得原来的 path。项目里已有这层处理，这次我补了 discovery upstream 的回归测试，确认即使没有新 payload，仍能根据旧节点路径传出正确的删除身份。

path-based sync 可以从 `.../discoveryUpstream/<plugin>/<selectorId>` 的末尾两段恢复身份；node-based sync 则从对应的节点 key 解析。Nacos、etcd、Consul、Polaris、Apollo 也沿用这些共享处理路径，不是每个协议都要再写一套独立的插件清理逻辑。

HTTP 更不同：它拿到的是全量快照，不会为每个消失的 selector 另发一次 DELETE。因此 `DiscoveryUpstreamDataRefresh` 要保存上一份身份快照，再和当前快照比较。

| 快照变化 | 要处理的状态 |
| --- | --- |
| `[S1, S2] → [S2]` | 取消订阅 S1，保留并更新 S2 |
| `[S1] → []` | 取消订阅原来的 S1 |
| 同一 ID，`old-name → new-name` | 先清旧名称对应的状态，再订阅新数据 |

HTTP 比较用的身份包含 namespace、plugin 和 selector ID，不只是一个裸 ID。名称变化也要单独检查，因为 TCP 的旧名称可能仍然对应着旧缓存。

这些情况最后都收敛到 `unSubscribe(DiscoveryUpstreamKey)`。我慢慢理解了：同步协议可以用不同方式告诉我“它不在了”，但到了 Subscriber，删除的对象和责任必须明确。

## 先弄清楚删的是谁，才能讨论该走 UPDATE 还是 DELETE

我原来以为，这个 PR 最费劲的部分会是跨模块修改。后来维护者拿它和 [PR #7172](https://github.com/apache/shenyu/pull/7172) 对照，提出了一个更根本的问题：discovery upstream 应该用完整快照同步，删除一个实例后重新发布剩余列表，为什么还要补一条 DELETE 链路？

这个担心是有道理的。实例从 `[A, B]` 变成 `[B]`，应该发布剩余实例的 UPDATE 快照；最后一个实例没了，也应该是 `UPDATE []`，而不是把整个 selector 当成不存在。

但我当时最难受的，是这不再是“这里少一个判断”或者“补一个测试”。如果判断成立，前面连起来的整条链路都可能需要重新设计。

我第一反应没有去反驳，而是先想：会不会真的是我把删除语义理解错了？可同时又有一点说不上来的疑问：#7172 和 #7289，删的好像不是同一种东西。

于是我没有立刻照着建议改代码，而是重新去找两个事件的生产者。

#7172 讨论的是 selector 内部的实例变化：Registry 的 `ADDED`、`UPDATED`、`DELETED` 先在 Admin 更新数据库，再查询完整剩余列表，发布 `DISCOVER_UPSTREAM UPDATE`。这是我认同的实例级快照模型。

而 #7289 接住的，是项目里**原本就存在的 selector 级 discovery 删除事件**：`SelectorServiceImpl#unbindDiscovery` 调用 `DiscoveryProcessor#removeSelectorUpstream`，发布 `DISCOVER_UPSTREAM DELETE`。这次没有把 Registry 的单实例删除改成 DELETE，也没有替换已有的 `SELECTOR DELETE` 或 `PROXY_SELECTOR DELETE`。

把两个场景放在一起以后，我才有把握说：我们当时讨论的是两个不同的生命周期对象。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; text-align:left; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 2 · 两边都有“删除”，但消失的不是同一种对象</figcaption>
<div tabindex="0" role="region" aria-label="图 2 · instance 与 selector 生命周期对比" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg class="shenyu-flow" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="shenyu7289-scope-title shenyu7289-scope-desc" viewBox="0 0 640 484" style="display:block; width:100%; min-width:560px; height:auto; font-family:var(--font-sans); --flow-node:light-dark(#e8f3fc,#142b3e); --flow-condition:light-dark(#f4f9fe,#102333); --flow-ink:light-dark(#235e89,#c0def4); --flow-border:light-dark(#d0e0ed,#355167); --flow-line:light-dark(#8e959d,#8295a6); --flow-warn:light-dark(#fff3d7,#352918); --flow-warn-ink:light-dark(#8b5b22,#f3ce8d); --flow-warn-border:light-dark(#e8c98e,#80663a); --flow-success:light-dark(#e5f6eb,#152f26); --flow-success-ink:light-dark(#286447,#a9debf); --flow-success-border:light-dark(#afd3bc,#426c57);">
<title id="shenyu7289-scope-title">instance 与 selector 生命周期对比</title>
<desc id="shenyu7289-scope-desc">左侧是 PR 7172 的实例级快照方案：selector S1 仍然存在，实例 A 消失后发布剩余列表 B，最后一个实例消失时发布空列表。右侧是 PR 7289：selector 级 discovery 记录移除，已有 DELETE 事件或 HTTP 快照差异触发取消订阅，清理该记录的运行时状态。</desc>
<defs><marker id="shenyu7289-scope-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<text x="164" y="30" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">#7172 · instance lifecycle</text>
<text x="476" y="30" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">#7289 · selector lifecycle</text>
<g fill="none" stroke="var(--flow-line)" stroke-width="1.2" marker-end="url(#shenyu7289-scope-arrow)">
<path d="M164 120 V158"/><path d="M164 234 V272"/><path d="M164 350 V388"/>
<path d="M476 120 V158"/><path d="M476 234 V272"/><path d="M476 350 V388"/>
</g>
<rect x="26" y="52" width="276" height="68" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="164" y="81" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">S1 还在，实例发生变化</text>
<text x="164" y="105" text-anchor="middle" fill="var(--flow-ink)" font-size="13">[A, B] → [B] / [A] → []</text>
<rect x="338" y="52" width="276" height="68" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="476" y="81" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">S1 的 discovery 记录移除</text>
<text x="476" y="105" text-anchor="middle" fill="var(--flow-ink)" font-size="13">解绑，或从 HTTP 快照中消失</text>
<rect x="26" y="160" width="276" height="74" rx="20" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-dasharray="3 4"/>
<text x="164" y="189" text-anchor="middle" fill="var(--flow-ink)" font-size="15" font-weight="500">Admin 发布完整 UPDATE</text>
<text x="164" y="214" text-anchor="middle" fill="var(--flow-ink)" font-size="13">剩余实例列表可以为空</text>
<rect x="338" y="160" width="276" height="74" rx="20" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-dasharray="3 4"/>
<text x="476" y="189" text-anchor="middle" fill="var(--flow-ink)" font-size="15" font-weight="500">已有 DELETE / HTTP 差异</text>
<text x="476" y="214" text-anchor="middle" fill="var(--flow-ink)" font-size="13">识别被移除的 selector 身份</text>
<rect x="26" y="274" width="276" height="76" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="164" y="304" text-anchor="middle" fill="var(--flow-ink)" font-size="15" font-weight="500">onSubscribe(snapshot)</text>
<text x="164" y="329" text-anchor="middle" fill="var(--flow-ink)" font-size="13">按新快照更新实例状态</text>
<rect x="338" y="274" width="276" height="76" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="476" y="304" text-anchor="middle" fill="var(--flow-ink)" font-size="15" font-weight="500">unSubscribe(key)</text>
<text x="476" y="329" text-anchor="middle" fill="var(--flow-ink)" font-size="13">插件清理这份 discovery 状态</text>
<rect x="26" y="390" width="276" height="64" rx="18" fill="var(--flow-success)" stroke="var(--flow-success-border)"/>
<text x="164" y="417" text-anchor="middle" fill="var(--flow-success-ink)" font-size="15" font-weight="500">有记录，但当前没有实例</text>
<text x="164" y="440" text-anchor="middle" fill="var(--flow-success-ink)" font-size="13">S1: [] 不是 S1 消失</text>
<rect x="338" y="390" width="276" height="64" rx="18" fill="var(--flow-warn)" stroke="var(--flow-warn-border)"/>
<text x="476" y="417" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="15" font-weight="500">当前快照已没有这份记录</text>
<text x="476" y="440" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="13">[S1, S2] → [S2]</text>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">左边是 #7172 的方案模型，不代表该 PR 已合并；两边关注不同层级的状态。</div>
</figure>

最容易混淆的恰好是那个 `[]`。`S1: []` 表示 S1 的 discovery 记录还在，只是没有实例；`[S1] → []` 表示当前 discovery 快照连 S1 这份记录都没有了。外观看起来都是“空了”，后续行为却不能一样。

我也在回复里把边界补清楚：WebSocket 的 MYSELF / REFRESH 重连对账是另一个问题，这个 PR 处理 DELETE，并没有顺便实现一套新的重连 reconciliation 算法。

## 把判断查清楚，才有勇气把话说出来

找到两个生命周期的差别以后，我并没有立刻就有底气去回应。对方比我熟悉项目，而我还是一个学生。我很担心：会不会只是自己读到的那几段代码能对上，放回整个项目里，其实还有我没看到的路径？

所以那次准备答复时，我整理的不只是自己的 diff，还包括另一个 PR、已有的事件生产代码，以及两边的测试。我反复跑了很多遍相关测试，包括 #7172 的 `DiscoveryDataChangedEventSyncListenerTest`、`UpstreamCacheManagerTest`，和 #7289 的 `DiscoveryUpstreamDataRefreshTest`、`DivideUpstreamDataHandlerTest`。跑通以后，还要回头看断言到底在验证什么，和我准备说出的结论是不是同一回事。

我也借助了 DeepSeek、Gemini、GPT 和 GLM，让不同模型一起辅助审查我的理解和方案。我当时很想确认，自己不是因为写了这段代码，就只看到了支持自己判断的部分。多换几个角度检查，至少能让我继续问：还有没有遗漏的边界？有没有哪一步是我想当然了？

模型的分析帮我多检查了几遍，但真正让我慢慢敢回应的，还是能回到代码里找到事件来源，能把测试结果和具体场景对上。我需要的不只是一个“你的理解没问题”的回答，而是自己也能解释清楚：为什么这里是 selector 级删除，为什么它没有改变实例级 UPDATE 的路径。

我把这些重新整理成几个可以逐项核对的判断：

| 我需要说明的边界 | 对应的证据 |
| --- | --- |
| 单个实例删除仍然走 UPDATE | Registry 事件的生产路径，以及 #7172 的实例快照测试 |
| selector 级 DELETE 不是这次新造的事件 | `unbindDiscovery → removeSelectorUpstream` 的已有调用链 |
| HTTP 能识别消失的 discovery 记录 | #7289 的 `[S1, S2] → [S2]`、`[S1] → []` 测试 |
| 取消订阅确实落到了插件状态 | 对应 Handler 的缓存清理测试 |

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; text-align:left; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 3 · 不是先决定谁对，而是先把判断查清楚</figcaption>
<div tabindex="0" role="region" aria-label="图 3 · 方案质疑后的查证与回应" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg class="shenyu-flow" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="shenyu7289-review-title shenyu7289-review-desc" viewBox="0 0 640 440" style="display:block; width:100%; min-width:520px; height:auto; font-family:var(--font-sans); --flow-node:light-dark(#e8f3fc,#142b3e); --flow-condition:light-dark(#f4f9fe,#102333); --flow-ink:light-dark(#235e89,#c0def4); --flow-border:light-dark(#d0e0ed,#355167); --flow-line:light-dark(#8e959d,#8295a6); --flow-success:light-dark(#e5f6eb,#152f26); --flow-success-ink:light-dark(#286447,#a9debf); --flow-success-border:light-dark(#afd3bc,#426c57);">
<title id="shenyu7289-review-title">方案质疑后的查证与回应</title>
<desc id="shenyu7289-review-desc">遇到方案级质疑，先重新追事件来源、对照相关 PR 和测试。发现实现确实有问题就修改并补验证，发现上下文理解不同就说明对象和边界。两种回应都要给出可复核的证据，再继续共同评审。</desc>
<defs><marker id="shenyu7289-review-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<g fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round">
<path d="M320 76 V110" marker-end="url(#shenyu7289-review-arrow)"/>
<path d="M320 178 V194 Q320 206 308 206 H174 Q162 206 162 218 V248" marker-end="url(#shenyu7289-review-arrow)"/>
<path d="M320 194 Q320 206 332 206 H466 Q478 206 478 218 V248" marker-end="url(#shenyu7289-review-arrow)"/>
<path d="M162 312 V330 Q162 342 174 342 H466 Q478 342 478 330 V312"/>
<path d="M320 342 V374" marker-end="url(#shenyu7289-review-arrow)"/>
</g>
<rect x="140" y="18" width="360" height="58" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="320" y="53" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">Reviewer 对方案提出疑问</text>
<rect x="140" y="112" width="360" height="66" rx="20" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-dasharray="3 4"/>
<text x="320" y="140" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">先重新验证自己的判断</text>
<text x="320" y="164" text-anchor="middle" fill="var(--flow-ink)" font-size="13">事件来源 / 相关 PR / 调用链 / 测试</text>
<rect x="24" y="250" width="276" height="62" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="162" y="276" text-anchor="middle" fill="var(--flow-ink)" font-size="15" font-weight="500">实现确实有问题</text>
<text x="162" y="299" text-anchor="middle" fill="var(--flow-ink)" font-size="13">修改，并补对应验证</text>
<rect x="340" y="250" width="276" height="62" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="478" y="276" text-anchor="middle" fill="var(--flow-ink)" font-size="15" font-weight="500">讨论的上下文不同</text>
<text x="478" y="299" text-anchor="middle" fill="var(--flow-ink)" font-size="13">说明对象、语义和边界</text>
<rect x="140" y="376" width="360" height="50" rx="18" fill="var(--flow-success)" stroke="var(--flow-success-border)"/>
<text x="320" y="407" text-anchor="middle" fill="var(--flow-success-ink)" font-size="15" font-weight="500">给出可复核的证据，继续共同评审</text>
</svg>
</div>
</figure>

准备这些证据，不只是为了让别人更容易复核，也是为了让我自己敢把话说出来。如果只是凭感觉说“这两个 PR 不一样”，我会很不踏实；把调用链和测试放在一起以后，我才觉得自己可以认真解释这个区别。

即便如此，回应时我还是很小心。我不想让讨论变成一句“你理解错了”，也担心自己表达不好，让对方觉得我只是舍不得改已经写好的代码。所以我先说明自己认同实例级完整快照的模型，再解释 #7289 处理的是另一层的删除，把依据和没有覆盖的范围一起写清楚，也同步澄清了 PR 描述。

真正把回复发出去时，我还是有点紧张。只是反复核对之后，我觉得不能一直停在“可能是我错了”这里。如果我查到的事实确实支持这个判断，就应该鼓起勇气说出来，也让别人有机会继续检查它。

后来维护者在[后续回复](https://github.com/apache/shenyu/pull/7289#issuecomment-5886721417)里确认，之前对事件范围有误解：instance 变化走完整 UPDATE 快照，#7289 处理的是 selector-scoped DELETE。他会按这个区分重新看 PR。

看到那条回复时，我确实松了一口气。前面一直担心自己是不是漏了什么，也担心这次回应会不会显得不够谨慎。对方愿意按澄清后的边界重新看 PR，让我觉得这番反复查证和认真组织的解释没有白费，原来卡住的讨论终于能继续了。

## 失败怎么被看见，也是方案的一部分

这次 Review 不只有事件范围的争议。有两个工程取舍，也让我记得很清楚。

### 批量删除可以失败，但不能让用户不知道发生了什么

Admin 发布删除事件前，需要解析出 `pluginName`。名字缺失时，不能继续构造一个地址不完整的 discovery upstream 路径。

我最开始选择直接抛 `IllegalStateException`。Reviewer 指出，一个 selector 的元数据异常，会让整个批次回滚；如果最后只给用户一个内部异常，他既不知道哪些数据动过，也不知道怎么重试。

讨论里有两种选择：跳过异常 selector，继续处理其他项；或者保留批次原子性，但用能映射到清晰错误响应的异常说明失败。

我最后选了第二种。先校验整个批次，再删除关联数据、发布事件；如果插件名经过补充查询仍无法解析，就抛 `ShenyuAdminException`，指出有问题的 selector，并说明本批次没有任何 selector 被删除，需要恢复插件名后再试。

以前我很容易觉得“加了异常，安全性就有了”。这次我开始意识到，还要站在使用者那边看一眼：**他看完这个错误，知不知道数据现在是什么状态，下一步该做什么？**

### 接口更清楚，不代表兼容性成本就消失了

`unSubscribe(DiscoverySyncData)` 改成 `unSubscribe(DiscoveryUpstreamKey)`，语义确实更准确。但这是公共 SPI，不是只在一个类里改个私有方法。

仓库内部实现和调用点全部迁移，不能代表下游实现也能直接继续用。这次修改有源代码和二进制兼容性影响，最后明确写进了 `RELEASE-NOTES.md`。

我保留了这个接口选择，但也需要承认它的代价。方案不能只解释“为什么这样更好”，还要说明“别人要为这个变化做什么”。

## CI 红灯，又把我带到了另一个问题

维护 #7289 的过程中，我还需要跟进 master、处理冲突和检查 CI。跨模块改动不能只靠自己读一遍代码就放心，Reviewer 也需要能检查的验证结果。

后来 `k8s-examples-http` 的安装步骤失败，我没有重跑权限，就继续往 workflow 里查。最后发现，`curl -sfL ... | sh -` 的下载失败可能被 pipeline 的退出状态掩盖，写好的重试并没有接住失败。

我把那个问题拆成了 [Issue #7379](https://github.com/apache/shenyu/issues/7379) 和 [PR #7380](https://github.com/apache/shenyu/pull/7380)，没有把无关的 CI 修复都塞进 discovery 删除的 diff。

那段经历已经写在[《CI 红了，不一定是代码错了》](/zh-cn/posts/shenyu-pr7380/)里。对我来说，它不是完全独立的另一件事，而是维护这个 PR 时，从“怎么又红了”一路追出来的。

## 把方案交出去，也要把上下文讲清楚

这个 PR 之后，我对“把一个改动做好”的理解，多了一点以前没有认真想过的东西。原来我更多盯着自己的代码：问题有没有修掉，测试能不能过，Review 提到的地方有没有改完。后来才发现，把代码写出来以后，还要让别人能理解，我为什么选择这样处理。

这次争议也让我回头看了自己的表达。我顺着代码追了很久，已经习惯把“实例删除”和“selector 级 discovery 删除”分开理解，写说明时却容易默认读者也有同样的上下文。维护者从另一个 PR 的快照模型看过来，关注的就可能是另一种删除。光把调用链列出来，并不一定能让这个区别变得明显。

以后再介绍一个方案，我想先把场景说清楚：这次消失的是什么，哪些状态还在，我的修改负责到哪一步。不是一上来就解释新增了什么接口，而是先让读者知道，为什么这里需要这个接口。以前我觉得这些是写完代码以后的说明，现在觉得，它们本来就是把一个 PR 交出去的一部分。

我对 Review 的感觉也变了一点。以前有点像等人批改作业：对方指出问题，我就想着赶紧改好，别给别人添麻烦。这次讨论让我发现，我也需要把自己掌握的上下文带进去。有人帮我看到没想周全的地方，我也可以补上对方暂时没有看到的部分，最后一起判断这个改动该怎么往前走。

我还是会担心自己经验不够，也不会因为这一次解释清楚了，就觉得以后都能判断准确。但至少，参与讨论不一定要等到自己已经很懂整个项目。对自己说出的判断认真负责，把知道的讲清楚，把不确定的留出来，也是我现在能做的一件事。

回头看，这次让我多了一点信心的，不是“我也能指出维护者的误解”，而是我开始觉得，自己可以认真参与一次技术讨论。还会紧张，还会怕漏掉什么，但不再只把自己放在等着接受修改意见的位置上。这是我想从这次经历里留下来的变化。

## 相关链接

- [Issue #6479 · discovery upstream 缓存残留](https://github.com/apache/shenyu/issues/6479)
- [PR #7289 · selector 级 discovery upstream 删除处理](https://github.com/apache/shenyu/pull/7289)
- [PR #7172 · 实例级完整快照对账方案](https://github.com/apache/shenyu/pull/7172)
- [关于事件范围的澄清答复](https://github.com/apache/shenyu/pull/7289#issuecomment-5885571487)
- [维护者对事件范围的后续确认](https://github.com/apache/shenyu/pull/7289#issuecomment-5886721417)
- [CI 排查复盘](/zh-cn/posts/shenyu-pr7380/)
