---
title: '一个多出来的 n，为什么不能只删掉：Apache ShenYu Registry 地址重写修复'
description: '从 nnamespace 这个小错误出发，我发现仅仅去掉一个 + 1，还会留下参数丢失和误截地址的问题。记录这次使用 Dubbo URL 模型修复 Registry 地址重写，以及围绕相邻输入补充测试的过程。'
pubDate: 2026-10-05T05:10:05+08:00
category: open-source
tags:
  - Apache ShenYu
  - Apache Dubbo
  - Java
  - URL
  - 回归测试
draft: false
postType: metaOnly
---

这次问题，最先让我注意到的是一个多出来的 `n`。

在 Apache ShenYu 的 Dubbo 插件中，请求可以带上 `namespace`，用于覆盖当前 Reference 的 Registry 地址参数。[Issue #6516](https://github.com/apache/shenyu/issues/6516) 里，原本的 `namespace=old` 在替换后却变成了 `nnamespace=new`：

```text
原地址：zookeeper://127.0.0.1:2181?namespace=old
请求：  namespace: new
结果：  zookeeper://127.0.0.1:2181?nnamespace=new
```

找到代码以后，我的第一反应也是：是不是把 `substring` 里那个 `+ 1` 去掉就好了？看起来只是多保留了一个字符，修复应该很直接。

但再往旁边看几个输入，我发现事情没有这么简单。地址里多一个参数，或者主机名里恰好出现 `namespace`，这段逻辑仍然可能改坏整个地址。**多出来的 `n` 只是最容易看见的结果，真正的问题是：代码在用字符串的位置猜 URL 的结构。**

最后这次修复合并为 [PR #7425](https://github.com/apache/shenyu/pull/7425)，只改了两个文件。相比改动大小，我更想记下的是：自己怎么从“删掉一个字符”，走到了重新理解这段代码到底要做什么。

## 修掉一个字符，不等于修掉同一种错误

问题出在 `ApacheDubboConfigCache` 的 `changeRegistryAddressNamespace(...)`。原来的实现分成两条路径：地址里没有 `namespace`，就拼上 `?namespace=...`；已经有了，就找到它的位置，截掉后半段，再拼一个新值。

把关键部分单独拿出来，是这样的：

```java
// 原实现的关键逻辑，省略 RegistryConfig 的创建和绑定
if (!address.contains(Constants.NAMESPACE)) {
    newAddress = address + "?" + Constants.NAMESPACE + "=" + namespace;
} else {
    newAddress = address.substring(
            0, address.indexOf(Constants.NAMESPACE) + 1)
            + Constants.NAMESPACE + "=" + namespace;
}
```

这里的 `Constants.NAMESPACE` 就是 `"namespace"`。`substring` 的结束位置不包含在结果里，但这里加了 `1`，于是多保留了开头的 `n`。后面又拼上完整的 `namespace=new`，就变成了 `nnamespace=new`。

把 `+ 1` 去掉，确实能让 Issue 里的这个例子恢复正常。可如果地址是下面这样呢？

```text
zookeeper://127.0.0.1:2181?namespace=old&group=g&timeout=5000
```

我们只想换掉 namespace，`group` 和 `timeout` 都应该留下。但原来的操作是“从 namespace 的位置截到结尾”，这两个参数会一起被丢掉。即使不再多出那个 `n`，这件事也没有改变。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; text-align:left; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 1 · 只想换一个参数，却可能把后面的配置一起截掉</figcaption>
<div tabindex="0" role="region" aria-label="图 1 · 字符串截取与参数修改的对比" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg class="shenyu-flow" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="shenyu7425-rewrite-title shenyu7425-rewrite-desc" viewBox="0 0 640 430" style="display:block; width:100%; min-width:540px; height:auto; font-family:var(--font-sans); --flow-node:light-dark(#e8f3fc,#142b3e); --flow-ink:light-dark(#235e89,#c0def4); --flow-border:light-dark(#d0e0ed,#355167); --flow-line:light-dark(#8e959d,#8295a6); --flow-warn:light-dark(#fff3d7,#352918); --flow-warn-ink:light-dark(#8b5b22,#f3ce8d); --flow-warn-border:light-dark(#e8c98e,#80663a); --flow-success:light-dark(#e5f6eb,#152f26); --flow-success-ink:light-dark(#286447,#a9debf); --flow-success-border:light-dark(#afd3bc,#426c57);">
<title id="shenyu7425-rewrite-title">字符串截取与参数修改的对比</title>
<desc id="shenyu7425-rewrite-desc">原地址的参数是 namespace=old、group=g、timeout=5000。原实现从 namespace 的位置截断，生成 nnamespace=new 并丢失其余参数；使用 Dubbo URL 模型设置 namespace 后，group 和 timeout 仍然保留。</desc>
<defs><marker id="shenyu7425-rewrite-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<rect x="54" y="18" width="532" height="86" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="320" y="49" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">原 Registry 地址</text>
<text x="320" y="78" text-anchor="middle" fill="var(--flow-ink)" font-size="14">namespace=old · group=g · timeout=5000</text>
<g fill="none" stroke="var(--flow-line)" stroke-width="1.2" marker-end="url(#shenyu7425-rewrite-arrow)">
<path d="M320 104 V126 Q320 136 310 136 H174 Q164 136 164 146 V182"/>
<path d="M320 104 V126 Q320 136 330 136 H466 Q476 136 476 146 V182"/>
<path d="M164 262 V314"/><path d="M476 262 V314"/>
</g>
<text x="164" y="164" text-anchor="middle" fill="var(--flow-ink)" font-size="13">原来的字符串逻辑</text>
<text x="476" y="164" text-anchor="middle" fill="var(--flow-ink)" font-size="13">修复后的 URL 模型</text>
<rect x="26" y="184" width="276" height="78" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="164" y="214" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">找到位置，截掉后半段</text>
<text x="164" y="240" text-anchor="middle" fill="var(--flow-ink)" font-size="13">substring + 拼接新值</text>
<rect x="338" y="184" width="276" height="78" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="476" y="214" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">解析地址，只设置 namespace</text>
<text x="476" y="240" text-anchor="middle" fill="var(--flow-ink)" font-size="13">addParameter → toFullString</text>
<rect x="26" y="316" width="276" height="92" rx="20" fill="var(--flow-warn)" stroke="var(--flow-warn-border)"/>
<text x="164" y="347" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="16" font-weight="500">nnamespace=new</text>
<text x="164" y="376" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="13">group / timeout 一起丢失</text>
<rect x="338" y="316" width="276" height="92" rx="20" fill="var(--flow-success)" stroke="var(--flow-success-border)"/>
<text x="476" y="347" text-anchor="middle" fill="var(--flow-success-ink)" font-size="16" font-weight="500">namespace=new</text>
<text x="476" y="376" text-anchor="middle" fill="var(--flow-success-ink)" font-size="13">group=g · timeout=5000 保留</text>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">窄屏可在图内左右滑动查看。</div>
</figure>

这时我开始觉得，不应该只盯着那个字符。需要继续问的是：这段代码还默认了哪些条件？

## 出现了同一个单词，不代表找到了同一个参数

另一个分支也有问题。如果原地址已经有 `group=g`，只是没有 namespace，直接追加 `?namespace=new` 就会得到：

```text
zookeeper://127.0.0.1:2181?group=g?namespace=new
```

第二个 query 参数应该由 `&` 分隔，而不是再加一个 `?`。不过，就算为它补一个“有没有问号”的判断，仍然没有解决更根本的问题：`contains("namespace")` 判断的是整个字符串，不是 query 的参数名。

| namespace 出现在哪里 | 为什么不能按原逻辑截取 |
| --- | --- |
| 主机名：`my-namespace-svc` | 它属于 host，不是参数名 |
| 路径：`/namespace` | 它属于 path，不能当成 query 来替换 |
| 参数值：`group=namespace` | 值里出现这个词，不代表存在同名 key |

这些都是合法输入可能具有的形态，却会被同一个 `contains` 命中。接着用第一个 `indexOf` 截取，甚至可能从主机名或路径中间截断地址。

到这里，继续补字符串规则就不太合适了。问题不是“namespace 在第几位”，而是“query 里有没有一个叫 namespace 的参数，以及怎么设置它”。

## 用已有的 URL 模型，直接表达要改什么

Dubbo 本身已经有 `org.apache.dubbo.common.URL`。最终我没有再手工判断分隔符和字符串位置，而是复用这个模型：

```java
URL.valueOf(currentRegistryConfig.getAddress())
        .addParameter(Constants.NAMESPACE, namespace)
        .toFullString()
```

这三步分别是解析原地址、设置 namespace 参数、重新序列化。已有这个参数就替换它，没有就新增；主机名、路径和其他参数不再跟着某个字符串位置一起被截走。

对我来说，最明显的变化其实是代码的表达方式。原来的代码在解释“怎么找到它、截到哪里、再拼什么”，现在只需要说明“我要修改这个参数”。其他部分交给项目本身已经使用的 URL 模型处理，也不需要引入新的依赖。

这里用的是 **Dubbo 的 URL 模型**，不是 `java.net.URL`。我希望保持项目原有的地址解析语义，而不是为了这次修复另写一套 URL 规则。

## 测试要覆盖相邻输入，也要比较真正的语义

如果测试只写 Issue 里的那个地址，去掉 `+ 1` 和换成 URL 模型，都可能让它通过。可这两种修复解决的问题范围并不一样。

所以我把前面发现的相邻输入一起整理成了八组参数化场景：

| 输入形态 | 重点确认 |
| --- | --- |
| 只有 `namespace=old` | 旧值被替换，没有多余的 `n` |
| 完全没有 query 参数 | 能新增 namespace |
| 有 `group=g`，没有 namespace | 新增参数，同时保留 group |
| namespace 在最前，后面还有参数 | 后面的 group、timeout 不丢失 |
| namespace 在中间 | 前后参数都保留 |
| host 包含 `namespace` | 主机名不被误截 |
| path 和参数值包含 `namespace` | 不把它们误认成参数名 |
| 有用户名、密码及 `group=g%26x` | 地址组件和已有编码参数值保留 |

测试里还有一个我觉得很值得记下来的细节：**没有直接比较最终 URL 字符串。**

对于这里的 Registry 地址，下面两个 query 表达的是同一组参数：

```text
?namespace=new&group=g
?group=g&namespace=new
```

重新序列化后，参数顺序未必和我手写的 expected 一样。如果只比较字符串，测试可能因为顺序变化而失败，但地址本身并没有错。

所以断言会把 expected 和 actual 都重新解析成 Dubbo URL，分别比较 protocol、host、port、path、username、password 和 parameters。像下面这两项，就是完整断言的一部分：

```java
URL expected = URL.valueOf(expectedAddress);
URL actual = URL.valueOf(actualAddress);

assertEquals(expected.getHost(), actual.getHost());
assertEquals(expected.getParameters(), actual.getParameters());
```

我需要确认的是 namespace 已更新、其余地址信息还在，而不是要求参数必须按某一种固定顺序打印。这让我对“测试到底应该比较什么”有了更具体的理解。

## 两条入口都要接住，原始配置也不能被改动

`ApacheDubboConfigCache` 不只有普通的 Reference 构建路径，还有根据 `RuleData` 和 `DubboUpstream` 构建 Reference 的路径。两边在 namespace 非空时，都会调用同一个地址重写方法。

除了八组参数化测试，我也补了一条 upstream 路径的回归测试，确认经过另一条入口，namespace 能更新，group 和 timeout 仍然保留。

还有一个边界需要守住：namespace 来自当前请求，不应该因此修改原始 Registry 配置。实现仍然创建新的 `RegistryConfig`，将重写后的地址绑定到当前 Reference，而不是直接改传入的配置对象。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; text-align:left; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 2 · 两条入口共用重写逻辑，结果只绑定到当前 Reference</figcaption>
<div tabindex="0" role="region" aria-label="图 2 · Reference 构建与 Registry 配置隔离" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg class="shenyu-flow" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="shenyu7425-reference-title shenyu7425-reference-desc" viewBox="0 0 640 550" style="display:block; width:100%; min-width:540px; height:auto; font-family:var(--font-sans); --flow-node:light-dark(#e8f3fc,#142b3e); --flow-condition:light-dark(#f4f9fe,#102333); --flow-ink:light-dark(#235e89,#c0def4); --flow-border:light-dark(#d0e0ed,#355167); --flow-line:light-dark(#8e959d,#8295a6); --flow-success:light-dark(#e5f6eb,#152f26); --flow-success-ink:light-dark(#286447,#a9debf); --flow-success-border:light-dark(#afd3bc,#426c57);">
<title id="shenyu7425-reference-title">Reference 构建与 Registry 配置隔离</title>
<desc id="shenyu7425-reference-desc">普通 Reference 从当前 RegistryConfig 读取地址，upstream Reference 从 DubboUpstream 构造临时配置。在 namespace 非空时，两条入口调用共同的 changeRegistryAddressNamespace，解析地址、设置参数并序列化。结果写入新的 RegistryConfig 后绑定当前 Reference，原 RegistryConfig 与 DubboUpstream 保持不变。</desc>
<defs><marker id="shenyu7425-reference-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<rect x="26" y="18" width="276" height="78" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="164" y="49" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">普通 Reference</text>
<text x="164" y="75" text-anchor="middle" fill="var(--flow-ink)" font-size="13">读取当前 RegistryConfig</text>
<rect x="338" y="18" width="276" height="78" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="476" y="49" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">Upstream Reference</text>
<text x="476" y="75" text-anchor="middle" fill="var(--flow-ink)" font-size="13">从 DubboUpstream 构造临时配置</text>
<g fill="none" stroke="var(--flow-line)" stroke-width="1.2" marker-end="url(#shenyu7425-reference-arrow)">
<path d="M164 96 V158 Q164 170 176 170 H320 V196"/>
<path d="M476 96 V158 Q476 170 464 170 H320 V196"/>
<path d="M320 312 V362"/><path d="M320 434 V474"/>
</g>
<text x="164" y="128" text-anchor="middle" fill="var(--flow-ink)" font-size="13">namespace 非空</text>
<text x="476" y="128" text-anchor="middle" fill="var(--flow-ink)" font-size="13">namespace 非空</text>
<rect x="118" y="198" width="404" height="114" rx="20" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-dasharray="3 4"/>
<text x="320" y="228" text-anchor="middle" fill="var(--flow-ink)" font-size="15" font-weight="500">changeRegistryAddressNamespace</text>
<text x="320" y="258" text-anchor="middle" fill="var(--flow-ink)" font-size="14">解析原地址 → 设置 namespace</text>
<text x="320" y="286" text-anchor="middle" fill="var(--flow-ink)" font-size="14">→ 重新序列化 URL</text>
<rect x="158" y="364" width="324" height="70" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="320" y="393" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">写入新的 RegistryConfig</text>
<text x="320" y="418" text-anchor="middle" fill="var(--flow-ink)" font-size="13">保留 register=false</text>
<rect x="158" y="476" width="324" height="56" rx="20" fill="var(--flow-success)" stroke="var(--flow-success-border)"/>
<text x="320" y="510" text-anchor="middle" fill="var(--flow-success-ink)" font-size="16" font-weight="500">绑定到当前 Reference</text>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">原 RegistryConfig 的地址、DubboUpstream 的 registry 字段都保持原值。窄屏可在图内左右滑动查看。</div>
</figure>

测试不只检查新地址，也检查 `reference.getRegistry()` 不是原配置对象、原地址仍然不变；upstream 用例同样检查 `DubboUpstream.getRegistry()` 没有被修改。这样一次请求的覆盖值，才不会顺手变成后续请求共用的配置。

## 小修复的价值，是让我看见原先没问过的问题

前面几个 ShenYu PR，我花了不少时间在同步链路、并发和缓存生命周期上。这次没有那么多模块，核心改动也很短。刚看到 Issue 时，我确实觉得它可能只是一个很快就能修好的字符串错误。

但把那些输入放在一起以后，我意识到：代码能处理眼前这个例子，不代表我已经理解了它应该接受什么样的输入。地址多一个参数，或者同一个词换个位置，就足以把原来没写出来的假设暴露出来。

以后再遇到类似问题，我会先问自己：**我是在修改数据的某个字段，还是只是在修改它打印出来的样子？** 如果项目已经有对应的模型，先读懂并复用它，往往比自己继续补分隔符和截取规则更合适。

测试也是一样。我以前很容易把“expected 和 actual 一样”当作目标，这次才更具体地想清楚：什么应该一样，什么只是表示方式不同。namespace 的值、其他参数和原配置的状态需要保证，query 参数的打印顺序则不是这里要守住的东西。

这个 PR 没有很大的 diff，但它让我多了一点面对小 Bug 时的耐心。先别急着把最显眼的那个字符删掉；再往旁边看一步，可能才会发现真正该修的地方。
