---
title: '当“没有实例”也是一次更新：Apache ShenYu ZooKeeper 缓存残留修复'
description: '维护另一个 PR 的间隙，我遇到了一个很小的缓存问题。顺着空列表往下看，才发现“没有实例”和“没有更新”其实是两回事。'
pubDate: 2026-10-01T02:54:10+08:00
tags:
  - Apache ShenYu
  - Java
  - ZooKeeper
  - Watcher
  - 缓存一致性
draft: false
postType: metaOnly
---

当时我正在维护另一个 ShenYu PR [#7289](https://github.com/apache/shenyu/pull/7289)。维护者让我处理 merge conflicts，在等待和重新跑测试的间隙，我又翻了一下项目里的 Issue，看到了 [#6526](https://github.com/apache/shenyu/issues/6526)。

问题第一眼看起来很简单：ZooKeeper Watcher 收到空的子节点列表时，没有更新本地缓存。最后一个实例已经删掉了，再查一次，返回的却还是旧实例。

和之前的 TCP 问题相比，这次没有复杂的并发设计，也不用沿着很多模块找调用链。最后的生产代码修改，确实只是去掉一个判断。但看进去以后，我觉得它有一个很值得记下来的地方：**空列表是在说“没有数据需要处理”，还是在说“最新状态就是没有数据”？**

这个区别想清楚以后，修改就不难了。修复最终通过 [PR #7372](https://github.com/apache/shenyu/pull/7372) 合并。下面想记录的，是我怎么理解这个空状态，以及为什么测试没有停在“删干净了”这一步。

## 最后一个实例被删了，缓存为什么还在？

`ZookeeperInstanceRegisterRepository.selectInstances()` 会读取 ZooKeeper 中的实例节点，把结果保存在 `watcherInstanceRegisterMap` 里，并注册一个 Watcher 来监听后续变化。

假设 `service-a` 下原来有两个实例。删除其中一个以后，Watcher 重新读取子节点列表，用剩下的实例更新缓存，这时一切正常。真正出问题的是再把**最后一个实例**删掉：ZooKeeper 返回 `[]`，缓存却没有跟着变空。

原来的 Watcher 回调里，有这样一段逻辑：

```java
// 原有回调中的关键片段
List<String> childrenList = StringUtils.isNotBlank(path)
        ? client.subscribeChildrenChanges(path, this)
        : Collections.emptyList();

if (!childrenList.isEmpty()) {
    watcherInstanceRegisterMap.put(
            selectKey,
            getInstanceRegisterFun.apply(childrenList)
    );
}
```

只要列表为空，就跳过更新。于是 ZooKeeper 已经没有实例，本地缓存里却还留着最后一个实例；后续查询命中缓存，读到的自然还是旧结果。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 1 · 同一次空列表通知，修复前后留下了不同的缓存</figcaption>
<div tabindex="0" role="region" aria-label="图 1 · 空列表更新的修复前后对比" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg class="shenyu-flow" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="shenyu7372-stale-title shenyu7372-stale-desc" viewBox="0 0 640 384" style="display:block; width:100%; min-width:520px; height:auto; font-family:var(--font-sans); --flow-node:light-dark(#e8f3fc,#142b3e); --flow-condition:light-dark(#f4f9fe,#102333); --flow-ink:light-dark(#235e89,#c0def4); --flow-border:light-dark(#d0e0ed,#355167); --flow-line:light-dark(#8e959d,#8295a6); --flow-warn:light-dark(#fff3d7,#352918); --flow-warn-ink:light-dark(#8b5b22,#f3ce8d); --flow-warn-border:light-dark(#e8c98e,#80663a); --flow-success:light-dark(#e5f6eb,#152f26); --flow-success-ink:light-dark(#286447,#a9debf); --flow-success-border:light-dark(#afd3bc,#426c57);">
<title id="shenyu7372-stale-title">空列表更新的修复前后对比</title>
<desc id="shenyu7372-stale-desc">最后一个实例删除后，Watcher 读到空列表。修复前跳过更新，缓存仍为实例 A；修复后保存空快照，缓存为空列表。</desc>
<defs><marker id="shenyu7372-stale-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<path d="M320 86 V108 Q320 122 306 122 H174 Q160 122 160 136 V172 M320 108 Q320 122 334 122 H466 Q480 122 480 136 V172 M160 230 V268 M480 230 V268" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu7372-stale-arrow)"/>
<rect x="150" y="18" width="340" height="68" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)" stroke-width="1.2"/>
<text x="320" y="47" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">最后一个实例被删除</text>
<text x="320" y="72" text-anchor="middle" fill="var(--flow-ink)" font-size="13">Watcher 读到 children = []</text>
<rect x="123" y="135" width="74" height="26" rx="13" fill="var(--flow-condition)" stroke="var(--flow-border)"/>
<text x="160" y="153" text-anchor="middle" fill="var(--flow-ink)" font-size="13">修复前</text>
<rect x="443" y="135" width="74" height="26" rx="13" fill="var(--flow-condition)" stroke="var(--flow-border)"/>
<text x="480" y="153" text-anchor="middle" fill="var(--flow-ink)" font-size="13">修复后</text>
<rect x="30" y="174" width="260" height="56" rx="18" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-dasharray="3 4"/>
<text x="160" y="208" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">因为为空，跳过更新</text>
<rect x="350" y="174" width="260" height="56" rx="18" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="480" y="208" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">把空列表也写入缓存</text>
<rect x="30" y="270" width="260" height="82" rx="20" fill="var(--flow-warn)" stroke="var(--flow-warn-border)"/>
<text x="160" y="303" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="16" font-weight="500">Cache: [A]</text>
<text x="160" y="329" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="13">仍然返回已经不存在的实例</text>
<rect x="350" y="270" width="260" height="82" rx="20" fill="var(--flow-success)" stroke="var(--flow-success-border)"/>
<text x="480" y="303" text-anchor="middle" fill="var(--flow-success-ink)" font-size="16" font-weight="500">Cache: []</text>
<text x="480" y="329" text-anchor="middle" fill="var(--flow-success-ink)" font-size="13">与 ZooKeeper 当前状态一致</text>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">A 表示之前缓存的实例。小屏可在图内左右滑动查看。</div>
</figure>

第一次看 `if (!childrenList.isEmpty())` 时，“有数据才更新”其实很容易让人觉得合理。但这里接收的是当前子节点列表，不是一批只需要追加的数据。Watcher 已经告诉我们最新结果是空，这本身就是一次更新。

我后来意识到，问题并不是没收到通知，而是**收到了通知，却因为结果为空，把这次状态变化忽略了**。

## 为什么保存空列表，而不是删掉缓存？

最直接的修复，就是去掉非空判断，让每一次读取到的列表都能更新缓存：

```java
// 修复后的缓存更新，childrenList 也可以是空列表
watcherInstanceRegisterMap.put(
        selectKey,
        getInstanceRegisterFun.apply(childrenList)
);
```

`getInstanceRegisterFun` 会把子节点转换成实例列表。输入为空时，得到的也是空列表，因此缓存中会保留 `service-a -> []`。

看到这里，也很容易想到另一种做法：既然已经没有实例了，直接 `remove(selectKey)` 不就行了吗？我继续看了 `selectInstances()` 读取缓存的部分：

```java
final List<InstanceEntity> cachedInstances =
        watcherInstanceRegisterMap.get(selectKey);

if (Objects.nonNull(cachedInstances)) {
    return cachedInstances;
}
```

它判断的是有没有缓存结果，而不是结果里有没有实例。`[]` 是一个有效的命中，下一次查询可以直接返回；如果把整个 entry 删掉，查询就会走到后面的订阅和初始化流程。

这时我才把两件事分开：**没有实例，不代表没有缓存结果。** 我们已经知道这个服务当前没有实例，没必要仅仅因为数量是零，就把它当作一次缓存未命中。

| 这里读到的结果 | 在这段逻辑中的含义 | 后续处理 |
| --- | --- | --- |
| 缓存为非空列表 | 已有当前实例快照 | 直接返回缓存 |
| 缓存为 `[]` | 已有快照，当前没有实例 | 同样直接返回缓存 |
| Map 查询返回 `null` | 没有这个 key 的缓存结果 | 进入订阅和初始化流程 |

在这段代码里，`null` 是没查到缓存，`[]` 是查到了一个空结果。两者的后续处理不同，不能因为“都没有实例”就混在一起。

## 缓存变空以后，还能继续更新吗？

接着我又想到一个问题：如果 `selectInstances()` 以后都直接返回缓存里的 `[]`，那服务重新注册实例的时候，怎么知道它又有数据了？

关键是，**查询命中空缓存，不等于 Watcher 停止工作**。

Watcher 回调仍然会调用 `client.subscribeChildrenChanges(path, this)`，重新读取子节点并续订监听。之后有新实例出现，回调再把新的实例列表写入同一个缓存 entry。空列表只是这段变化中的一个正常快照，不是终点。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 2 · 查询读快照，Watcher 负责让快照继续变化</figcaption>
<div tabindex="0" role="region" aria-label="图 2 · 缓存读取与 Watcher 更新的两条路径" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg class="shenyu-flow" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="shenyu7372-watch-title shenyu7372-watch-desc" viewBox="0 0 640 490" style="display:block; width:100%; min-width:520px; height:auto; font-family:var(--font-sans); --flow-node:light-dark(#e8f3fc,#142b3e); --flow-condition:light-dark(#f4f9fe,#102333); --flow-ink:light-dark(#235e89,#c0def4); --flow-border:light-dark(#d0e0ed,#355167); --flow-line:light-dark(#8e959d,#8295a6); --flow-success:light-dark(#e5f6eb,#152f26); --flow-success-ink:light-dark(#286447,#a9debf); --flow-success-border:light-dark(#afd3bc,#426c57);">
<title id="shenyu7372-watch-title">缓存读取与 Watcher 更新的两条路径</title>
<desc id="shenyu7372-watch-desc">监听已经建立且缓存存在时，查询直接返回快照，包括空列表。子节点发生变化后，Watcher 重新读取并续订，再把新快照写入缓存。查询命中空列表不会终止监听。</desc>
<defs><marker id="shenyu7372-watch-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<path d="M160 100 V138 M160 204 V354 M480 100 V138 M480 214 V252 M480 318 V354" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" marker-end="url(#shenyu7372-watch-arrow)"/>
<path d="M480 414 V443 Q480 457 494 457 H613 Q626 457 626 443 V85 Q626 71 612 71 H602" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-dasharray="4 5" stroke-linejoin="round" marker-end="url(#shenyu7372-watch-arrow)"/>
<text x="160" y="25" text-anchor="middle" fill="var(--flow-ink)" font-size="13" opacity=".8">查询路径 · 已命中缓存</text>
<text x="480" y="25" text-anchor="middle" fill="var(--flow-ink)" font-size="13" opacity=".8">更新路径 · 监听已建立</text>
<rect x="40" y="42" width="240" height="58" rx="18" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="160" y="77" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">selectInstances(key)</text>
<rect x="360" y="42" width="240" height="58" rx="18" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="480" y="77" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">子节点发生变化</text>
<rect x="30" y="140" width="260" height="64" rx="18" fill="var(--flow-condition)" stroke="var(--flow-border)"/>
<text x="160" y="168" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">读取已有缓存快照</text>
<text x="160" y="191" text-anchor="middle" fill="var(--flow-ink)" font-size="13">[] 也是有效命中</text>
<rect x="350" y="140" width="260" height="74" rx="18" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="480" y="171" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">Watcher 回调</text>
<text x="480" y="196" text-anchor="middle" fill="var(--flow-ink)" font-size="13">重新读取子节点，并续订监听</text>
<rect x="350" y="254" width="260" height="64" rx="18" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="480" y="282" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">转换后写入缓存</text>
<text x="480" y="305" text-anchor="middle" fill="var(--flow-ink)" font-size="13">无论列表里有没有实例</text>
<rect x="30" y="356" width="260" height="58" rx="18" fill="var(--flow-success)" stroke="var(--flow-success-border)"/>
<text x="160" y="391" text-anchor="middle" fill="var(--flow-success-ink)" font-size="16" font-weight="500">直接返回，不重新初始化</text>
<rect x="350" y="356" width="260" height="58" rx="18" fill="var(--flow-success)" stroke="var(--flow-success-border)"/>
<text x="480" y="391" text-anchor="middle" fill="var(--flow-success-ink)" font-size="16" font-weight="500">Cache 保存最新快照</text>
<text x="455" y="448" text-anchor="end" fill="var(--flow-ink)" font-size="12.5" opacity=".8">后续变化仍由 Watcher 处理</text>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">示意监听正常建立后的读写路径，省略缓存未命中与异常处理分支。</div>
</figure>

所以这里不是“把缓存清空以后就不管了”，而是继续用同一套 Watcher 更新当前快照。把读取路径和更新路径放在一起看，这个选择就更容易理解了。

## 测试为什么没有停在“已经变空”？

这次我觉得测试比生产代码的修改更值得展开一点。原来的测试主要检查有实例时能正常读取，我把它补成了 `1 → 0 → 1`：先有一个实例，删除最后一个，再让实例重新出现。

测试用一个简单状态变量控制模拟的 ZooKeeper 返回值：

```java
final boolean[] hasInstance = {true};

// 根据当前模拟状态，返回一个子节点或空列表
when(mock.subscribeChildrenChanges(anyString(), any(CuratorWatcher.class)))
        .thenAnswer(invocation -> {
            watcherArr[0] = (CuratorWatcher) invocation.getArguments()[1];
            return hasInstance[0]
                    ? Collections.singletonList("shenyu-test")
                    : Collections.emptyList();
        });
```

接着，主动触发捕获到的 Watcher 回调，检查每一次状态变化后的查询结果：

```java
// 测试中的关键步骤，省略 repository 和 mockEvent 的初始化
assertEquals(1, repository.selectInstances(selectKey).size());

hasInstance[0] = false;
watcherArr[0].process(mockEvent);
assertTrue(repository.selectInstances(selectKey).isEmpty());

hasInstance[0] = true;
watcherArr[0].process(mockEvent);
assertEquals(1, repository.selectInstances(selectKey).size());
```

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 3 · 1 → 0 → 1：变空以后，缓存还能跟着下一次变化恢复</figcaption>
<div tabindex="0" role="region" aria-label="图 3 · 实例与缓存的一到零再到一状态变化" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg class="shenyu-flow" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="shenyu7372-cycle-title shenyu7372-cycle-desc" viewBox="0 0 640 336" style="display:block; width:100%; min-width:520px; height:auto; font-family:var(--font-sans); --flow-node:light-dark(#e8f3fc,#142b3e); --flow-condition:light-dark(#f4f9fe,#102333); --flow-ink:light-dark(#235e89,#c0def4); --flow-border:light-dark(#d0e0ed,#355167); --flow-line:light-dark(#8e959d,#8295a6); --flow-success:light-dark(#e5f6eb,#152f26); --flow-success-ink:light-dark(#286447,#a9debf); --flow-success-border:light-dark(#afd3bc,#426c57);">
<title id="shenyu7372-cycle-title">实例与缓存的一到零再到一状态变化</title>
<desc id="shenyu7372-cycle-desc">三个阶段依次为存在一个实例 A、删除后为空、实例 A 重新出现。初始查询与后两次 Watcher 回调，使缓存分别保存 A、空列表、A。空列表是中间快照，并不阻断后续更新。</desc>
<defs><marker id="shenyu7372-cycle-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<path d="M186 91 H238 M402 91 H454 M186 241 H238 M402 241 H454 M104 124 V206 M320 124 V206 M536 124 V206" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" marker-end="url(#shenyu7372-cycle-arrow)"/>
<text x="104" y="27" text-anchor="middle" fill="var(--flow-ink)" font-size="14">有一个实例</text>
<text x="320" y="27" text-anchor="middle" fill="var(--flow-ink)" font-size="14">删除最后一个</text>
<text x="536" y="27" text-anchor="middle" fill="var(--flow-ink)" font-size="14">实例重新出现</text>
<rect x="22" y="58" width="164" height="66" rx="18" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="104" y="83" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5" opacity=".8">ZooKeeper</text>
<text x="104" y="109" text-anchor="middle" fill="var(--flow-ink)" font-size="18" font-weight="500">[A]</text>
<rect x="238" y="58" width="164" height="66" rx="18" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-dasharray="3 4"/>
<text x="320" y="83" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5" opacity=".8">ZooKeeper</text>
<text x="320" y="109" text-anchor="middle" fill="var(--flow-ink)" font-size="18" font-weight="500">[]</text>
<rect x="454" y="58" width="164" height="66" rx="18" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="536" y="83" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5" opacity=".8">ZooKeeper</text>
<text x="536" y="109" text-anchor="middle" fill="var(--flow-ink)" font-size="18" font-weight="500">[A]</text>
<rect x="51" y="151" width="106" height="26" rx="13" fill="var(--flow-condition)" stroke="var(--flow-border)"/>
<text x="104" y="169" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5">初始查询</text>
<rect x="265" y="151" width="110" height="26" rx="13" fill="var(--flow-condition)" stroke="var(--flow-border)"/>
<text x="320" y="169" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5">Watcher 回调</text>
<rect x="481" y="151" width="110" height="26" rx="13" fill="var(--flow-condition)" stroke="var(--flow-border)"/>
<text x="536" y="169" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5">Watcher 回调</text>
<rect x="22" y="208" width="164" height="66" rx="18" fill="var(--flow-success)" stroke="var(--flow-success-border)"/>
<text x="104" y="233" text-anchor="middle" fill="var(--flow-success-ink)" font-size="12.5" opacity=".8">Cache</text>
<text x="104" y="259" text-anchor="middle" fill="var(--flow-success-ink)" font-size="18" font-weight="500">[A]</text>
<rect x="238" y="208" width="164" height="66" rx="18" fill="var(--flow-success)" stroke="var(--flow-success-border)"/>
<text x="320" y="233" text-anchor="middle" fill="var(--flow-success-ink)" font-size="12.5" opacity=".8">Cache</text>
<text x="320" y="259" text-anchor="middle" fill="var(--flow-success-ink)" font-size="18" font-weight="500">[]</text>
<rect x="454" y="208" width="164" height="66" rx="18" fill="var(--flow-success)" stroke="var(--flow-success-border)"/>
<text x="536" y="233" text-anchor="middle" fill="var(--flow-success-ink)" font-size="12.5" opacity=".8">Cache</text>
<text x="536" y="259" text-anchor="middle" fill="var(--flow-success-ink)" font-size="18" font-weight="500">[A]</text>
<text x="320" y="310" text-anchor="middle" fill="var(--flow-ink)" font-size="14">空列表是正常快照，不是监听的终点</text>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">对应这次单元测试的状态序列；A 是模拟返回的同一个实例。</div>
</figure>

如果测试只停在中间一步，能检查旧实例有没有残留，但看不到后续变化还能不能生效。再往后走一步，就把“从有到无”和“从无到有”连起来了。

PR 里还记录了一个对我很有帮助的检查：先加上空列表的断言，它在旧代码下失败；去掉判断以后，再运行通过。这样能确认，新测试确实抓住了这次修复的问题，而不只是给测试多加了几行代码。

## 和之前的空快照问题，原来有同一个盲点

做这个 Issue 时，我想起了[第一次处理的 HTTP 空快照问题](/zh-cn/posts/shenyu-pr6909)。那次是收到空的 ProxySelector 快照以后，刷新链路没有把旧的 TCP Server 清理掉；这次是 ZooKeeper 返回空子节点列表以后，旧实例缓存没有被覆盖。

模块不同，后果也不同，但我在两次排查里碰到了一个相似的盲点：看到列表为空，很容易顺手把它理解成“这次没东西需要做”。

但对这些全量快照来说，空数据可能恰恰在说：**之前存在的东西，现在已经全部没有了。** 继续保留旧状态，反而和这次更新的含义相反。

我以前更习惯关注“数据来了以后怎么处理”，这两次之后，开始会多问一句：数据从有变成没有的时候，代码会走哪条分支？旧状态会不会还留在那里？

## 改动很小，但我想记下的不只是那两行代码

和前两个 PR 相比，这次修复简单很多。最后也没有做什么很大的改造，就是删掉一个非空判断，补上状态变化的测试。

不过我并不觉得它只能写成一句“修复缓存残留”。对我来说，这次有意思的地方，是沿着一个看起来很合理的判断往下读，发现它其实混淆了两种状态：没有缓存结果，和已经知道结果为空。

也让我对测试有了一点新的想法。除了检查某个时刻返回什么，还可以把前后变化连起来看：先有数据，后来没有，再后来又有。很多问题正好藏在这些过渡里，而不是某一个静态结果里。

这次记下的东西很简单：**“没有实例”不是“没有状态”，它本身就是当前状态。** 以后再遇到 Watcher、全量同步或者快照式缓存，我想自己会更留意那个容易被直接跳过的空列表。

## 相关链接

- [Issue #6526 · 最后一个子节点删除后，ZooKeeper 实例缓存仍有旧数据](https://github.com/apache/shenyu/issues/6526)
- [PR #7372 · 更新空子节点列表对应的实例缓存](https://github.com/apache/shenyu/pull/7372)
- [合并版本中的实现](https://github.com/apache/shenyu/blob/1cadb4b09d7cdff47f233ff72d7ff29da1cbef75/shenyu-registry/shenyu-registry-zookeeper/src/main/java/org/apache/shenyu/registry/zookeeper/ZookeeperInstanceRegisterRepository.java)
- [这次补充的 Watcher 测试](https://github.com/apache/shenyu/blob/1cadb4b09d7cdff47f233ff72d7ff29da1cbef75/shenyu-registry/shenyu-registry-zookeeper/src/test/java/org/apache/shenyu/registry/zookeeper/ZookeeperInstanceRegisterRepositoryTest.java)
- [PR #7289 · 当时正在维护的 discovery 缓存删除修复](https://github.com/apache/shenyu/pull/7289)
