---
title: '安装成功，不等于升级成功：Octop Windows 便携版在线升级修复'
description: '一次卡在 85% 的在线升级，让我追到了依赖复用与实际版本校验，也第一次和学弟一起拆分修复、对齐接口并补齐联动测试。记录 Octop PR #1576 的排查与合作。'
pubDate: 2026-10-16T23:25:14+08:00
category: open-source
tags:
  - Octop
  - Python
  - pip
  - uv
  - 在线升级
draft: false
postType: metaOnly
---

进度条停在 85%，到底是在下载、安装，还是已经失败了？

这次在 [TencentCloud Octop](https://github.com/TencentCloud/Octop) 里处理的，就是这样一个在线升级问题。用户反馈 Windows 便携版升级迟迟没有完成。我用官方 `1.0.2b4` 包复现升级到 `1.0.2b5` 的过程，最后等到的不是新版，而是多次超时，目标目录里仍然是旧版本。

继续查下去，我发现需要分开回答两个问题：**为什么升级会重新安装一批已经存在的依赖？即使安装程序正常退出，又凭什么确认升级真的完成了？**

前一个问题影响用户要等多久，后一个问题决定页面上的“成功”是否可信。最后的修改合并在 [PR #1576](https://github.com/TencentCloud/Octop/pull/1576)。这篇想记录的，是我怎样把这两个问题拆开，又把它们放回同一条升级流程里。

不过，这次不是我一个人在处理升级问题。学弟也在修相邻的一段链路。我们从差点重复修改，到把问题拆开、分工，再检查两份修改接到一起后的行为。对我来说，这也是这次贡献里很重要的一部分。

## 同样是“升级后还是旧版”，先拆清我们各自负责什么

刚开始看，两边遇到的现象很像：用户明明尝试了升级，最后却还是旧版本。但继续查根因后，我们发现需要分成两个问题，而不是往同一份修复里不断加东西。

| 问题 | 分工与对应修改 |
| --- | --- |
| 换了新版桌面程序，启动器却继续使用旧运行时 | 学弟 [MakerFlyFly](https://github.com/MakerFlyFly) 负责，跟踪在 [Issue #1560](https://github.com/TencentCloud/Octop/issues/1560) 和 [PR #1561](https://github.com/TencentCloud/Octop/pull/1561) |
| 程序内在线升级反复安装依赖、超时，升级结果也缺少可靠校验 | 我负责，跟踪在 Issue #1562 和 PR #1576 |

我们先对齐修改范围。我把自己这边重复的 Go 版本比较和启动器改动拿掉，集中处理程序内安装、uv 打包和升级结果校验。启动器已经传入的 `OCTOP_GREEN_PACKAGES` 继续沿用，让升级仍然写到应用真正使用的 `packages` 目录，不额外发明一套接口。

分工清楚之后，还要检查交界处。例如：`VERSION.txt` 仍写着 b4，但程序内升级已经把实际包更新成 b6，此时再启动内置 b5 的桌面程序，应该保留 b6，而不是把它换回 b5。这里的 b6 是构造的测试版本，用来确认“在线升级”和“启动器准备运行时”不会互相拆台。

学弟在启动器侧补了这类联动用例，我也在 Python 侧对齐了 Go 比较器的版本排序用例。两份 PR 因此不只是各自修好一段，还要确认它们对版本先后、目标目录和不降级行为有一致的理解。

## 卡住的不是进度条，而是一次重新开始的依赖安装

在 [Issue #1562](https://github.com/TencentCloud/Octop/issues/1562) 的排查里，我没有只看界面上的百分比，而是用隔离的官方便携包调用实际升级 worker，去看安装日志和最后留下的版本。

那次复现中，升级依次尝试了五个软件源，每个安装过程都有 90 秒的超时限制。日志里反复出现依赖收集，最后仍然失败。界面的 85% 只是进度计时逻辑的上限，不能据此判断它正卡在哪个安装步骤。

便携版把 Python 包放在自己的 `packages` 目录中，升级时使用 `pip install --target` 写回这个位置。我原本需要确认的是：目录里已经有依赖，pip 会不会直接用它们？

查到这里，关键区别才清楚了：**文件存在于目标目录，不等于 pip 的依赖解析器会把它们当成当前环境中已安装的包。** `--target` 走的安装路径会忽略已安装状态，因此一次只更新 Octop 的操作，也可能重新解析、下载并安装整套依赖。

这也解释了为什么补一个 `--upgrade-strategy only-if-needed` 不够。它没有改变解析器看待这个目标目录的方式。换一个软件源，或者把等待时间调长，能缓解部分失败，却没有解决“为什么又从头装了一遍”的问题。

## 复用依赖之前，先证明这些依赖还能用

但另一个极端也不行：既然依赖都在目录里，直接加上 `--no-deps`，只更新 Octop，不就好了？

这样确实可以少装很多东西，可新版本可能新增依赖，也可能提高了版本要求。安装得快，和安装后的环境完整，是两件事。

所以这次没有把所有便携版都改成无条件跳过依赖，而是保留了两条路径：

| 环境 | 安装策略 |
| --- | --- |
| 能使用 uv 的便携版 | 优先使用随包提供的 uv，再考虑外部 uv |
| 没有 uv 的旧便携包 | 继续支持 pip，符合条件时复用已有依赖，否则走完整依赖安装 |

新打包的便携版会带上 uv，但旧包只更新 Octop 的 wheel，并不会凭空多出一个 uv。因此，旧包的 pip 路径仍然要修，不能让用户先手动换一整套环境。

这条 pip 快速路径先下载 **Octop 自身的 wheel**，暂时不动目标目录。接着读取 wheel 的依赖信息，对照目标目录中的包，检查直接依赖、传递依赖、版本约束，以及 extras、环境标记和 Python 版本要求。

只有这些条件都满足，才从本地 wheel 执行不联网、不重新解析依赖的安装：

```text
先下载 Octop wheel → 检查已有依赖 → 本地安装 --no-index --no-deps
```

如果依赖不满足、元数据不完整，或者快速安装后的校验没有通过，就回到完整安装路径。下载本身失败时，则直接换下一个软件源，目标目录还没有被修改。

我想保留的不是“一定走最快的路线”，而是：能确认安全时少做重复工作，确认不了时仍然有原来的安装方式可以走。

## 超时要给修复留机会，也不能让每次重试重新计时

排查时我也对照了 [PR #1575](https://github.com/TencentCloud/Octop/pull/1575) 对超时和新进程版本校验的处理。完整依赖安装确实可能需要比 90 秒更长的时间，但如果每换一个软件源，就重新给一整段很长的超时，用户还是不知道要等到什么时候。

这次对旧包的 pip 路径做了区分：单独下载 wheel 和本地快速安装通常各有 90 秒限制；一旦进入完整安装回退，就启用一个 **900 秒的共享时间窗口**。后续换源或安装步骤使用剩余时间，而不是每次重新获得 900 秒。

这个窗口约束的是进入回退后的安装尝试，不是整个升级的总耗时上限。首次回退前的尝试和最后的版本探测，还有各自的耗时。

## 安装器的返回码，不能替用户确认升级结果

前面的复现确实是超时失败。继续检查代码时，我还发现了另一处需要加固的判断：安装程序返回 `0` 后，如果没有读到可信的新版本，也不应该兜底报告成功。

这里不能只看包的安装元数据。目标目录里可能留下了较新的 `dist-info`，实际导入的代码却还是旧的；服务进程也可能一直在运行，内存里的模块不会因为磁盘上的文件被替换，就自动变成新版。

因此，安装结束后的检查放到一个新的 Python 解释器里执行：从目标目录加载 Octop，处理 `.pth`，确认模块确实来自这个目录，再读取代码中的 `__version__`。它还会执行一次 CLI 的 `--version`，确认入口能正常运行；但**用来判断版本的是加载到的代码，不是 CLI 打印的元数据版本**。

最终要求也很直接：实际版本必须可读取，比升级前更新；如果用户指定了版本，还必须与指定版本一致。探测最多尝试三次，满足条件才返回成功。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; text-align:left; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 1 · 安装器退出之后，升级还没有被证明成功</figcaption>
<div tabindex="0" role="region" aria-label="图 1 · Octop 目标版本校验流程" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg class="shenyu-flow" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="octop1576-verify-title octop1576-verify-desc" viewBox="0 0 640 580" style="display:block; width:100%; min-width:540px; height:auto; font-family:var(--font-sans); --flow-node:light-dark(#e8f3fc,#142b3e); --flow-condition:light-dark(#f4f9fe,#102333); --flow-ink:light-dark(#235e89,#c0def4); --flow-border:light-dark(#d0e0ed,#355167); --flow-line:light-dark(#8e959d,#8295a6); --flow-success:light-dark(#e5f6eb,#152f26); --flow-success-ink:light-dark(#286447,#a9debf); --flow-success-border:light-dark(#afd3bc,#426c57); --flow-warning:light-dark(#fff5dc,#332a18); --flow-warning-ink:light-dark(#856020,#e5c78c); --flow-warning-border:light-dark(#e5cc95,#6c5830);">
<title id="octop1576-verify-title">Octop 安装后的目标版本校验</title>
<desc id="octop1576-verify-desc">安装器返回零之后，还要在新解释器中检查目标模块来源、实际代码版本和 CLI 能否执行。探测与版本判断最多一起执行三次，实际版本可读、比旧版更新，且匹配明确指定的版本时，返回升级成功。三次均未通过则返回校验失败，调用方可能继续回退安装或尝试下一镜像。此图省略安装与镜像重试。</desc>
<defs><marker id="octop1576-verify-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<g fill="none" stroke="var(--flow-line)" stroke-width="1.2" marker-end="url(#octop1576-verify-arrow)"><path d="M320 84 V132"/><path d="M320 326 V364 Q320 374 310 374 H174 Q164 374 164 384 V428"/><path d="M320 326 V364 Q320 374 330 374 H466 Q476 374 476 384 V428"/></g>
<rect x="176" y="20" width="288" height="64" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="320" y="58" text-anchor="middle" fill="var(--flow-ink)" font-size="17" font-weight="500">安装器返回 0</text>
<text x="320" y="113" text-anchor="middle" fill="var(--flow-ink)" font-size="13">继续校验，不能直接报告成功</text>
<rect x="112" y="134" width="416" height="192" rx="22" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-dasharray="3 4"/>
<text x="320" y="168" text-anchor="middle" fill="var(--flow-ink)" font-size="17" font-weight="500">探测并校验目标版本</text>
<text x="320" y="198" text-anchor="middle" fill="var(--flow-ink)" font-size="14">新解释器 · 来源检查 · CLI 冒烟检查</text>
<path d="M144 216 H496" fill="none" stroke="var(--flow-border)"/>
<text x="320" y="244" text-anchor="middle" fill="var(--flow-ink)" font-size="14">实际版本可读取，且比升级前更新</text>
<text x="320" y="270" text-anchor="middle" fill="var(--flow-ink)" font-size="14">指定版本时，还必须与请求匹配</text>
<text x="320" y="302" text-anchor="middle" fill="var(--flow-ink)" font-size="13">最多三次，取得合格版本即返回</text>
<rect x="112" y="390" width="104" height="26" rx="13" fill="var(--flow-condition)" stroke="var(--flow-border)"/>
<text x="164" y="408" text-anchor="middle" fill="var(--flow-ink)" font-size="12">取得合格版本</text>
<rect x="418" y="390" width="116" height="26" rx="13" fill="var(--flow-condition)" stroke="var(--flow-border)"/>
<text x="476" y="408" text-anchor="middle" fill="var(--flow-ink)" font-size="12">三次均未通过</text>
<rect x="44" y="430" width="240" height="80" rx="20" fill="var(--flow-success)" stroke="var(--flow-success-border)"/>
<text x="164" y="464" text-anchor="middle" fill="var(--flow-success-ink)" font-size="17" font-weight="500">返回升级成功</text>
<text x="164" y="490" text-anchor="middle" fill="var(--flow-success-ink)" font-size="13">记录实际加载的版本</text>
<rect x="356" y="430" width="240" height="80" rx="20" fill="var(--flow-warning)" stroke="var(--flow-warning-border)"/>
<text x="476" y="464" text-anchor="middle" fill="var(--flow-warning-ink)" font-size="17" font-weight="500">返回校验失败</text>
<text x="476" y="490" text-anchor="middle" fill="var(--flow-warning-ink)" font-size="13">由调用方继续处理回退 / 换源</text>
<text x="320" y="552" text-anchor="middle" fill="var(--flow-ink)" font-size="12">此图只展示目标版本校验，省略安装与镜像重试流程</text>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">窄屏可在图内左右滑动查看。</div>
</figure>

这也影响升级开始前的判断：同版本重装或降级请求应该先被拒绝，而不是等文件被修改后再发现。读取目标目录里的实际版本，也能避免服务尚未重启时，用内存中的旧版本做错误判断。

## 验证时，我关心的是文件最后变成了什么

这类修改只验证“命令拼得对不对”，还是不够。它写的是用户正在使用的目录，安装前后的实际状态才是重点。

我在 PR 中记录的验证，主要围绕下面几种情况展开：

| 要确认的判断 | 对应验证 |
| --- | --- |
| 已有依赖满足时，能否只更新 Octop | 用官方 b4 便携包、真实 Python / pip 和 b5 wheel 跑升级 worker，已有 194 个依赖的版本保持不变 |
| 依赖已经不满足时，会不会错误跳过安装 | 构造已安装 1.0、新版本要求 2.0 的依赖，确认回到完整安装 |
| 元数据看起来很新，是否就算升级完成 | 检查新元数据搭配旧代码、模块无法导入等情况，确认不能误报成功 |
| 换源后会不会重新拿到完整等待时间 | 用模拟时钟检查完整安装回退的共享时间窗口 |

第一项使用了本地 wheel 来源，也限制了依赖 wheel 的可用性，重点是确认快速路径真的复用了已有依赖，不是换了个地方把依赖又下载了一遍。

这次也没有把升级系统全部重做。Launcher 重新安装旧版的问题由另一条修改处理；完整安装回退仍然是在现有目标上修复，不代表最终失败时可以自动回滚整套便携包。优化哪条路径、成功由什么证明、失败后保留什么能力，需要分别讲清楚。

## “成功”的条件，应该落在用户真正使用的东西上

这次最让我重新理解的，是几个看起来很接近、实际却不同的状态。

目录里有依赖，不等于解析器会复用；安装元数据写着新版，不等于导入的代码就是新版；进程正常退出，也不等于用户下一次启动就能用上它。

经历这次排查后，再看到一个操作返回成功，我会多问一句：**它证明的是哪个环节成功了？离用户真正要的结果，还差哪一步？**

快速路径也是一样。少装一批依赖并不难，难的是把“什么时候可以少装”判断清楚，再给不能走快速路径的环境留下退路。我意识到，性能优化不只是减少工作量，也是在补齐允许省略这些工作的条件。

以后再遇到“完成”“成功”这样的状态，我会更愿意沿着它往下查一层：真正要交到用户手里的东西，到底有没有变成我们承诺的样子。

## 把问题一起修好，比抢先把它做成自己的 PR 更重要

这次也是我第一次和这位学弟一起，分工修复一个牵涉不同链路的问题。

坦白说，一开始我也有过想和他抢进度的念头：能不能赶在前面，把这一整块都放进自己的 PR？但想到他已经花了时间排查、写了修复，我再把这些工作覆盖掉，就觉得这样做不太厚道。而且我们面对的明明是一个还没修完整的问题，没必要先把彼此当成竞争对手。

我当时甚至有点不敢找他，怕他觉得我是在抢他的工作。后来还是决定把话说开：你负责启动器，我负责程序内升级，重复的部分我拿掉，我们把各自的修改做成能一起合并、一起运行的方案。

真正开始合作后，我发现要做的事情并没有变少。我们需要重新划分 Issue 的范围，确认谁改哪段代码，沿用已有接口，再补上两边接起来时的测试。有些已经写过的东西要删掉，有些不属于自己 PR 的边界，也要一起确认。只是这些时间终于花在了互相补齐上，而不是各做一套、再担心谁覆盖了谁。

这次让我意识到，别人先做了一部分，并不意味着我的贡献空间就少了一块。把那部分接住，继续解决剩下的问题，同样是有价值的工作。开源贡献当然会留下各自的提交记录，但一个问题能不能真正解决，并不由某个人的 PR 包含了多少内容决定。

最后，我们分别完成了启动器和程序内升级这两部分修复。我挺庆幸当时还是去找他聊了，也愿意把自己已经做过的一部分拿掉。比起抢先把整个问题做成“我的 PR”，这次能和学弟一起把链路接好，是我更想记下来的一件事。
