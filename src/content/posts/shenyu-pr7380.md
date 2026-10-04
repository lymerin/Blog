---
title: 'CI 红了，不一定是代码错了：第一次排查 Apache ShenYu CI 故障'
description: '维护一个 PR 时，我被一次 k3s 安装失败卡住了。从没有重跑权限，到用假的 curl 稳定复现问题，再第一次主动找维护者讨论，记录这次 CI 排查的过程。'
pubDate: 2026-10-01T13:06:56+08:00
category: open-source
tags:
  - Apache ShenYu
  - GitHub Actions
  - CI
  - Bash
  - k3s
  - 故障排查
draft: false
postType: metaOnly
cover: '../../assets/covers/shenyu-pr7380-light.png'
---

这次修复，是从另一个 PR 的红灯里找出来的。

当时我正在维护 Apache ShenYu [PR #7289](https://github.com/apache/shenyu/pull/7289)。它改动比较多，每次提交都要等 CI 跑不少模块。有一次，`k8s-examples-http` 又失败了，日志最后只留下了一句：

```text
cat: /etc/rancher/k3s/k3s.yaml: No such file or directory
```

这次测试还没跑到业务代码，安装 k3s 的步骤就已经出问题了。我第一反应是想再跑一次看看，但我没有重跑 ShenYu CI 的权限。继续等着，也不知道下一次会不会还是同样的结果。

于是我开始认真看这段 workflow：为什么安装失败了，却只在最后读取文件时才报错？原来写好的重试，又为什么没有运行？

顺着这两个问题，我第一次把 CI 从“提交之后等结果”的黑盒，拆成了自己可以读、可以复现、也可以测试的脚本。最后这次修复单独提交为 [PR #7380](https://github.com/apache/shenyu/pull/7380)，并被合并。对我来说，值得记下来的不只是那几行 Bash，还有从“能不能帮我重跑一下”，到自己拿着日志和复现去讨论问题的过程。

## 先看失败在哪一层，再回头检查代码

以前看到 CI 红了，我通常会先打开自己的 diff，找是不是哪里写错了。但这次日志指向的是环境初始化：workflow 要先安装 k3s，再读取 `/etc/rancher/k3s/k3s.yaml` 作为 kubeconfig。这个文件不存在，后面的 Kubernetes 测试自然也就跑不起来。

CI 里的失败不只有业务代码这一种来源。Runner、下载源、网络、Docker 和依赖仓库，都可能影响一次运行。我开始意识到，红灯只是结果，**先弄清楚它停在哪一步，才知道该往哪里找。**

继续读 workflow 时，我发现它其实已经有重试逻辑。把和问题有关的部分摘出来，大致是这样：

```bash
# 原 workflow 的关键结构，省略版本参数和失败日志
install_k3s() {
  curl -sfL https://get.k3s.io | sh -
}

for attempt in 1 2 3; do
  if install_k3s; then
    break
  fi
  # 第三次失败时退出；前两次分别等待 15、30 秒
done
```

第一次失败等 15 秒，第二次失败等 30 秒，第三次再失败就退出。看起来并没有少写重试。

但实际那次 `Install k8s` 很快就结束了，日志里没有 `k3s install failed on attempt 1`，也没有等到第一次重试的 15 秒。[Issue #7379](https://github.com/apache/shenyu/issues/7379) 里记录的时间和日志，都和“正常执行过重试”对不上。

这让我换了一个方向：会不会不是循环没写好，而是它根本没有收到“安装失败”这个信号？

## 写了重试，不代表失败真的会进入重试

问题就在那条看起来很普通的命令里：

```bash
curl -sfL https://get.k3s.io | sh -
```

我原来很容易把它理解成“下载脚本，然后执行脚本”，所以直觉上下载失败，整条命令也应该失败。

但没有开启 `pipefail` 时，Bash 默认取 pipeline **最后一个命令的退出状态**。如果 `curl` 下载失败，没有把脚本送给后面的 `sh -`，`sh` 读到空输入，什么也没执行，却可以正常退出。

结果就是：前面的 `curl` 失败，后面的 `sh` 返回 `0`，整条 pipeline 也返回 `0`。`if install_k3s` 看到的是成功，于是直接 `break`，直到后面的 `cat` 才发现 kubeconfig 根本不存在。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; text-align:left; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 1 · 同样一次下载失败，退出状态决定了重试能不能接住它</figcaption>
<div tabindex="0" role="region" aria-label="图 1 · 下载失败的状态传递对比" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg class="shenyu-flow" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="shenyu7380-pipeline-title shenyu7380-pipeline-desc" viewBox="0 0 640 488" style="display:block; width:100%; min-width:520px; height:auto; font-family:var(--font-sans); --flow-node:light-dark(#e8f3fc,#142b3e); --flow-condition:light-dark(#f4f9fe,#102333); --flow-ink:light-dark(#235e89,#c0def4); --flow-border:light-dark(#d0e0ed,#355167); --flow-line:light-dark(#8e959d,#8295a6); --flow-warn:light-dark(#fff3d7,#352918); --flow-warn-ink:light-dark(#8b5b22,#f3ce8d); --flow-warn-border:light-dark(#e8c98e,#80663a); --flow-success:light-dark(#e5f6eb,#152f26); --flow-success-ink:light-dark(#286447,#a9debf); --flow-success-border:light-dark(#afd3bc,#426c57);">
<title id="shenyu7380-pipeline-title">下载失败的状态传递对比</title>
<desc id="shenyu7380-pipeline-desc">curl 下载失败且没有脚本输出，sh 读取空输入后返回零。未启用 pipefail 时，pipeline 返回零，重试误判为安装成功；启用 pipefail 后，pipeline 返回非零，安装尝试判为失败，进入重试或在次数耗尽后退出。</desc>
<defs><marker id="shenyu7380-pipeline-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<path d="M320 92 V116 Q320 130 306 130 H174 Q160 130 160 144 V178 M320 116 Q320 130 334 130 H466 Q480 130 480 144 V178 M160 250 V294 M480 250 V294 M160 356 V400 M480 356 V400" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu7380-pipeline-arrow)"/>
<rect x="150" y="20" width="340" height="72" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="320" y="50" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">curl 失败，没有输出脚本</text>
<text x="320" y="76" text-anchor="middle" fill="var(--flow-ink)" font-size="13">sh - 读到空输入，仍可返回 0</text>
<rect x="98" y="142" width="124" height="26" rx="13" fill="var(--flow-condition)" stroke="var(--flow-border)"/>
<text x="160" y="160" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5">没有 pipefail</text>
<rect x="418" y="142" width="124" height="26" rx="13" fill="var(--flow-condition)" stroke="var(--flow-border)"/>
<text x="480" y="160" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5">开启 pipefail</text>
<rect x="30" y="180" width="260" height="70" rx="20" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-dasharray="3 4"/>
<text x="160" y="210" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">pipeline 返回 0</text>
<text x="160" y="235" text-anchor="middle" fill="var(--flow-ink)" font-size="13">只看到最后的 sh 成功</text>
<rect x="350" y="180" width="260" height="70" rx="20" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-dasharray="3 4"/>
<text x="480" y="210" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">pipeline 返回非零</text>
<text x="480" y="235" text-anchor="middle" fill="var(--flow-ink)" font-size="13">下载失败被传递出来</text>
<rect x="30" y="296" width="260" height="60" rx="18" fill="var(--flow-warn)" stroke="var(--flow-warn-border)"/>
<text x="160" y="333" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="16" font-weight="500">误判成功，提前 break</text>
<rect x="350" y="296" width="260" height="60" rx="18" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="480" y="333" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">本次尝试失败</text>
<rect x="30" y="402" width="260" height="60" rx="18" fill="var(--flow-warn)" stroke="var(--flow-warn-border)"/>
<text x="160" y="439" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="15">最后读取 kubeconfig 才报错</text>
<rect x="350" y="402" width="260" height="60" rx="18" fill="var(--flow-success)" stroke="var(--flow-success-border)"/>
<text x="480" y="427" text-anchor="middle" fill="var(--flow-success-ink)" font-size="15" font-weight="500">进入重试</text>
<text x="480" y="449" text-anchor="middle" fill="var(--flow-success-ink)" font-size="12.5">次数耗尽时明确退出</text>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">这里展示下载失败且没有脚本输出的路径。小屏可在图内左右滑动。</div>
</figure>

这里也不是只补一个 `set -e` 就能解决。原来的 step 已经用 `bash -e` 运行，安装函数却处在 `if` 的条件判断里；我需要让 pipeline 正确返回失败，再由重试逻辑处理，而不是期待某个 Shell 选项替我判断“安装到底有没有完成”。

还有一个让排查更难的细节：原来的 `curl -sfL` 用了 `-s`，错误信息也被静默了。改成 `curl -sSfL`，加上的 `-S` 才能让错误继续出现在日志里。

那次日志没有留下具体的 curl 错误，所以我没法再倒推出究竟是哪一种下载故障。但“下载失败被误判为成功”这条路径，后来可以用离线测试稳定复现。

我这才意识到，日志最后报错的位置，不一定就是问题最早发生的位置。失败可能已经发生了一会儿，只是没有被正确传下去。

## 退出码是信号，安装结果才是成功条件

开启 `pipefail` 后，下载失败终于能进入重试。但我继续想了一步：如果安装脚本返回 `0`，却没有生成 kubeconfig 呢？循环还是会提前结束，最后仍然读不到文件。

所以这里的成功条件不能只有“命令返回了成功”，还要检查这一步实际需要的结果。最终判断是：

```bash
if install_k3s && [[ -s "${kubeconfig_file}" ]]; then
  break
fi
```

`[[ -s file ]]` 检查文件存在且非空。两边都满足，才结束重试；否则最多尝试三次，前两次分别等待 15、30 秒，最后明确报错退出。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; text-align:left; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 2 · 重试判断的，不只是命令有没有返回 0</figcaption>
<div tabindex="0" role="region" aria-label="图 2 · k3s 安装的成功条件与重试" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg class="shenyu-flow" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="shenyu7380-retry-title shenyu7380-retry-desc" viewBox="0 0 640 526" style="display:block; width:100%; min-width:520px; height:auto; font-family:var(--font-sans); --flow-node:light-dark(#e8f3fc,#142b3e); --flow-condition:light-dark(#f4f9fe,#102333); --flow-ink:light-dark(#235e89,#c0def4); --flow-border:light-dark(#d0e0ed,#355167); --flow-line:light-dark(#8e959d,#8295a6); --flow-warn:light-dark(#fff3d7,#352918); --flow-warn-ink:light-dark(#8b5b22,#f3ce8d); --flow-warn-border:light-dark(#e8c98e,#80663a); --flow-success:light-dark(#e5f6eb,#152f26); --flow-success-ink:light-dark(#286447,#a9debf); --flow-success-border:light-dark(#afd3bc,#426c57);">
<title id="shenyu7380-retry-title">k3s 安装的成功条件与重试</title>
<desc id="shenyu7380-retry-desc">执行安装后，同时检查安装命令成功和 kubeconfig 文件存在且非空。满足条件则复制 kubeconfig 并结束安装脚本。否则判断尝试次数，未满三次时等待十五或三十秒再试，第三次仍失败则返回非零。</desc>
<defs><marker id="shenyu7380-retry-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<path d="M260 84 V122 M420 160 H450 M260 200 V250 M420 282 H506 Q520 282 520 296 V360 M260 314 V360" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu7380-retry-arrow)"/>
<path d="M100 405 H64 Q44 405 44 385 V70 Q44 52 62 52 H117" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#shenyu7380-retry-arrow)"/>
<rect x="120" y="20" width="280" height="64" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="260" y="48" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">执行 install_k3s</text>
<text x="260" y="71" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5">pipefail 传递失败，curl -S 留下错误</text>
<rect x="100" y="124" width="320" height="76" rx="20" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-dasharray="3 4"/>
<text x="260" y="155" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">安装成功，而且 kubeconfig 非空？</text>
<text x="260" y="181" text-anchor="middle" fill="var(--flow-ink)" font-size="13">install_k3s &amp;&amp; [[ -s file ]]</text>
<text x="436" y="148" text-anchor="middle" fill="var(--flow-ink)" font-size="13">是</text>
<rect x="452" y="124" width="168" height="76" rx="20" fill="var(--flow-success)" stroke="var(--flow-success-border)"/>
<text x="536" y="149" text-anchor="middle" fill="var(--flow-success-ink)" font-size="14" font-weight="500">结束重试</text>
<text x="536" y="171" text-anchor="middle" fill="var(--flow-success-ink)" font-size="12.5">复制配置</text>
<text x="536" y="190" text-anchor="middle" fill="var(--flow-success-ink)" font-size="11.5">install -m 600</text>
<rect x="236" y="211" width="48" height="26" rx="13" fill="var(--flow-condition)" stroke="var(--flow-border)"/>
<text x="260" y="229" text-anchor="middle" fill="var(--flow-ink)" font-size="13">否</text>
<rect x="100" y="252" width="320" height="62" rx="18" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-dasharray="3 4"/>
<text x="260" y="289" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">已经是第三次尝试？</text>
<rect x="454" y="267" width="48" height="26" rx="13" fill="var(--flow-condition)" stroke="var(--flow-border)"/>
<text x="478" y="285" text-anchor="middle" fill="var(--flow-ink)" font-size="13">是</text>
<rect x="236" y="323" width="48" height="26" rx="13" fill="var(--flow-condition)" stroke="var(--flow-border)"/>
<text x="260" y="341" text-anchor="middle" fill="var(--flow-ink)" font-size="13">否</text>
<rect x="100" y="362" width="320" height="86" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="260" y="396" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">记录失败，等待后再试</text>
<text x="260" y="422" text-anchor="middle" fill="var(--flow-ink)" font-size="13">第一次 15 秒 / 第二次 30 秒</text>
<rect x="430" y="362" width="190" height="86" rx="20" fill="var(--flow-warn)" stroke="var(--flow-warn-border)"/>
<text x="520" y="396" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="16" font-weight="500">记录最终失败</text>
<text x="520" y="422" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="13">exit 1，不再复制配置</text>
<text x="45" y="482" fill="var(--flow-ink)" font-size="12.5" opacity=".8">只在前两次失败后等待，最多执行三次安装。</text>
</svg>
</div>
</figure>

最终的改动没有继续堆在 workflow 的 `run:` 里，而是抽成 `.github/scripts/install-k3s.sh`。workflow 调用脚本，脚本负责明确的成功判断、重试和失败日志。

另外，原来会把 kubeconfig 直接打印到 CI 日志，再用 `cp` 复制到用户目录。这次也去掉了打印，改用 `install -m 600` 写到 job 用户的 `.kube/config`。后续命令仍然能读取，不需要把配置内容留在日志里。

以前我写这类脚本，容易把“命令执行完了”当作“事情完成了”。这次让我开始多问一句：**这一步完成以后，下一步需要的东西，真的已经有了吗？**

## 让失败稳定发生，比等一次绿灯更有用

修复方向有了，但怎么确认它真的解决了问题？我没有重跑权限，网络失败也不是想遇到就能遇到。即使下一次 CI 变绿，也不等于下载失败这条分支被验证过。

后来我没有继续等网络出错，而是在临时目录里放了一个假的 `curl`，把这个目录排到 `PATH` 最前面。安装脚本调用的名字还是 `curl`，实际执行的却是测试准备好的 stub。

想模拟下载失败，就让它直接返回非零，并且不输出安装脚本：

```bash
#!/bin/sh
# 模拟 curl 下载失败的最小片段，不访问网络
exit 22
```

想模拟“安装器成功，但没有产生 kubeconfig”，就让假的 curl 输出一段只会 `exit 0` 的安装脚本。这样，下载和执行可以看起来都成功，但我故意不提供安装结果。

原来难以等到的故障，就变成了我每次运行都能制造的条件。再把相同输入交给旧逻辑和修复后的逻辑，差别就不再是猜测了。

最后的 `.github/scripts/install-k3s-test.sh` 覆盖了四种情况：

| 测试输入 | 安装尝试次数 | 等待次数 | 预期结果 |
| --- | --- | --- | --- |
| curl 下载失败 | 3 | 2 | 明确失败，不复制配置 |
| 安装器返回成功，但没有 kubeconfig | 3 | 2 | 明确失败，不复制配置 |
| 安装器生成空的 kubeconfig | 3 | 2 | 明确失败，不复制配置 |
| 安装器成功，并生成非空 kubeconfig | 1 | 0 | 成功，复制配置 |

测试里的 `sleep` 也换成了 stub，记录调用而不真的等待，所以不需要每个失败场景都花 45 秒。成功场景还检查复制后的内容和 `600` 权限，失败场景则检查最终报错，以及没有写出目标配置。

这是我第一次比较认真地模拟 CI 故障。让我印象深的不是 stub 写得多复杂，而是思路变了：不再等一次运行替我证明结果，而是自己控制输入，看看失败会不会按预期被处理。

## 把 workflow 拆开，CI 就没那么像黑盒了

排查过程中，我原来闲置的阿里云开发机也派上了用场。我开始把它当作自己的 Linux 测试环境，用来跑从 workflow 里拆出来的 Shell 命令，模拟 CI 的执行过程。

以前遇到这类问题，很容易变成：改一点，push，等 GitHub Actions，再看结果。等待久倒还不是最烦的，主要是有时等完了，还是不知道自己的判断对不对。

把脚本拿到自己能控制的环境里以后，我就可以先看退出码、准备缺失文件的场景、确认重试次数，再提交修改。不需要每调整一处判断，都等整个项目重新跑一遍。

我没有把自己的服务器当成 GitHub Runner 的完整替代品。它对这次排查最有用的地方，是让我能把一个具体的失败条件单独拿出来，反复看它怎么执行。

当我开始这样读 workflow，CI 就没以前那么神秘了。至少其中的 `run:` 不再只是页面上的一段配置，而是一组我也能拿出来运行、检查和测试的命令。

## 准备好证据，再去找维护者讨论

还有一件事，我自己挺想保留下来：这次是我第一次主动联系 ShenYu 的维护者讨论 CI 问题。

当时我已经有了初步判断，但没有重跑权限。我犹豫了一阵，还是把失败的位置、为什么怀疑 k3s 下载，以及目前还不能确定的地方简单说明了一下，想确认这种环境问题能不能单独提出来处理。

对方回复的大意是，如果是 k3s 环境的问题，可以发出来；有其他明确的问题，也可以单独提 PR。后来还问我是在读书还是已经工作了，我说自己还是学生。他也鼓励我继续在社区里多看看、多处理一些问题。

对别人来说，这可能只是很普通的一次交流。但对当时的我，它确实减轻了不少心理压力。以前想到找维护者，我会先担心：自己是不是懂得太少，问题是不是太小，会不会判断错了，又会不会打扰别人。

这次让我发现，正常讨论一个工程问题，并不需要先把整个项目都摸透。先自己查过，把日志、判断和能复现的部分准备好，再把不确定的地方说清楚，就已经比一句“CI 挂了”更容易继续讨论。

后来 [Aias00 的 review](https://github.com/apache/shenyu/pull/7380#pullrequestreview-5372312366) 也明确认可了这个方向：把安装器抽出来，加上非空 kubeconfig 判断和专门的重试测试，让原本隐含在 workflow 里的行为变得可以验证。

我开始觉得，证据不仅是用来证明自己没改错，也能让别人更快理解问题，和我一起把事情往前推进。

## 看 CI 绿灯，也要看哪些步骤真正跑过

这次还有一个容易忽略的地方。PR 修改的是 `.github/**`，相关 workflow 会启动，新增的离线测试也会执行，但真实的 `Install k8s` 仍受 path filter 和 case resolver 控制。

也就是说，离线测试通过，说明这些失败输入下的重试行为符合预期；真实下载和安装是否执行过，还要看 `run_k8s_examples` 的输出，不能只看页面最上面的绿勾。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; text-align:left; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 3 · 离线重试测试与真实安装，是两条不同的验证路径</figcaption>
<div tabindex="0" role="region" aria-label="图 3 · 离线测试与真实安装的执行范围" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg class="shenyu-flow" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="shenyu7380-scope-title shenyu7380-scope-desc" viewBox="0 0 640 394" style="display:block; width:100%; min-width:520px; height:auto; font-family:var(--font-sans); --flow-node:light-dark(#e8f3fc,#142b3e); --flow-condition:light-dark(#f4f9fe,#102333); --flow-ink:light-dark(#235e89,#c0def4); --flow-border:light-dark(#d0e0ed,#355167); --flow-line:light-dark(#8e959d,#8295a6); --flow-warn:light-dark(#fff3d7,#352918); --flow-warn-ink:light-dark(#8b5b22,#f3ce8d); --flow-warn-border:light-dark(#e8c98e,#80663a); --flow-success:light-dark(#e5f6eb,#152f26); --flow-success-ink:light-dark(#286447,#a9debf); --flow-success-border:light-dark(#afd3bc,#426c57);">
<title id="shenyu7380-scope-title">离线测试与真实安装的执行范围</title>
<desc id="shenyu7380-scope-desc">同一 workflow 中，离线重试测试不受 k8s case 条件限制，使用 curl 和 sleep stub 验证四个场景。真实安装受路径过滤和 case resolver 控制，run_k8s_examples 为 true 才安装。只修改 .github 的本次 PR 执行离线测试，但跳过真实安装。</desc>
<defs><marker id="shenyu7380-scope-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<path d="M160 114 V154 M480 114 V154 M160 230 V274 M480 230 V274" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" marker-end="url(#shenyu7380-scope-arrow)"/>
<rect x="20" y="22" width="280" height="92" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="160" y="55" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">离线重试测试</text>
<text x="160" y="81" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5">install-k3s-test.sh</text>
<text x="160" y="101" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5" opacity=".8">不受 k8s case 条件限制</text>
<rect x="340" y="22" width="280" height="92" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="480" y="55" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">真实 Install k8s</text>
<text x="480" y="81" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5">install-k3s.sh</text>
<text x="480" y="101" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5" opacity=".8">受路径与 case resolver 控制</text>
<rect x="20" y="156" width="280" height="74" rx="18" fill="var(--flow-condition)" stroke="var(--flow-border)"/>
<text x="160" y="186" text-anchor="middle" fill="var(--flow-ink)" font-size="15" font-weight="500">curl / sleep stub</text>
<text x="160" y="211" text-anchor="middle" fill="var(--flow-ink)" font-size="13">四种输入，不需要真实网络</text>
<rect x="340" y="156" width="280" height="74" rx="18" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-dasharray="3 4"/>
<text x="480" y="186" text-anchor="middle" fill="var(--flow-ink)" font-size="14.5" font-weight="500">run_k8s_examples == true</text>
<text x="480" y="211" text-anchor="middle" fill="var(--flow-ink)" font-size="13">满足条件才下载与安装 k3s</text>
<rect x="20" y="276" width="280" height="88" rx="20" fill="var(--flow-success)" stroke="var(--flow-success-border)"/>
<text x="160" y="310" text-anchor="middle" fill="var(--flow-success-ink)" font-size="16" font-weight="500">本次 PR 执行了</text>
<text x="160" y="338" text-anchor="middle" fill="var(--flow-success-ink)" font-size="13">验证失败处理与成功路径</text>
<rect x="340" y="276" width="280" height="88" rx="20" fill="var(--flow-warn)" stroke="var(--flow-warn-border)"/>
<text x="480" y="310" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="16" font-weight="500">本次 PR 跳过了</text>
<text x="480" y="338" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="13">只修改 .github/** 不触发安装</text>
</svg>
</div>
</figure>

我把这个范围也写进了 PR 描述。它让我养成了一个更具体的检查习惯：不只看任务是否通过，也看看自己关心的那一步，到底是执行了，还是被跳过了。

## 从等人重跑，到自己解释它为什么失败

如果只看最终修改，这个 PR 是三个文件：安装脚本、离线测试脚本，以及调用它们的 workflow。它没有改 Java 业务逻辑，但排查过程中，我对“CI 配置”的看法确实变了一点。

以前 `.github/workflows/*.yml` 更像项目附带的配置。现在我会留意，它里面一样有分支、退出状态、成功条件和外部依赖，也会有“代码看起来写了，实际上却没有生效”的问题。

这次最开始，我只是希望有人能帮我再跑一次。后来我能说清楚：失败停在哪里，为什么怀疑 pipeline，怎样不依赖真实网络复现，以及修复以后要检查什么。

对我来说，这种变化比“又合并了一个 PR”更值得记下来。没有重跑权限时，我也不一定只能等；先把能控制的部分拿出来，准备好证据，再去讨论剩下的问题，事情就能继续往前走。

以后看到 CI 红灯，我还是会检查自己的代码，但会先问一句：**它到底失败在哪一层？** 如果重新跑一次就绿了，我也想再弄清楚，第一次失败的信号为什么没有早点出现在日志里。

这次算是我真正开始接触 CI 工程的起点。不是一下子懂了所有 workflow，而是终于开始把它当成一段自己也需要读懂、测试和维护的程序。

## 相关链接

- [Issue #7379 · k3s 安装重试被提前跳过](https://github.com/apache/shenyu/issues/7379)
- [PR #7380 · 处理下载失败与缺失 kubeconfig 的重试](https://github.com/apache/shenyu/pull/7380)
- [PR #7289 · 这次排查的起点](https://github.com/apache/shenyu/pull/7289)
- [合并版本的安装脚本](https://github.com/apache/shenyu/blob/51ec9761092733b85481eb67fee7a44d69354710/.github/scripts/install-k3s.sh)
- [合并版本的离线测试](https://github.com/apache/shenyu/blob/51ec9761092733b85481eb67fee7a44d69354710/.github/scripts/install-k3s-test.sh)
- [Bash 手册 · Pipeline 的退出状态](https://www.gnu.org/software/bash/manual/html_node/Pipelines)
- [curl 手册 · silent 与 show-error](https://curl.se/docs/manpage.html)
