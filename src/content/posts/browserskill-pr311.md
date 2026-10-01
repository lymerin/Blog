---
title: 'Issue 已经修好了，为什么还要补一个 PR：BrowserSkill 后台输入的状态加固'
description: '原本想修一个后台点击失效的 Issue，却发现它早已解决。继续读代码后，我追到了临时输入唤醒与持久后台 lease 的交互边界，也在 Review 和故障注入中重新理解了状态所有权。'
pubDate: 2026-10-01T15:47:25+08:00
tags:
  - BrowserSkill
  - TypeScript
  - CDP
  - 浏览器自动化
  - 状态一致性
draft: false
postType: metaOnly
---

这次贡献，是从一个已经修好的 Issue 开始的。

我最初在 Tencent BrowserSkill 的 Issue 列表里看到 [#242](https://github.com/Tencent/BrowserSkill/issues/242)：后台执行点击时，CLI 返回成功，页面却没有收到任何点击事件。对自动操作浏览器的 Agent 来说，这比直接报错更麻烦——它以为自己已经点到了，可能就会沿着这个错误的前提继续操作。

我本来准备从这里入手。但查看当前 `main` 后发现，原问题已经由 [PR #261](https://github.com/Tencent/BrowserSkill/pull/261) 修复了。

按以前的想法，我可能会换一个还没解决的 Issue。这次我又往下读了一些：当初为什么这样修？现在的命令还是沿着同一条路径执行吗？结果发现，项目还引入了另一套持久后台运行机制，两层逻辑都会控制同一个浏览器状态，却没有完全对齐彼此的所有权。

最后，这段排查变成了 [PR #311](https://github.com/Tencent/BrowserSkill/pull/311)。它不是重新修一遍 #242，而是为已有修复补上一层组合场景下的保护。这个过程里，我第一次比较具体地体会到：**一个 Issue 标记为已解决，不代表围绕它的设计就不需要继续理解了。**

## 已修复的 Issue，也值得先弄清楚它为什么被修好

[BrowserSkill](https://github.com/Tencent/BrowserSkill) 让 AI Agent 通过 CLI 和浏览器扩展操作真实浏览器。这里讨论的后台输入，是让 Agent 在不抢走用户窗口焦点的情况下，仍能完成页面交互。

Issue #242 报告的是 0.2.1：使用 `bsk session start --no-focus` 启动后台 Agent Window 后，再执行点击，CLI 看起来成功了，坐标也正确，但页面没有收到 `pointerdown`、`mousedown`、`mouseup` 或 `click`。

问题在于，CDP 接受输入命令，并不等于页面真的处理了输入。原来的链路缺少对页面输入状态的确认。

后来 #261 加入了 `withInputReady()`。它先读取 `document.visibilityState`；如果页面是 `hidden`，就临时打开 `Emulation.setFocusEmulationEnabled(true)`，等待渲染端准备好，再发送输入，最后清理这次临时开启的状态。

这套输入 readiness 逻辑已经包含在 0.3.0 中，维护者也确认了原问题的修复。因此，我需要先把自己的判断摆正：**接下来发现的问题，不能直接说成“#242 没有修好”。**

## 临时唤醒和持久运行，不能各自管理同一个状态

继续看调用链时，我注意到了 [PR #249](https://github.com/Tencent/BrowserSkill/pull/249) 引入的 `BackgroundExecution`。

它处理的是另一个需求：后台页面加载完成后，一些依赖可见性或 `requestAnimationFrame` 的逻辑仍可能停住。于是，当前 Session 控制的 tab 会获得一份持久后台执行 lease，让相关 override 跨命令保持生效，直到释放控制时再清理。

这里的 lease，可以先理解成“这个 Session 持有这项后台运行状态的控制权”。它与 `withInputReady()` 的生命周期不同：一层只负责一次输入，另一层需要维持多个命令之间的状态。

真实的工具执行也不是直接进入 click handler。`ToolDispatcher` 会先准备后台执行、获取持久 lease，再进入 handler 和 `withInputReady()`。

两套机制各自解决的问题都合理。但放在同一条链路里，就需要回答一个之前没有说清楚的问题：**这个 focus emulation 状态，究竟由谁来关闭？**

## 缓存还记着 ON，浏览器却已经变成 OFF

当时 `withInputReady()` 并不知道当前 Session 是否已经持有 persistent lease。如果 lease 已被持有，页面却仍报告 `hidden`，它就可能继续进入临时唤醒路径。

先发一次 `true`，完成输入，再在 `finally` 里发一次 `false`。对临时逻辑而言，这像是正常收尾；对持久机制而言，却相当于别人把它负责维持的状态关掉了。

更麻烦的是，临时逻辑直接通过 CDP 修改状态，没有同步更新 `BackgroundExecution` 的 applied-state cache。于是控制器内部仍记录着“应该开启，也已经开启”，Chrome 里的实际 override 却已经关闭。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; text-align:left; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 1 · 一次临时清理，让控制器记录与浏览器实际状态分开了</figcaption>
<div tabindex="0" role="region" aria-label="图 1 · 持久状态与临时清理的交互" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg class="browserskill-flow" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="bs311-state-title bs311-state-desc" viewBox="0 0 640 508" style="display:block; width:100%; min-width:520px; height:auto; font-family:var(--font-sans); --flow-node:light-dark(#e8f3fc,#142b3e); --flow-condition:light-dark(#f4f9fe,#102333); --flow-ink:light-dark(#235e89,#c0def4); --flow-border:light-dark(#d0e0ed,#355167); --flow-line:light-dark(#8e959d,#8295a6); --flow-warn:light-dark(#fff3d7,#352918); --flow-warn-ink:light-dark(#8b5b22,#f3ce8d); --flow-warn-border:light-dark(#e8c98e,#80663a);">
<title id="bs311-state-title">持久状态与临时清理的交互</title>
<desc id="bs311-state-desc">获取持久 lease 后，控制器记录和浏览器实际 override 都为开启。在页面仍隐藏的边界状态下，临时 readiness 的清理关闭 override，却没有更新持久控制器的缓存。之后控制器可能跳过重新应用，导致状态持续不一致。</desc>
<defs><marker id="bs311-state-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<path d="M320 86 V126" fill="none" stroke="var(--flow-line)" stroke-width="1.2" marker-end="url(#bs311-state-arrow)"/>
<path d="M320 198 V236" fill="none" stroke="var(--flow-line)" stroke-width="1.2" marker-end="url(#bs311-state-arrow)"/>
<path d="M320 302 V322 Q320 336 306 336 H174 Q160 336 160 350 V362" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linejoin="round" marker-end="url(#bs311-state-arrow)"/>
<path d="M320 322 Q320 336 334 336 H466 Q480 336 480 350 V362" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linejoin="round" marker-end="url(#bs311-state-arrow)"/>
<rect x="150" y="16" width="340" height="70" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="320" y="45" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">获取 persistent lease</text>
<text x="320" y="69" text-anchor="middle" fill="var(--flow-ink)" font-size="13">控制器记录 ON · Chrome override ON</text>
<rect x="110" y="128" width="420" height="70" rx="20" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-dasharray="3 4"/>
<text x="320" y="157" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">页面仍 hidden，进入临时 readiness</text>
<text x="320" y="181" text-anchor="middle" fill="var(--flow-ink)" font-size="13">再次开启 → 等待就绪 → 执行输入</text>
<rect x="150" y="238" width="340" height="64" rx="20" fill="var(--flow-warn)" stroke="var(--flow-warn-border)"/>
<text x="320" y="266" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="16" font-weight="500">临时 finally 发送 OFF</text>
<text x="320" y="288" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="13">没有更新持久控制器的缓存</text>
<rect x="30" y="364" width="260" height="70" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="160" y="393" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">BackgroundExecution：ON</text>
<text x="160" y="417" text-anchor="middle" fill="var(--flow-ink)" font-size="13">desired / applied 记录仍一致</text>
<rect x="350" y="364" width="260" height="70" rx="20" fill="var(--flow-warn)" stroke="var(--flow-warn-border)"/>
<text x="480" y="393" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="16" font-weight="500">Chrome override：OFF</text>
<text x="480" y="417" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="13">实际状态已被临时清理关闭</text>
<text x="320" y="476" text-anchor="middle" fill="var(--flow-ink)" font-size="14">之后 synchronize() 可能依据缓存跳过重新应用</text>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">这里展示 lease 已持有、页面仍 hidden 的边界路径，并非每次后台点击都会发生。小屏可在图内左右滑动。</div>
</figure>

后续 `ensureAttached()` 触发 `BackgroundExecution.synchronize()` 时，它还可能根据缓存与 attachment 的匹配情况提前返回，认为不需要重新应用 override。这样，状态失配就不只是一次临时关闭，还可能影响后面的命令。

不过，读到这里还不能把它说成所有后台页面都会发生的故障。[Review](https://github.com/Tencent/BrowserSkill/pull/311) 特别提醒了这个边界：维护者在 macOS 的 Chrome 153 上观察到，focus emulation 开启后，页面会同步变为 `visible`，最小化窗口也一样。在这个正常路径上，临时 fallback 根本不会被触发。

我需要保护的，是 **lease 已被持有，页面却仍然 `hidden`** 的不一致状态。把这一点说清楚，也让我没有把“代码里存在的交互缺口”直接等同于“每个平台都能自然复现”。

## 持有控制权，不代表页面现在已经准备好

我最先想到的办法，是让输入层知道持久 lease 的存在。因此新增了一个只读查询：

```typescript
ownsBackgroundExecution(sessionId, tabId)
```

最初我的思路很直接：既然后台执行已经有人负责，`withInputReady()` 就不要再临时开关 focus emulation，直接发送输入。

这确实避开了两个 owner 互相覆盖的问题，却把另一层保护一起绕过了。Review 指出：**“已经持有 lease，但页面仍然 hidden”恰恰是不能放心发送输入的时候。** 如果不再检查实际可见性，就可能重新回到“命令成功，页面没处理”的状态。

所以最终实现仍然读取 `document.visibilityState`。ownership 查询回答的是“这个 Session 是否请求持有这份持久 override”，不是“Chrome 此刻一定已经应用了它”。

我原来很容易把这两件事混在一起：有人负责，就应该已经生效。但这次它们之间的差别，正好决定了能不能继续发送输入。

## 状态不确定时，明确失败比假装点到了更重要

最后的处理规则分成了两个维度：先区分是否持有持久 lease，再检查页面是否 `hidden`。

持有 lease 且页面 `visible` 时，可以直接进入输入操作，不做临时 focus toggle，也不额外走 readiness screenshot。持有 lease 却仍 `hidden` 时，则在发送输入前返回明确错误，并且不由输入层私自修改持久状态。

没有持久 lease 的路径，继续保留原来的行为：页面可见就正常输入；页面隐藏时，由 `withInputReady()` 完成有界的临时唤醒、渲染就绪检查、输入和清理。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; text-align:left; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 2 · 先确认谁负责状态，再决定能不能发送输入</figcaption>
<div tabindex="0" role="region" aria-label="图 2 · PR 311 的输入就绪处理规则" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg class="browserskill-flow" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="bs311-ready-title bs311-ready-desc" viewBox="0 0 800 504" style="display:block; width:100%; min-width:680px; height:auto; font-family:var(--font-sans); --flow-node:light-dark(#e8f3fc,#142b3e); --flow-condition:light-dark(#f4f9fe,#102333); --flow-ink:light-dark(#235e89,#c0def4); --flow-border:light-dark(#d0e0ed,#355167); --flow-line:light-dark(#8e959d,#8295a6); --flow-warn:light-dark(#fff3d7,#352918); --flow-warn-ink:light-dark(#8b5b22,#f3ce8d); --flow-warn-border:light-dark(#e8c98e,#80663a); --flow-success:light-dark(#e5f6eb,#152f26); --flow-success-ink:light-dark(#286447,#a9debf); --flow-success-border:light-dark(#afd3bc,#426c57);">
<title id="bs311-ready-title">PR 311 的输入就绪处理规则</title>
<desc id="bs311-ready-desc">持有 lease 和没有 lease 的页面都检查 visibility。两者在 visible 时都正常输入；持有 lease 但 hidden 时不发送输入、不修改 focus emulation，返回 input_not_ready。没有 lease 且 hidden 时保留临时唤醒、渲染就绪检查、输入和清理路径。本图对应 PR 311 的实现，不包含后续自动恢复机制。</desc>
<defs><marker id="bs311-ready-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<path d="M400 82 V102 Q400 118 384 118 H216 Q200 118 200 134 V156" fill="none" stroke="var(--flow-line)" stroke-width="1.2" marker-end="url(#bs311-ready-arrow)"/>
<path d="M400 102 Q400 118 416 118 H584 Q600 118 600 134 V156" fill="none" stroke="var(--flow-line)" stroke-width="1.2" marker-end="url(#bs311-ready-arrow)"/>
<path d="M200 218 V240 Q200 254 186 254 H114 Q100 254 100 268 V318" fill="none" stroke="var(--flow-line)" stroke-width="1.2" marker-end="url(#bs311-ready-arrow)"/>
<path d="M200 240 Q200 254 214 254 H286 Q300 254 300 268 V318" fill="none" stroke="var(--flow-line)" stroke-width="1.2" marker-end="url(#bs311-ready-arrow)"/>
<path d="M600 218 V240 Q600 254 586 254 H514 Q500 254 500 268 V318" fill="none" stroke="var(--flow-line)" stroke-width="1.2" marker-end="url(#bs311-ready-arrow)"/>
<path d="M600 240 Q600 254 614 254 H686 Q700 254 700 268 V318" fill="none" stroke="var(--flow-line)" stroke-width="1.2" marker-end="url(#bs311-ready-arrow)"/>
<rect x="245" y="18" width="310" height="64" rx="20" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-dasharray="3 4"/>
<text x="400" y="56" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">是否持有 persistent lease？</text>
<rect x="171" y="126" width="58" height="25" rx="12.5" fill="var(--flow-condition)" stroke="var(--flow-border)"/>
<text x="200" y="144" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5">持有</text>
<rect x="567" y="126" width="66" height="25" rx="12.5" fill="var(--flow-condition)" stroke="var(--flow-border)"/>
<text x="600" y="144" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5">未持有</text>
<rect x="70" y="158" width="260" height="60" rx="18" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-dasharray="3 4"/>
<text x="200" y="194" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">仍然读取 visibilityState</text>
<rect x="470" y="158" width="260" height="60" rx="18" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-dasharray="3 4"/>
<text x="600" y="194" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">读取 visibilityState</text>
<rect x="63" y="275" width="74" height="28" rx="14" fill="var(--flow-condition)" stroke="var(--flow-border)"/>
<text x="100" y="294" text-anchor="middle" fill="var(--flow-ink)" font-size="13">visible</text>
<rect x="263" y="275" width="74" height="28" rx="14" fill="var(--flow-condition)" stroke="var(--flow-border)"/>
<text x="300" y="294" text-anchor="middle" fill="var(--flow-ink)" font-size="13">hidden</text>
<rect x="463" y="275" width="74" height="28" rx="14" fill="var(--flow-condition)" stroke="var(--flow-border)"/>
<text x="500" y="294" text-anchor="middle" fill="var(--flow-ink)" font-size="13">visible</text>
<rect x="663" y="275" width="74" height="28" rx="14" fill="var(--flow-condition)" stroke="var(--flow-border)"/>
<text x="700" y="294" text-anchor="middle" fill="var(--flow-ink)" font-size="13">hidden</text>
<rect x="15" y="320" width="170" height="146" rx="20" fill="var(--flow-success)" stroke="var(--flow-success-border)"/>
<text x="100" y="358" text-anchor="middle" fill="var(--flow-success-ink)" font-size="16" font-weight="500">正常输入</text>
<text x="100" y="392" text-anchor="middle" fill="var(--flow-success-ink)" font-size="13">不临时开关</text>
<text x="100" y="415" text-anchor="middle" fill="var(--flow-success-ink)" font-size="13">持久 override</text>
<rect x="215" y="320" width="170" height="146" rx="20" fill="var(--flow-warn)" stroke="var(--flow-warn-border)"/>
<text x="300" y="351" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="16" font-weight="500">明确拒绝输入</text>
<text x="300" y="382" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="13">input_not_ready</text>
<text x="300" y="405" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="13">effect_state: none</text>
<text x="300" y="437" text-anchor="middle" fill="var(--flow-warn-ink)" font-size="13">不输入 · 不开关 focus</text>
<rect x="415" y="320" width="170" height="146" rx="20" fill="var(--flow-success)" stroke="var(--flow-success-border)"/>
<text x="500" y="358" text-anchor="middle" fill="var(--flow-success-ink)" font-size="16" font-weight="500">正常输入</text>
<text x="500" y="392" text-anchor="middle" fill="var(--flow-success-ink)" font-size="13">不需要临时唤醒</text>
<rect x="615" y="320" width="170" height="146" rx="20" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="700" y="351" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">临时唤醒</text>
<text x="700" y="382" text-anchor="middle" fill="var(--flow-ink)" font-size="13">ON → 渲染就绪</text>
<text x="700" y="405" text-anchor="middle" fill="var(--flow-ink)" font-size="13">→ 输入</text>
<text x="700" y="437" text-anchor="middle" fill="var(--flow-ink)" font-size="13">最后清理临时状态</text>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">图中规则对应 #311，不包含后续自动恢复。小屏可在图内左右滑动。</div>
</figure>

异常分支返回的结果是：

```json
{
  "code": "cdp_failed",
  "data": {
    "reason": "input_not_ready",
    "effect_state": "none"
  }
}
```

这里的 `effect_state: none` 指的是这次输入没有发送出去，而不是说整个工具调用没有做过任何准备工作。

这次选择的是 fail closed：无法确认页面准备好时，先明确拒绝输入。对于会根据结果继续行动的 Agent，我觉得“没有点到，而且清楚告诉你没有点到”，比返回一个不可靠的成功更有价值。

## 组合问题，要沿着真实执行链路去测试

修复时还有一个让我印象比较深的地方：直接测 click handler，并不一定能测到这个问题。

handler 级测试可以覆盖 `withInputReady()`，但如果绕过 `ToolDispatcher`，前面就没有获取 persistent lease 的步骤。这样测到的，是临时输入逻辑本身，而不是它和持久后台机制相遇后的行为。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; text-align:left; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 3 · 同样进入 handler，前面有没有 lease，测到的是不同的场景</figcaption>
<div tabindex="0" role="region" aria-label="图 3 · Handler 与 Dispatcher 测试链路的区别" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg class="browserskill-flow" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="bs311-test-title bs311-test-desc" viewBox="0 0 640 390" style="display:block; width:100%; min-width:520px; height:auto; font-family:var(--font-sans); --flow-node:light-dark(#e8f3fc,#142b3e); --flow-condition:light-dark(#f4f9fe,#102333); --flow-ink:light-dark(#235e89,#c0def4); --flow-border:light-dark(#d0e0ed,#355167); --flow-line:light-dark(#8e959d,#8295a6); --flow-success:light-dark(#e5f6eb,#152f26); --flow-success-ink:light-dark(#286447,#a9debf); --flow-success-border:light-dark(#afd3bc,#426c57);">
<title id="bs311-test-title">Handler 与 Dispatcher 测试链路的区别</title>
<desc id="bs311-test-desc">没有先获取 lease 的直接 handler 测试，覆盖的是独立输入 readiness 路径；Dispatcher 级测试先准备后台执行、获取 lease，再进入 handler 和 readiness，因此能覆盖两个机制的组合边界。</desc>
<defs><marker id="bs311-test-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--flow-line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<text x="160" y="31" text-anchor="middle" fill="var(--flow-ink)" font-size="14">直接调用 handler，未预先获取 lease</text>
<text x="480" y="31" text-anchor="middle" fill="var(--flow-ink)" font-size="14">这次补充的 Dispatcher 级回归</text>
<path d="M480 108 V138" fill="none" stroke="var(--flow-line)" stroke-width="1.2" marker-end="url(#bs311-test-arrow)"/>
<path d="M160 198 V232" fill="none" stroke="var(--flow-line)" stroke-width="1.2" marker-end="url(#bs311-test-arrow)"/>
<path d="M480 198 V232" fill="none" stroke="var(--flow-line)" stroke-width="1.2" marker-end="url(#bs311-test-arrow)"/>
<path d="M160 294 V326" fill="none" stroke="var(--flow-line)" stroke-width="1.2" marker-end="url(#bs311-test-arrow)"/>
<path d="M480 294 V326" fill="none" stroke="var(--flow-line)" stroke-width="1.2" marker-end="url(#bs311-test-arrow)"/>
<rect x="350" y="48" width="260" height="60" rx="18" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="480" y="73" text-anchor="middle" fill="var(--flow-ink)" font-size="15" font-weight="500">ToolDispatcher</text>
<text x="480" y="94" text-anchor="middle" fill="var(--flow-ink)" font-size="12.5">准备后台执行，先获取持久 lease</text>
<rect x="30" y="140" width="260" height="58" rx="18" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="160" y="175" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">handleClick()</text>
<rect x="350" y="140" width="260" height="58" rx="18" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="480" y="175" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">handleClick()</text>
<rect x="30" y="234" width="260" height="60" rx="18" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-dasharray="3 4"/>
<text x="160" y="270" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">withInputReady()</text>
<rect x="350" y="234" width="260" height="60" rx="18" fill="var(--flow-condition)" stroke="var(--flow-border)" stroke-dasharray="3 4"/>
<text x="480" y="270" text-anchor="middle" fill="var(--flow-ink)" font-size="16" font-weight="500">withInputReady()</text>
<rect x="30" y="328" width="260" height="46" rx="16" fill="var(--flow-node)" stroke="var(--flow-border)"/>
<text x="160" y="357" text-anchor="middle" fill="var(--flow-ink)" font-size="14">覆盖独立 readiness 路径</text>
<rect x="350" y="328" width="260" height="46" rx="16" fill="var(--flow-success)" stroke="var(--flow-success-border)"/>
<text x="480" y="357" text-anchor="middle" fill="var(--flow-success-ink)" font-size="14" font-weight="500">覆盖 lease 与输入的组合边界</text>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">区别不在于测试名称，而在于是否真正包含“先获取 lease，再进入输入层”的前置状态。</div>
</figure>

这次补充的 Dispatcher 回归测试，先确认获取 lease、查询 ownership、读取可见性、发送输入的顺序。随后把页面状态改为 `hidden`，验证返回 `input_not_ready`，既不发送 `Input.dispatchMouseEvent`，也不发送临时 focus 命令。再把可见性改回 `visible`，下一次点击应当能够正常执行。

这组测试检查的是控制流和组件协作，不是让真实浏览器凭空恢复一个已经丢失的 override。把这两种验证分开，我才更清楚每个测试究竟在证明什么。

## 故障注入验证的，是安全失败，而不是自动恢复

Review 还给了一个很具体的验证建议：在接近原 Issue 的环境里，人为制造一次“lease 还在，实际 override 却丢了”的状态。

我最后在 Windows 11、Chrome for Testing 153、DPR 1.5 的环境中启动 `--no-focus` Session，最小化 Agent Window，再从扩展 Service Worker 主动关闭 focus emulation。

这时，Session 仍持有 lease，浏览器里的 override 已关闭，页面报告 `hidden`。执行 `bsk click` 后，返回了 `input_not_ready` 和 `effect_state: none`，页面点击计数保持为零。

它没有恢复点击。这个结果乍看像是“还是没点到”，但对 #311 来说，区别已经很明确：以前可能返回一个假的成功，现在会在输入前拒绝，并告诉调用方页面还没准备好。

当时我把自动恢复拆到了 [Issue #355](https://github.com/Tencent/BrowserSkill/issues/355)。先守住“不确定时不要报告成功”的边界，再讨论由持久状态的管理者恢复 override，而不是让输入层重新越权处理。

补充到写下这篇文章时：恢复丢失 lease 后再尝试隐藏页面输入的后续改动，已通过 [PR #374](https://github.com/Tencent/BrowserSkill/pull/374) 合并。这里记录的规则和故障注入结果，仍然对应我这次 #311 的范围，而不是项目最新版本的全部行为。

## 这次让我学会，在 Fixed 后面多问一步

#311 对我比较特别，是因为我最开始并不是冲着这个改动去的。我只是想找一个自己能处理的 Issue，结果先发现它已经解决，再一点点读到两个状态管理层之间的边界。

以前我更习惯从明确的问题描述开始：找到原因，写修复，等待 Review。这次让我意识到，已有修复同样有值得学习的地方。理解它为什么成立，才能看见项目继续演化之后，哪些前提需要重新确认。

Review 也让我放下了一个很自然、却不够严谨的想法：“既然有 lease，就说明状态已经准备好了。”现在再看到类似代码，我会更愿意分开想：谁声明负责这个状态，谁实际修改它，底层现在又是什么样子。

回头看，这次最具体的收获，是我第一次把 ownership、缓存记录和浏览器实际状态之间的差别，顺着代码、测试和一次故障注入连了起来。

以后再看到一个已修复的 Issue，我想自己会多问一句：

> 这个修复放到项目现在的设计里，它依赖的假设还成立吗？

有时候，继续把这个问题弄明白，本身就能成为下一次贡献的起点。
