---
title: '删掉 418 行之前，我先确认了什么：Apache ShenYu 废弃锁清理'
description: '一套锁实现已经标记 Deprecated，Spring 却还在创建它。沿着 Bean、实际注册入口和现有锁机制查下去，我才确认这次该做的是清理，而不是迁移。'
pubDate: 2026-10-08T17:36:56+08:00
category: open-source
tags: [Apache ShenYu, Java, Spring Integration, LockRegistry, 代码清理]
draft: false
postType: metaOnly
---

这次 ShenYu PR，最后没有新增一行代码，只删掉了 418 行。和之前沿着同步链路排查 Bug 不同，这次面对的是一套已经标记 `@Deprecated` 的注册锁实现。

但真正让我停下来的，是一个看起来矛盾的地方：类上已经写着废弃，Spring 配置里却还留着创建它的 Bean。它到底只是历史遗留，还是仍然在某条业务路径上保护着并发注册？

我不敢只凭一个注解就删掉它。毕竟这里不只是几个工具方法，还涉及事务、数据库行锁和线程里的事务状态。于是，这次的大部分工作都发生在按下删除之前：查消费者，追当前注册入口，再把旁边仍然在用的锁机制区分开。

最后确认下来，这次需要做的不是迁移锁逻辑，而是把已经退出仓库内业务调用链的旧实现清理干净。下面记录的是，我怎么走到这个判断。

## 标记废弃，不等于已经退出调用链

[Issue #6606](https://github.com/apache/shenyu/issues/6606) 指向 `shenyu-admin.lock` 下的五个旧类型：

- `RegisterExecutionLock`
- `RegisterExecutionRepository`
- `ForUpdateBackedRegisterExecutionLock`
- `PlatformTransactionRegisterExecutionRepository`
- `RegisterTransactionUtil`

这些类型都已经标记 `@Deprecated`。其中的接口和实现还在 Javadoc 中指向 `JdbcLockRegistry#obtain` 或 `DefaultLockRepository`，提示使用替代方案。

与此同时，`RegisterCenterConfiguration` 里仍然有一个 `registerExecutionRepository(...)` Bean，用来创建旧的 `PlatformTransactionRegisterExecutionRepository`。

这时候其实有两个方向。如果业务还在使用它，就需要先处理迁移，不能直接删除；如果业务已经不走这里，留下来的才是旧 Bean 和旧实现。**`@Deprecated` 能告诉我它不再被推荐使用，却不能替我回答现在有没有人在用。**

而这套实现也不是空壳。旧的 `ForUpdateBackedRegisterExecutionLock` 会开启事务、设置超时，通过 `RegisterTransactionUtil` 把事务状态放进 `ThreadLocal`，再调用 `pluginMapper.selectByNameForUpdate(...)` 获取数据库行锁。解锁时，按事务状态提交或回滚，最后清掉线程中的状态。

越往里看，越觉得不能凭“看起来很旧”做判断。我需要查的是这套职责还有没有消费者，而不是它的实现写得完整不完整。

## Bean 还在创建，业务却已经走了另一条路

我先把“Spring 会创建这个 Bean”和“业务会使用这个 Bean”分开查。

沿着旧类型和配置查引用后，没有找到仓库内的生产代码消费者。剩下的是旧实现之间的引用、创建 Bean 的配置，以及专门测试这套实现的两个测试文件。注册服务已经不再依赖它。

不过，确认旧接口没有消费者，只回答了一半问题。我还需要知道：**当前 context-path 注册路径，由谁来负责加锁？**

继续追到 `AbstractContextPathRegisterService.registerContextPath(...)`，可以看到它注入的是 Spring Integration 的 `LockRegistry`。方法先根据 context-path 构造 key，通过 `registry.obtain(key)` 取得锁对象，再在 `try` 中加锁并执行注册，最后在 `finally` 中解锁。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; text-align:left; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 1 · 旧实现清理后，这条 context-path 注册锁路径仍然保留</figcaption>
<div tabindex="0" role="region" aria-label="图 1 · 保留的 context-path 注册锁路径" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg class="shenyu-flow" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="shenyu7426-lock-title shenyu7426-lock-desc" viewBox="0 0 640 520" style="display:block; width:100%; min-width:540px; height:auto; font-family:var(--font-sans); --flow-node:light-dark(#e8f3fc,#142b3e); --flow-condition:light-dark(#f4f9fe,#102333); --flow-ink:light-dark(#235e89,#c0def4); --flow-border:light-dark(#d0e0ed,#355167); --flow-line:light-dark(#8e959d,#8295a6); --flow-success:light-dark(#e5f6eb,#152f26); --flow-success-ink:light-dark(#286447,#a9debf); --flow-success-border:light-dark(#afd3bc,#426c57);">
<title id="shenyu7426-lock-title">保留的 context-path 注册锁路径</title>
<desc id="shenyu7426-lock-desc">registerContextPath 构造锁 key，使用 LockRegistry.obtain 取得锁对象，在 try 中调用 lock.lock 并执行注册。已有 Rule 时提前返回。正常完成、提前返回或异常退出都会执行 finally 中的 lock.unlock。此图不是所有注册入口的概括。</desc>
<defs><marker id="shenyu7426-lock-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<g fill="none" stroke="var(--flow-line)" stroke-width="1.2" marker-end="url(#shenyu7426-lock-arrow)"><path d="M320 76 V108"/><path d="M320 176 V208"/><path d="M320 264 V296"/><path d="M320 382 V426"/></g>
<rect x="160" y="20" width="320" height="56" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="320" y="54" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">进入 context-path 注册方法</text>
<rect x="144" y="110" width="352" height="66" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="320" y="138" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">LockRegistry.obtain(key)</text>
<text x="320" y="162" text-anchor="middle" fill="var(--flow-ink)" font-size="13">取得锁对象，key 来自 context-path</text>
<rect x="196" y="210" width="248" height="54" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="320" y="243" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">lock.lock()</text>
<rect x="144" y="298" width="352" height="84" rx="20" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-dasharray="3 4"/>
<text x="320" y="329" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">执行 Selector / Rule 注册逻辑</text>
<text x="320" y="360" text-anchor="middle" fill="var(--flow-ink)" font-size="13">已有 Rule 时提前 return</text>
<text x="320" y="408" text-anchor="middle" fill="var(--flow-ink)" font-size="13">正常完成 · 提前返回 · 异常退出</text>
<rect x="144" y="428" width="352" height="72" rx="20" fill="var(--flow-success)" stroke="var(--flow-success-border)"/>
<text x="320" y="458" text-anchor="middle" fill="var(--flow-success-ink)" font-size="16" font-weight="500">finally：lock.unlock()</text>
<text x="320" y="484" text-anchor="middle" fill="var(--flow-success-ink)" font-size="13">退出 try 时执行解锁</text>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">只展示本次核对的 context-path 路径，不代表所有注册入口。窄屏可在图内左右滑动查看。</div>
</figure>

这里还有一个容易忽略的细节：发现同名 Rule 已存在时，方法会提前 `return`，但依然会走 `finally`。我确认的不是“找到了另一个叫 lock 的类”，而是具体入口里的加锁、业务操作和解锁确实连在一起。

这让我能把两件事区分开：如果旧实现仍在承担业务职责，那是迁移；现在这条现存路径已经使用 `LockRegistry`，旧类型又没有仓库内消费者，这次才是清理。它们的 diff 可能都很小，但前提完全不同。

## 名字里都有 lock，也不能一起删

确认可以清理旧实现之后，我没有把搜索结果里所有带 lock、JDBC 或 ZooKeeper 的代码都算进来。ShenYu Admin 还有其他锁机制，同样的关键词不代表同样的职责。

这次的边界可以拆成下面几块：

| 范围 | 这次怎么处理 | 原因 |
| --- | --- | --- |
| 五个旧注册锁类型 | 删除 | 已废弃，仓库内没有生产消费者 |
| `registerExecutionRepository` Bean 及相关 imports | 删除 | 只负责创建旧实现 |
| 两个旧锁测试文件 | 删除 | 专门验证这套被移除的实现 |
| context-path 的 `LockRegistry` 路径 | 保留 | 当前仍在使用的注册加锁路径 |
| JDBC / ZooKeeper 集群选主、锁配置 | 保留 | 仍在运行，且不是这套旧注册锁的职责 |
| 数据库 schema、其他活跃的 `selectByNameForUpdate` 调用 | 保留 | 不能因为旧锁使用过它们，就认为它们也已废弃 |

例如，旧锁调用过 `selectByNameForUpdate`，但这个 mapper 方法还有活跃的调用点。删除旧调用方，不等于数据库行锁本身已经没用了。

最后的修改因此很集中：五个生产类型、配置中的一个 Bean 和相关 imports、两个旧测试文件，总共涉及八个 `shenyu-admin` 文件。没有改数据库结构，也没有顺手调整现有锁配置。

## 旧测试可以删，留下来的行为仍然要检查

这个 PR 没有新增测试，还删除了两个测试文件：`ForUpdateBackedRegisterExecutionLockTest` 和 `RegisterExecutionRepositoryTest`。

它们验证的就是旧实现。对应的生产代码删掉后，继续保留这些测试没有意义。但这不代表这次不需要验证——重点变成了：**清理旧实现之后，真正还在用的路径有没有受到影响？**

我保留并运行了 context-path 注册、JDBC 选主和 ZooKeeper 选主对应的测试。PR 提交记录里，三个相关测试类分别通过了 1、2、5 个用例，完整 Admin 测试套件也通过：1,718 个测试，0 failures、0 errors，以及 1 个原有 skipped test。Checkstyle 和 Apache RAT 同样通过。

以前我更容易从“这次新增了什么测试”看一个修改。这次我关心的却是留下来的部分：不再测试已经不存在的旧实现，而是确认清理没有误伤现有行为。

## 仓库内没有消费者，不等于没有兼容性成本

还有一个边界需要说清楚。这些类型虽然已经废弃，却是发布在 `shenyu-admin` artifact 中的公开类型，不是纯粹的私有实现。

所以，我能通过搜索确认仓库内部没有消费者，却不能据此说外部也没人依赖它们。外部代码如果还实现 `RegisterExecutionRepository`，或者直接引用旧实现，删除后就会遇到源码或二进制兼容性问题。这个成本在 PR 描述中也明确写了出来。

旧 Javadoc 已经提示替代方案，但“有迁移提示”和“所有用户都已经迁移”仍然不是一回事。最终这次清理经过维护者 review 后合并；对我来说，重要的是把内部调用链的结论和公开 API 的兼容性影响分别讲清楚，而不是拿 `@Deprecated` 把后者一笔带过。

## 删除之前的判断，才是这次的主要工作

以前想到开源贡献，我更容易想到修 Bug、补功能，或者写出一段新的实现。这次的结果却是零新增、418 行删除。单看 diff 很简单，但真正花时间的，是弄清楚为什么它现在可以被删除。

我也更具体地理解了 `@Deprecated`：它像是在告诉我，这个 API 正在退出，而不是宣布它已经消失。往后再遇到类似清理，我会先找消费者和实际入口，确认现存路径怎么工作，再决定清理到哪里为止。Bean 还在不代表业务还在用；名字相似，也不代表职责相同。

这次让我有把握提交的，不是“这些代码看起来没人要了”，而是我能解释清楚：仓库内没有旧实现的生产消费者，当前 context-path 加锁路径仍然完整，旁边活跃的选主和数据库机制也没有被动到。至于公开 API 的兼容性成本，需要单独说明，不能假装不存在。

我觉得这种贡献的价值，不一定体现在写了多少行。有时候，把一套已经退出业务链路、却还会让后来的人困惑的实现清掉，也是在帮项目往前走。**比“我删了 418 行”更值得记住的，是我终于能把为什么要删、为什么只删这些讲清楚。**
