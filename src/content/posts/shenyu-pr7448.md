---
title: '少了一个问号，参数成了路径：Apache ShenYu MCP 请求修复'
description: '固定 query 参数和工具输入合并后，为什么整个请求地址变了？从丢失的问号、查错位置的重复判断，到回调中的 URI 验证，记录 ShenYu PR #7448 的修复与收获。'
pubDate: 2026-10-17T11:31:21+08:00
category: open-source
tags:
  - Apache ShenYu
  - Java
  - MCP
  - HTTP
  - 回归测试
draft: false
postType: metaOnly
cover: '../../assets/covers/shenyu-pr7448-light.png'
---

给 MCP 工具配置一个 `/users?fixed=true` 的地址，再让工具输入补上 `page=1`，看起来只是把两个 query 参数放到一起。但 ShenYu 原来的构造结果是 `/users&page=1&fixed=true`。

参数一个都没少，位置却全错了。没有 `?`，后面的内容就不再是 query，而是路径的一部分。

[Issue #7442](https://github.com/apache/shenyu/issues/7442) 记录了这个问题。我在 [PR #7448](https://github.com/apache/shenyu/pull/7448) 中修复它时，还一起处理了重复参数判断：固定参数已经存在时，动态输入不应再添加同名字段；但路径或参数值中出现了相似文字，也不该让动态参数被误删。

这次修改集中在 `RequestConfigHelper`。我需要确认的不只是地址字符串变得好看了，而是回调拿到它之后，仍然能把路径和参数分别读对。

## 模板有问号，不代表拆出来的路径还有问号

`buildPath()` 会先拆开 URL 模板。对于 `/users?fixed=true`，拆出的 `basePath` 是 `/users`，`existingQuery` 是 `fixed=true`。动态参数则单独累积到 `queryBuilder` 中。

到这里都没有问题。错误发生在重新拼接的时候。

原来的 `buildFinalPath()` 根据 `hasExistingQuery` 选择分隔符：模板有 query，就用 `&` 添加动态参数；没有才用 `?`。

但这个标记描述的是**原模板**，不是当前正在拼接的 `basePath`。问号已经在拆分时被拿掉了，不能因为原来有，就假定现在也有。

| 阶段 | 内容 |
| --- | --- |
| 原模板 | `/users?fixed=true` |
| 拆出的路径 | `/users` |
| 生成的动态参数 | `page=1` |
| 原来的拼接结果 | `/users&page=1&fixed=true` |
| 修复后的拼接结果 | `/users?page=1&fixed=true` |

我把添加动态 query 的第一处分隔符固定为 `?`。后面如果还有固定 query，再用 `&` 接上；如果没有动态参数，就让固定 query 自己带上第一个 `?`。

这样，分隔符取决于实际正在构造的内容，而不是之前那个已经被拆开的模板。

## 判断参数是否重复，得去 query 里找

补上问号之后，还需要检查固定参数和动态参数同名时怎么办。

这次保留固定参数优先的规则。例如模板已经写了 `/users?page=10`，工具输入又给出 `page=1`，最终仍然使用 `/users?page=10`，不额外追加一个 `page=1`。

原代码虽然有重复判断，但它检查的是 `modifiedBasePath.contains(key + "=")`。

此时 `modifiedBasePath` 已经不含 query。它既看不到固定的 `page=10`，又可能因为路径里恰好包含 `page=`，误以为参数已经存在。

所以，我把 `existingQuery` 传进 `processArguments()`，让判断回到固定 query 上。同时，不直接搜索任意位置的 `page=`，而是检查它是否出现在开头，或者紧跟在 `&` 后面。

这个边界很重要。`homepage=10` 不是 `page=10`；`note=page=10` 里的 `page=10` 则属于参数值，也不是一个名叫 `page` 的字段。

回归用例把这两种干扰放在同一个模板里：

```text
/users?homepage=10&note=page=10
```

再传入动态 `page=1`，结果应该保留原来的两个字段，并正常加入 `page`。如果只用不分位置的子串搜索，就会把真正需要添加的参数跳过去。

这里采用的是对现有 query 文本的字段边界检查，没有另做一套通用 URL 解析器。固定 query 的原文仍然保留，已有的参数优先级也不变。

## 编码前，先分清原始值和已编码内容

合并参数时，不能因为两边都是字符串，就把它们当成同一种输入。工具传入的是待编码的值，模板里保留的则是已有的 query 文本，其中可能已经包含编码结果。

例如，动态输入 `hello world & 50%` 中的 `&` 是值的一部分，不是参数分隔符，需要编码成 `%26`。但固定 query 中如果已经有 `%26`，再把它当成原始值编码，百分号就会变成 `%25`，得到 `%2526`。看起来只是多处理了一遍，传给下游的含义却变了。

因此，这次合并只对动态值沿用 `UriUtils.encodeQueryParam()`，固定 query 保留原文。回归用例把原始输入和已编码的固定值放在一起，检查的就是这两种状态没有被混为一谈。

这里要先确认的不是“该调用哪个编码方法”，而是“这段内容之前已经经过了什么处理”。分清这个前提，才能判断哪一层需要编码、哪一层只负责拼接，避免在修复一个问题时又改变了原本正常的参数含义。

## 字符串包含参数，还不够证明请求构造正确

这个 Bug 有一个很容易误判的地方：错误地址里也能找到 `page=1` 和 `fixed=true`，甚至连 `&` 都在。如果测试只检查这些子串，仍然可能放过它。

因此，helper 的新增用例直接比较完整结果，覆盖固定与动态参数合并、固定同名参数优先、字段边界，以及编码保留。

但 helper 返回正确字符串，还需要和实际使用它的地方接起来看。

`ShenyuToolCallback` 会根据配置调用 `buildPath()`，再用结果构造内部 HTTP 请求，并更新 `ShenyuContext`。我补了一条回调测试，用 `MockServerWebExchange` 和真实的回调构造方法检查结果，而不是只停在 helper 的返回值。

这条用例从一个 `/mcp` 请求出发，模板设为 `/users?fixed=true`，输入提供 `page=1`。构造后分别确认：

- 请求 URI 是 `http://gateway.example:9195/users?page=1&fixed=true`。
- 请求的 query 参数能分别读出 `page=1` 和 `fixed=true`。
- 上下文的 `path` 和 `realUrl` 都是 `/users`，不混入 query。

这些断言检查的是回调构造出的请求及上下文，没有实际向后端发起网络请求。它们把这次需要修复的边界接了起来：helper 负责拼接，回调负责使用，最终两边对 path 和 query 的理解要一致。

维护者在 [Review](https://github.com/apache/shenyu/pull/7448#pullrequestreview-5450624997) 中确认，修复保留了固定参数，能加入动态参数，也没有覆盖已有的同名字段。对方在 Java 17 下针对当前提交运行目标测试后批准了 PR，随后合并。

## 看起来相似的字符串，可能已经不是同一种数据

这次我意识到，拆开再拼回去，并不是原样搬运。`urlTemplate`、`basePath` 和 `existingQuery` 虽然都是字符串，表示的内容却已经不同。沿用原模板的判断条件之前，需要先确认它对当前这段内容是否还成立。

重复参数的判断也是如此。我需要找的是一个 query 字段，不是任意位置的一段相同文字。先分清查找对象，再决定在哪儿查、按什么边界查，比往 `contains()` 里补几个条件更清楚。

测试上，我也更理解了为什么要检查解析后的含义。参数出现在字符串里，不代表它就是参数；只有请求能把它读进 query，而路径仍然保持 `/users`，才能说明这次拼接达到了预期。

这次的改动不大，但从 helper 一直看到回调以后，修复依据就具体了：保留固定配置的含义，让动态输入在正确的位置加入，再确认使用方读到的还是同一回事。
