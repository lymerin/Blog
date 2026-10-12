---
title: 'Computer Environment：Agent 的动作在哪里真正执行？'
description: '打开 Agent Loop 中的工具执行环节，理解 Shell、文件系统、进程、容器和外部服务怎样承载行动，以及环境结果怎样成为模型的下一次观察。'
pubDate: 2026-10-12T08:40:00+08:00
category: notes
tags: [Agent, OpenAI, Shell, Container, 学习笔记]
draft: false
postType: metaOnly
---

[上一篇 Agent Loop](/zh-cn/posts/codex-agent-loop/)把执行过程压成了一个循环：模型提出动作，程序执行工具，再把结果交回模型。其中的 `runTool(call)` 还只是一个函数名。这一篇把它打开：读取文件时读的是哪里的文件，运行测试时谁在执行，修改后的代码又保存在哪里？

OpenAI 的 [《From model to agent: Equipping the Responses API with a computer environment》](https://openai.com/index/equip-responses-api-computer-environment/)从 Shell 入手，再介绍容器中的文件、数据和网络。它让我更关注 Agent 的另一半：**模型决定下一步，计算环境承载这一步真正发生。**

- **行动入口：** Shell 怎样把工具请求接到现成的计算机程序。
- **执行落点：** 文件、进程和容器怎样承载工作，数据库与网络怎样连接其他资源。
- **观察结果：** 实际输出怎样包装为 Tool Result，再回到 Agent Loop。

继续沿用上一篇的 Java 排查场景：Agent 读取 `UserService.java`，修改实现，再运行测试。这里讨论的是这几步怎样落到真实系统上，不是假设模型已经掌握了整台电脑。

## 一、Shell：把模型提出的动作接到现成程序

模型输出一条命令，与命令已经运行，是两件事。比如：

```bash
grep -R -n "UserService" src/
```

如果它只出现在回答里，就是一段文本。通过 Shell Tool 提交后，还需要运行时把命令交给执行环境，由 Shell 启动 `grep`，读取当前项目中的文件，再返回匹配结果。

所以，“模型本身没有电脑”更准确的意思是：**一次模型推理不会自动获得项目目录、系统进程或数据库连接。** 模型当然运行在计算硬件上，但那不等于它能够直接操作用户的工作空间。可操作哪些资源，来自外部系统接入的执行能力。

Shell 的价值，是把大量已有程序变成可组合的行动方式：

| 想完成的工作 | 环境中可以使用的程序 |
| --- | --- |
| 查看目录、读取文件 | `ls`、`cat` |
| 搜索实现和引用 | `grep`、`rg` |
| 查看代码差异 | `git diff` |
| 编译、运行测试 | Maven、Gradle 或项目自己的脚本 |
| 处理数据、生成文件 | Python、Node.js 等运行时 |
| 发出网络请求 | `curl` 等客户端 |

这里以常见的 Unix 命令为例，具体能力取决于环境实际安装了什么。给 Agent 一个 Shell，不等于同时安装了 Java、Maven 和所有依赖。

这也是 Shell 和专用工具的一个直观区别：搜索 Java 类，不一定需要单独做一个 `search_java_class()`。执行环境已经有搜索程序时，模型可以通过 Shell 请求使用它。**通用程序提供了行动空间，运行时把模型的请求接到这些程序上。**

原文还区分了两种接法：自定义工具把执行交回客户端，由应用自己的 Harness 接手；托管 Shell 则由 Responses API 把命令送到容器运行时。两者的执行位置不同，但都不是模型自己执行命令。

## 二、Filesystem：文件既是工作材料，也是环境状态

Agent 读取代码，是从执行环境的文件系统拿到内容；Agent 修改代码，改变的也是那里的文件。工作目录不是对话中的一个装饰字段，它决定了相对路径指向哪个项目。

假设这次工作使用下面的目录：

```text
/workspace/user-service/
├── pom.xml
├── src/main/java/.../UserService.java
├── src/test/java/.../UserServiceTest.java
└── target/
```

这只是示例目录，不是 Responses API 固定要求的路径。它表达的是：源码、测试和构建输出，都有实际存放的位置。

假设工具先读取 `UserService.java`，随后应用了一次修改。在同一个仍然存在的工作空间中，再读取这条路径，拿到的应该是修改后的内容，而不是最初的版本。环境不会因为模型进行了下一次推理，就自动还原。

这里有一个重要区别：

| 所在位置 | 保存的是什么 |
| --- | --- |
| 模型 Context | 本次推理能够使用的指令、消息、工具调用和结果 |
| 文件系统 | 项目文件、中间产物、日志等实际内容 |

**文件改了，不代表模型已经看到了最新文件；模型曾经看过文件，也不代表文件一直没有变化。** 两者之间需要读取结果、修改结果或差异等反馈来连接。

例如，工具执行一次修改后，返回“已应用补丁”，这能说明修改操作的状态，但未必包含整个新文件。模型需要进一步核对时，可以请求读取文件或查看 `git diff`。反过来，把旧代码保留在 Context 中，也不会阻止外部程序继续修改磁盘上的内容。

因此，文件系统不只是“给模型提供文本”的地方。它承载实际工作，也让连续的工具调用能够在已有成果上继续推进。

## 三、Process：验证来自程序运行，不是模型对运行结果的预测

代码写回文件后，Agent 可以提出运行测试：

```bash
mvn test
```

真正发生的是：运行时在指定工作目录启动命令，Maven 读取项目配置，并按构建生命周期调用相应插件，在 Java 运行环境中完成编译和测试等步骤。这里执行的是实际程序，使用的是实际项目文件。[Maven 的构建生命周期文档](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)也将 `test` 定义为构建中的一个阶段，而不是一段文字指令。

假设测试返回下面的摘要：

```text
Tests run: 19, Failures: 1, Errors: 0, Skipped: 0
BUILD FAILURE
```

这段示例表示 19 个测试中有一个失败。它的意义不在于数字，而在于来源：**测试框架实际运行后的输出，能够与模型对修改效果的判断相互核对。**

但“运行一次命令”也不是一个只有成功或失败的黑盒。需要区分几个信息：

- **stdout：** 程序的标准输出，可能包含结果、日志或进度。
- **stderr：** 程序的标准错误输出，可能包含诊断，也可能只是警告。
- **执行状态：** 进程是已经退出、仍在运行，还是超时。
- **exit code：** 进程退出时的状态码，需要结合对应程序的语义解读。

例如，“找不到 `mvn`”说明测试程序根本没有成功启动，不能据此说代码测试失败。`stderr` 有内容也不必然表示失败；退出码为零，则仍需要确认运行了哪些检查，而不是直接推导出整个项目没有问题。

启动服务也是一样。命令被接受、进程已经启动、端口开始监听、接口能够响应，是不同的状态。**模型需要依据执行端返回的状态继续判断，而不是把“已经发出启动命令”说成“服务已经可用”。**

## 四、Container：为这些操作准备一份可用的工作空间

要让前面的步骤连起来，执行端至少需要项目文件、Shell、构建工具、运行时和依赖。容器的一项直接价值，就是把这些工作条件组织到一个可以运行程序的环境中。

对一个 Java 项目，可以把准备好的环境理解为：

```text
工作环境
├── 项目目录与文件系统
├── Shell 和系统工具
├── JDK、Maven 等项目所需程序
├── 已准备或可获取的依赖
└── 本次工作产生的文件与进程
```

这是所需条件的示意，不代表任意托管容器都预装了这些程序。具体任务需要什么，就要检查实际环境有没有。

把容器类比成 Agent 的“工作台”是有帮助的：文件放在这里，程序在这里运行，中间结果也可以继续在这里使用。但它不是一台完整虚拟机的同义词。[Docker 的基础说明](https://docs.docker.com/get-started/docker-concepts/the-basics/what-is-a-container/)将容器解释为带有所需文件的隔离进程，不能把这个类比理解成模型拥有了一台独立操作系统。

另外，**模型在哪里推理，与工具在哪里执行，可以是两个位置。** 模型服务可以在云端，工具可以接到本地工作目录，也可以接到托管容器。原文展示的是托管容器这一种接法，不是说所有 Agent 都必须在容器里行动。

同一工作空间中的文件能够被后续调用继续使用，也不等于它们会永久保存。环境被替换或销毁后，不能假设原来的文件仍然存在。这是执行环境的生命周期问题，不是模型是否“记得”某段对话的问题。

<figure class="not-prose" style="margin:1.75em 0;">
<figcaption style="margin:0 0 .75rem; color:hsl(var(--muted-foreground)); font-size:.8125rem; line-height:1.7;">图 1 · 打开执行环节：动作落到环境，结果返回模型</figcaption>
<div tabindex="0" role="region" aria-label="Computer Environment 的资源与执行反馈" style="overflow-x:auto; max-width:100%; border-radius:16px; padding:8px 0; background:hsl(var(--background));">
<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="computer-env-title computer-env-desc" viewBox="0 0 640 570" style="display:block; width:100%; min-width:540px; height:auto; font-family:var(--font-sans); --node:light-dark(#e8f3fc,#142b3e); --condition:light-dark(#f4f9fe,#102333); --ink:light-dark(#235e89,#c0def4); --border:light-dark(#d0e0ed,#355167); --line:light-dark(#8e959d,#8295a6); --success:light-dark(#e5f6eb,#152f26); --success-ink:light-dark(#286447,#a9debf); --success-border:light-dark(#afd3bc,#426c57);">
<title id="computer-env-title">Agent 的动作与计算环境</title><desc id="computer-env-desc">模型提出 Tool Call，运行时把请求交给执行端。计算环境承载文件读写和进程执行，并可通过已配置的连接访问数据库与网络服务。结果被包装为 Tool Result，作为 Observation 进入下一次模型判断。读取资源不要求业务状态发生变化。</desc>
<defs><marker id="computer-env-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 2 L6 5 L2 8" fill="none" stroke="var(--line)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<g fill="none" stroke="var(--line)" stroke-width="1.2" marker-end="url(#computer-env-arrow)"><path d="M352 76 V112"/><path d="M352 170 V218"/><path d="M352 418 V474"/><path d="M234 510 H74 Q62 510 62 498 V60 Q62 48 74 48 H234"/></g>
<rect x="234" y="18" width="236" height="58" rx="20" fill="var(--node)" stroke="var(--border)"/><text x="352" y="43" text-anchor="middle" fill="var(--ink)" font-size="18" font-weight="500">Model</text><text x="352" y="65" text-anchor="middle" fill="var(--ink)" font-size="13">产生行动请求 / Tool Call</text>
<rect x="234" y="114" width="236" height="56" rx="20" fill="var(--node)" stroke="var(--border)"/><text x="352" y="138" text-anchor="middle" fill="var(--ink)" font-size="17" font-weight="500">Runtime 对接执行端</text><text x="352" y="160" text-anchor="middle" fill="var(--ink)" font-size="12">本地环境，或托管容器</text>
<text x="372" y="200" fill="var(--ink)" font-size="13">真正执行操作</text>
<rect x="144" y="220" width="416" height="198" rx="22" fill="var(--condition)" stroke="var(--border)"/>
<text x="352" y="249" text-anchor="middle" fill="var(--ink)" font-size="18" font-weight="500">Computer Environment</text>
<rect x="164" y="265" width="178" height="60" rx="14" fill="var(--node)" stroke="var(--border)"/><text x="253" y="289" text-anchor="middle" fill="var(--ink)" font-size="15" font-weight="500">Filesystem</text><text x="253" y="311" text-anchor="middle" fill="var(--ink)" font-size="12">源码、数据与产物</text>
<rect x="362" y="265" width="178" height="60" rx="14" fill="var(--node)" stroke="var(--border)"/><text x="451" y="289" text-anchor="middle" fill="var(--ink)" font-size="15" font-weight="500">Shell / Process</text><text x="451" y="311" text-anchor="middle" fill="var(--ink)" font-size="12">启动程序、编译与测试</text>
<rect x="164" y="338" width="178" height="60" rx="14" fill="var(--node)" stroke="var(--border)"/><text x="253" y="362" text-anchor="middle" fill="var(--ink)" font-size="15" font-weight="500">Database</text><text x="253" y="384" text-anchor="middle" fill="var(--ink)" font-size="12">本地库或远端连接</text>
<rect x="362" y="338" width="178" height="60" rx="14" fill="var(--node)" stroke="var(--border)"/><text x="451" y="362" text-anchor="middle" fill="var(--ink)" font-size="15" font-weight="500">Network</text><text x="451" y="384" text-anchor="middle" fill="var(--ink)" font-size="12">访问可用的外部服务</text>
<text x="372" y="447" fill="var(--ink)" font-size="13">执行输出 / 可观察结果</text>
<rect x="234" y="476" width="236" height="70" rx="20" fill="var(--success)" stroke="var(--success-border)"/><text x="352" y="504" text-anchor="middle" fill="var(--success-ink)" font-size="16" font-weight="500">Tool Result / Observation</text><text x="352" y="529" text-anchor="middle" fill="var(--success-ink)" font-size="12">内容、输出与执行状态</text>
<text x="39" y="302" text-anchor="middle" fill="var(--ink)" font-size="13" transform="rotate(-90 39 302)">纳入下一次输入 → 再次判断</text>
</svg>
</div>
<div style="margin-top:.5rem; text-align:center; color:hsl(var(--muted-foreground)); font-size:.75rem; line-height:1.7;">资源是否可用取决于环境配置；只读操作不必改变业务状态。窄屏可在图内左右滑动查看。</div>
</figure>

## 五、Database 与 Network：行动也可以落到其他系统

文件和进程之外，Agent 还可以通过工具访问数据库与网络服务。区别是执行落点不同，基本连接方式没有改变。

| 动作 | 实际执行者 | 可以返回什么 |
| --- | --- | --- |
| 查询本地 SQLite 文件 | 执行环境中的数据库引擎 | 查询结果或数据库错误 |
| 通过 SQL Tool 查询远端数据库 | 工具实现与所连接的数据库服务 | 行、列及执行状态 |
| 通过 HTTP Tool 发出请求 | HTTP 客户端与远端 Web Service | 状态码、响应体或连接错误 |

例如，分析销售数据时，可以先把结构化数据整理到 SQLite，再查询需要的行，而不是把整张表塞进模型输入。[SQLite 的使用说明](https://www.sqlite.org/whentouse.html)也将数据分析列为它的一种适用场景。这里执行筛选的是数据库引擎，模型获得的是筛选结果。

网络请求也是一样：模型可以提出获取某个接口的数据，但实际连接由客户端建立，远端服务返回响应。环境中有没有网络、能访问哪些地址、是否具备所需连接条件，都不是模型生成一个 URL 就能决定的。

需要注意，**数据库或服务可访问，不等于它们都运行在当前容器内部。** SQLite 可以是本地文件，业务数据库可以在另一台服务器上；环境提供的是操作入口与连接条件。

这里也不必把每次行动都说成“改变世界”。读取文件、执行 `SELECT`、请求一份数据，主要是在获取已有状态；修改文件、写入记录、提交请求，才可能改变相应状态。两类行动都可以产生供模型使用的观察结果。

## 六、Observation：环境结果怎样接回 Agent Loop？

执行环境不会把自己全部“装进模型”。它通过工具返回一部分可观察信息，运行时再把这些信息组织为 Tool Result。

以 Shell 为例，一条已经退出的命令可以返回这样的结果。下面借用 Shell Tool 的字段说明，内容是示例，不是本次博客实际运行的测试记录：

```json
{
  "type": "shell_call_output",
  "call_id": "call_run_tests",
  "output": [
    {
      "stdout": "Tests run: 19, Failures: 1, Errors: 0, Skipped: 0",
      "stderr": "",
      "outcome": { "type": "exit", "exit_code": 1 }
    }
  ]
}
```

`call_id` 关联的是模型提出的那次请求；输出与执行状态说明的是环境里实际发生了什么。[OpenAI Docs 的 Shell 文档](https://developers.openai.com/api/docs/guides/tools-shell)也区分了本地执行、托管执行以及对应的输出结果。

模型下一次拿到这些信息后，可以决定查看失败测试、读取报告，或者说明执行为什么被阻塞。文件内容、查询结果和 HTTP 响应也以类似方式成为 Observation：**它们是模型对环境的观察，不是环境本身。**

这个区别很实用。日志被截断时，不能把没返回的部分当作已经看过；文件发生变化却没有读回时，不能假设 Context 中的旧内容自动更新。运行时提供什么反馈，会直接影响下一次判断能够依据什么。

于是，第三篇和第四篇就接在了一起：

| 视角 | 要理解的连接 |
| --- | --- |
| [03 · Agent Loop](/zh-cn/posts/codex-agent-loop/) | 模型输出怎样接上工具结果，再进入下一次判断 |
| 04 · Computer Environment | 工具请求怎样落到真实资源，再产生可以回传的结果 |

我把这两层合起来理解为：**Loop 组织决策与反馈，Environment 承载执行与状态。** 模型提出动作，运行时对接执行端，文件或程序产生结果，再由结果影响下一次行动。

原文还讨论了 Compaction 和 Skills，分别涉及增长中的模型上下文，以及可复用的任务知识与流程。它们与计算环境配合，但不是执行环境本身：文件在哪里、程序在哪里运行，与模型这次带上哪些信息，是不同的问题。

执行通路清楚以后，一个更具体的设计问题也就出现了：**工具的名称、参数和结果应该怎样表达，才能让模型稳定地选对、用对，并理解执行结果？**

## 几个关键问题，串起执行环境与反馈

**模型在云端运行，修改的文件就一定在云端吗？**

不一定。推理服务的位置与工具执行端的位置可以不同。要看 Runtime 将文件操作交给了哪里：本地工作目录、托管容器，还是远端服务。模型的位置不能直接推出文件的位置。

**有 Shell，为什么还会出现“命令不存在”？**

Shell 是调用程序的入口，不是所有软件的集合。运行 Maven 需要对应程序与 Java 环境，执行项目脚本还可能需要依赖。命令文本可以被模型正确生成，但执行环境仍然可能没有满足运行条件。

**文件已经修改，为什么还要把结果传回模型？**

修改改变了外部状态，不会直接改写模型当前输入。只有通过修改结果、差异或重新读取等反馈，后续判断才能知道哪些内容发生了变化。磁盘上的新文件与 Context 中的旧内容可以同时存在。

**测试命令失败，就能判断是代码改错了吗？**

不能只凭失败状态下结论。需要区分程序没有启动、依赖准备失败、编译失败与测试断言失败。它们都可能阻止命令成功结束，但指向的原因不同；执行状态和输出需要一起看。

**容器保留了文件，就等于模型保留了这些信息吗？**

不是。文件存在意味着它仍可被工具读取，不代表全部内容都进入了这次模型输入。反过来，模型输入里有某份文件的内容，也不保证原工作空间仍然存在。环境状态与模型上下文各自有不同的边界。

## 参考资料

- [OpenAI — From model to agent: Equipping the Responses API with a computer environment](https://openai.com/index/equip-responses-api-computer-environment/)
- [OpenAI Docs — Shell](https://developers.openai.com/api/docs/guides/tools-shell)
- [Docker Docs — What is a container?](https://docs.docker.com/get-started/docker-concepts/the-basics/what-is-a-container/)
- [Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [SQLite — Appropriate Uses For SQLite](https://www.sqlite.org/whentouse.html)
- [上一篇：Agent Loop](/zh-cn/posts/codex-agent-loop/)
