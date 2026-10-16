---
title: '文件已经下载，为什么 --out 还是空的：BrowserSkill 下载目录冲突修复'
description: 'BrowserSkill 和 Chrono 同时处理下载时，浏览器已经保存了文件，CLI 却没能生成指定输出。记录 PR #362 中对目录边界、失败清理和真实浏览器验证的排查与取舍。'
pubDate: 2026-10-16T23:44:56+08:00
category: open-source
tags:
  - BrowserSkill
  - TypeScript
  - Rust
  - 浏览器扩展
  - 文件传输
draft: false
postType: metaOnly
---

浏览器的下载列表里已经有文件，为什么 `bsk download --out ...` 还没有生成指定输出？

这次在 BrowserSkill 里处理的问题，比“下载失败”这几个字要绕一点。用户在 [Issue #361](https://github.com/Tencent/BrowserSkill/issues/361) 中反馈：同时安装 Chrono 下载管理器后，BrowserSkill 建议的下载目录被覆盖了。文件仍然下载下来，却没有进入原本按调用划分的目录。

表面上看，只是文件少套了一层文件夹。但沿着扩展、daemon 和 CLI 之间的传输链路查下去，这层目录恰好决定了文件能不能交给调用方。

最后，我在 [PR #362](https://github.com/Tencent/BrowserSkill/pull/362) 中补上了最终路径检查和恢复提示。这个 PR 没有让两个下载扩展从此完全兼容，而是把一种原本不够清楚的失败说清楚，同时保留已经下载好的文件，让用户知道接下来该怎么处理。

## 这层目录，决定文件能不能交给调用方

BrowserSkill 让 Agent 通过 CLI 和扩展操作真实浏览器。下载也不是浏览器直接把文件写到 `--out`：浏览器先保存文件，daemon 接收这次下载的内容，CLI 再将内容写到调用方指定的位置。

开始一次传输时，daemon 会生成独立的 transfer ID，并把类似 `BrowserSkill/tr_<id>/` 的相对目录交给扩展。扩展捕获到对应下载后，通过 `onDeterminingFilename` 建议浏览器把文件放进去。

daemon 导入文件时，还会检查实际路径的父目录是否以本次传输的专属目录结尾，之后才继续检查文件、读取内容并准备交给 CLI。

所以它不只是为了让 Downloads 看起来整齐，也不能被理解成“找到一个同名文件就拿来用”。**文件落在别处，即使文件名和内容都像是对的，也没有满足这条导入路径的要求。**

Issue 里最初关注的是目录分组丢失。我需要继续确认的是：目录丢了以后，后面的传输还能不能成立。追到 daemon 的检查后，我才把这两件事分开：扩展能拿到真实保存路径，不代表 CLI 能把它变成请求的 `--out`。

## 调用了 suggest，不代表浏览器会采用这个建议

为什么扩展已经指定了目录，文件却还能跑到外面？

BrowserSkill 和 Chrono 都可以参与下载文件名的确定。按照 [Chrome 下载 API 的规则](https://developer.chrome.com/docs/extensions/reference/api/downloads#event-onDeterminingFilename)，多个扩展同时提供命名建议时，会按安装顺序选择其中一个，最近安装的扩展提供的建议优先。

因此，BrowserSkill 调用了 `suggest(...)`，只说明它提出了建议，并不能证明最后保存的文件采用了这个路径。竞争扩展可能覆盖建议，浏览器也可能拒绝建议的文件名，或者用户选择了其他保存位置。

我把检查放在下载完成之后，读取最终的 `DownloadItem.filename`，再核对它的父目录。这里检查的是实际结果，不是之前发出去的建议。

路径处理也要同时识别 `/` 和 Windows 的 `\`，取父目录的末尾路径段进行比较，而不是只看 basename，更不是搜索路径里有没有出现过 `BrowserSkill` 这个词。

## 明确报错，但不替用户处理目录外的文件

发现路径不匹配后，扩展返回的关键信息是：

```json
{
  "reason": "download_path_mismatch",
  "effect_state": "committed",
  "phase": "download"
}
```

这里的 `committed` 容易让人误会。它不是说 CLI 已经成功写出了目标文件，而是说浏览器下载已经发生，不能把这次失败当成“什么都没有做”。

这也影响失败后的清理。原来下载捕获失败时，会尝试清理已经认领的下载。但现在遇到的是：文件已经完成，最后的位置却不在本次专属目录里。它可能是另一个扩展安排的，也可能是用户主动选的。仅凭这次命令没有完成，就把它删除，并不合适。

所以这条分支在返回错误前设置了保留标记，让 `finally` 跳过对这个下载文件的取消和删除。事件监听、计时器等清理仍然继续，不是出了错就什么都不收拾。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; text-align:left; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 1 · 下载完成之后，再决定是否可以交给下一层</figcaption>
<div tabindex="0" role="region" aria-label="图 1 · BrowserSkill 下载路径核对" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg class="browserskill-flow" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="bs362-path-title bs362-path-desc" viewBox="0 0 640 660" style="display:block; width:100%; min-width:540px; height:auto; font-family:var(--font-sans); --flow-node:light-dark(#e8f3fc,#142b3e); --flow-condition:light-dark(#f4f9fe,#102333); --flow-ink:light-dark(#235e89,#c0def4); --flow-border:light-dark(#d0e0ed,#355167); --flow-line:light-dark(#8e959d,#8295a6); --flow-success:light-dark(#e5f6eb,#152f26); --flow-success-ink:light-dark(#286447,#a9debf); --flow-success-border:light-dark(#afd3bc,#426c57); --flow-warn:light-dark(#fff3d7,#352918); --flow-warn-ink:light-dark(#8b5b22,#f3ce8d); --flow-warn-border:light-dark(#e8c98e,#80663a);">
<title id="bs362-path-title">BrowserSkill 下载完成后的路径核对</title>
<desc id="bs362-path-desc">只展示已完成且已归属到本次捕获的浏览器下载。核对最终文件父目录是否匹配本次 BrowserSkill transfer 目录。匹配时返回捕获结果，后续仍要经过 daemon 导入与 CLI 写出；不匹配时保留目录外文件，返回 download_path_mismatch、effect_state committed。其他必要的监听器与触发清理仍执行，不表示完整任务已经成功。</desc>
<defs><marker id="bs362-path-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<g fill="none" stroke="var(--flow-line)" stroke-width="1.2" marker-end="url(#bs362-path-arrow)"><path d="M320 92 V132"/><path d="M320 220 V256 Q320 266 310 266 H164 Q154 266 154 276 V316"/><path d="M320 220 V256 Q320 266 330 266 H476 Q486 266 486 276 V316"/><path d="M486 412 V466"/></g>
<rect x="154" y="20" width="332" height="72" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="320" y="50" text-anchor="middle" fill="var(--flow-ink)" font-size="17" font-weight="500">浏览器下载已完成</text>
<text x="320" y="76" text-anchor="middle" fill="var(--flow-ink)" font-size="13">读取最终 DownloadItem.filename</text>
<rect x="112" y="134" width="416" height="86" rx="22" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-dasharray="3 4"/>
<text x="320" y="168" text-anchor="middle" fill="var(--flow-ink)" font-size="17" font-weight="500">父目录匹配本次 transfer 目录？</text>
<text x="320" y="196" text-anchor="middle" fill="var(--flow-ink)" font-size="14">BrowserSkill/tr_&lt;id&gt;/</text>
<rect x="125" y="280" width="58" height="26" rx="13" fill="var(--flow-condition)" stroke="var(--flow-border)"/>
<text x="154" y="298" text-anchor="middle" fill="var(--flow-ink)" font-size="13">匹配</text>
<rect x="449" y="280" width="74" height="26" rx="13" fill="var(--flow-condition)" stroke="var(--flow-border)"/>
<text x="486" y="298" text-anchor="middle" fill="var(--flow-ink)" font-size="13">不匹配</text>
<rect x="24" y="318" width="260" height="94" rx="20" fill="var(--flow-success)" stroke="var(--flow-success-border)"/>
<text x="154" y="352" text-anchor="middle" fill="var(--flow-success-ink)" font-size="17" font-weight="500">返回捕获结果</text>
<text x="154" y="380" text-anchor="middle" fill="var(--flow-success-ink)" font-size="13">后续仍需 daemon 导入</text>
<text x="154" y="400" text-anchor="middle" fill="var(--flow-success-ink)" font-size="13">与 CLI 写出指定文件</text>
<rect x="356" y="318" width="260" height="94" rx="20" fill="var(--flow-warn)" stroke="var(--flow-warn-border)"/>
<text x="486" y="352" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="17" font-weight="500">保留目录外的文件</text>
<text x="486" y="380" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="13">不取消、不删除这次下载</text>
<text x="486" y="400" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="13">其余必要清理继续执行</text>
<rect x="338" y="468" width="296" height="104" rx="20" fill="var(--flow-warn)" stroke="var(--flow-warn-border)"/>
<text x="486" y="501" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="15" font-weight="500">download_path_mismatch</text>
<text x="486" y="529" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="14">effect_state: committed</text>
<text x="486" y="554" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="13">未生成请求的 --out 文件</text>
<text x="320" y="623" text-anchor="middle" fill="var(--flow-ink)" font-size="12">此图省略下载归属判断、未完成下载及其他失败路径</text>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">窄屏可在图内左右滑动查看。</div>
</figure>

CLI 侧的提示也不应该直接断言“就是 Chrono 的问题”。它会引导用户先到浏览器下载列表找文件，再检查竞争扩展、文件名被拒绝或保存位置变化。需要重试时，先暂停相关下载接管，并确认自己仍然需要生成 `--out`。

文件已经落盘了，让用户看见这个事实，比简单地告诉他“失败了，再试一次”更有用。

## 一个绕开冲突的开关，并不能补齐后面的传输

Issue 还提出了一个可选想法：既然会抢文件名，能不能提供设置，让 BrowserSkill 不再建议目录？

这次没有实现它。因为跳过建议以后，文件仍然可能落在专属目录外，daemon 的导入检查也仍然存在。只关掉前面的建议，不能让后面的内容传输自动成立。

我选择先补排障文档、最终路径检查和明确的错误提示，不为了完成一个可选请求，把文件导入边界一起放宽。

文档里也保留了调整扩展安装顺序的绕开方式，但没有把它写成长期兼容方案。让 BrowserSkill 的建议暂时胜出，并不代表冲突机制消失；另一个扩展以后更新，结果还可能反过来。

## 维护者要看的，是两个扩展一起运行时的结果

提交后，维护者在 [Review 评论](https://github.com/Tencent/BrowserSkill/pull/362#issuecomment-5893990975) 中认可了最终路径检查和恢复提示的方向，但也要求补两件事：修正新测试的格式，以及在真实 Windows Edge 中同时安装 BrowserSkill 和 Chrono，验证三种情况。

格式问题很直接。另一项则要求把 CLI、daemon、扩展和浏览器真正接起来，不能只靠测试里的模拟下载事件。

于是，我从这个 PR 的源码构建 CLI、daemon 和扩展，用隔离的 Edge 配置测试。环境是 Windows 11、Edge `154.0.4258.37` 和 Chrono `0.13.12`。BrowserSkill 源码里的版本号仍为 `0.3.1`，但这里使用的是包含修复的 PR 构建，不是把已发布的旧版本当成验证对象。

我先做没有 Chrono 的正常下载，再让后安装的 Chrono 覆盖目录建议，最后关闭 Chrono，用相同的 session、tab 和输出路径重复命令。

| 场景 | 实际观察到的结果 |
| --- | --- |
| 没有 Chrono 的正常下载 | 命令成功，指定输出包含预期内容 |
| Chrono 覆盖目录建议 | 命令返回 `download_path_mismatch` 和 `committed`，没有生成请求的输出；浏览器显示下载完成，目录外文件仍然存在 |
| 关闭 Chrono 后重复相同命令 | 输出成功生成，内容与源附件的 SHA-256 一致；前一次冲突留下的文件也还在 |

这样验证下来，检查的就不只是“新增的判断分支会返回一个错误码”，还包括出错时有没有误删文件，以及解除冲突后原有链路能否继续工作。我把环境、步骤和结果补进 PR，并在[回应](https://github.com/Tencent/BrowserSkill/pull/362#issuecomment-5913761818)中逐项说明。

实际测试还遇到另一个行为：普通 HTTP 附件被 Chrono 取消后，用相同 URL 重新发起下载，导致归属变得不明确。这时返回的是 `download_capture_failed` 和 `unknown`，还没有走到最终路径检查。

这和“同一次下载完成，但目录建议被覆盖”不是同一条路径。我把它作为后续兼容问题记录下来，没有把这次 PR 写成已经解决了下载管理器的所有接管行为。

## 失败不等于什么都没发生，清理也不是删得越彻底越好

这次修改让我更在意的，是一个失败结果里究竟包含了多少已经发生的事情。

如果只看命令返回值，下载就是失败了。但换到浏览器那一侧，文件已经保存好了。对用户来说，这个文件可能仍然有用；对 Agent 来说，下一步也不该默认“刚才没有效果，可以直接重试”。

我意识到，错误信息不只是给人解释原因，也会影响后续动作。说清楚文件在哪里找、为什么没有生成指定输出、重试之前应该检查什么，本身就是修复的一部分。

失败清理也一样。清掉自己能确认负责的临时状态，和把所有看起来相关的文件都删除，不是一回事。这次我需要守住的，恰恰是那个“不该顺手处理”的目录外文件。

维护者要求补真实浏览器验证，也让我把目光从新增的几行判断移到了整条链路上：单元测试能确认分支逻辑，两个扩展同时运行时，事件顺序、最终路径和文件是否留下来，还得真的接起来看。

最后这个 PR 的范围并不大，但它留下了一个我想继续带着的问题：**准备告诉调用方“失败了”之前，我有没有把已经发生的效果，以及自己有权清理的范围，一起想清楚？**
