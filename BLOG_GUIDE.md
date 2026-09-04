# Blog 使用指南

本项目基于 Litos，所有项目文件、依赖缓存、构建产物都保留在 `D:\Projects\Blog` 内。当前为本地 V1；生产站点地址上线前再修改。

## 本地启动

```powershell
pnpm install
pnpm dev
```

开发服务器启动后，访问终端显示的本地地址。草稿文章会在开发模式中出现。

## Production Build

```powershell
pnpm build
pnpm preview
```

`pnpm build` 已包含 Astro 类型检查、静态构建和 Pagefind 搜索索引生成。`pnpm preview` 用来检查最终构建产物。

## 新增文章

文章目录是 `src/content/posts`。新建 `.md` 或 `.mdx` 文件后不需要登记索引或路由。

最小 Frontmatter：

```yaml
---
title: "文章标题"
description: "文章摘要"
pubDate: 2026-09-04
tags:
  - Java
  - Engineering
draft: true
---
```

完整可用字段：

```yaml
---
title: "文章标题"                 # 必填，字符串
description: "文章摘要"           # 必填，字符串
pubDate: 2026-09-04               # 必填，日期
tags: [Java, Engineering]         # 可选，字符串数组
updatedDate: 2026-09-05           # 可选，日期
author: "De Lin"                 # 可选，默认取全局作者
cover: ./assets/cover.png         # 可选，本地图片
ogImage: ./assets/og.png          # 可选，本地图片
recommend: false                  # 可选，默认 false
postType: metaOnly                # 可选：metaOnly / coverSplit / coverTop
coverLayout: left                 # 可选：left / right
pinned: false                     # 可选，默认 false
draft: true                       # 可选，默认 false
license: "CC BY-NC-SA 4.0"       # 可选
---
```

## Draft

设置 `draft: true` 后：

- `pnpm dev` 中可预览；
- `pnpm build` 的公开页面、标签、RSS、Atom 和搜索索引中不会出现；
- 即使同时设置 `pinned: true`，生产构建也不会泄露草稿。

准备发布时改为 `draft: false`，或删除该字段（默认是 `false`）。

## Tags

直接在文章 Frontmatter 的 `tags` 数组中增加标签。标签页和聚合页会自动生成，不需要手工维护。

建议同时保留内容类标签（如 `Engineering`、`Notes`、`Thoughts`、`Misc`）与技术标签（如 `Java`、`OpenTelemetry`、`Redis`）。

## Markdown / MDX

- 普通文章使用 `.md`。
- 需要在正文中引入 Astro/React 组件时使用 `.mdx`。
- 两种格式都放在 `src/content/posts`，使用相同 Frontmatter。

## 图片

推荐每篇文章建立独立目录：

```text
src/content/posts/my-post/
├─ index.md
└─ assets/
   ├─ cover.png
   └─ diagram.png
```

Frontmatter 中使用 `cover: ./assets/cover.png`。正文中使用：

```markdown
![架构图](./assets/diagram.png)
```

需要固定公共 URL 的资源也可放在 `public`，正文用 `/文件名` 引用。

## 个人信息

- 站点名、作者、简介、导航、社交链接和 GitHub 开关：`src/config.ts`
- 简体/繁体固定文案：`src/i18n/index.ts`
- About 页面结构：`src/pages/[locale]/about.astro`

没有真实 GitHub、Email 或 Resume URL 时保持为空，不要添加占位链接。

## Skills

在 `src/config.ts` 的 `SKILLSSHOWCASE_CONFIG.SKILLS_DATA` 中增加、删除或调整技能。每项包含 `name` 和 Iconify 图标类 `icon`，不使用等级或进度条。

## Featured Open Source

真实数据集中在 `src/data/open-source.json`，`src/data/open-source.ts` 只提供类型与读取辅助。新增或修改条目时填写真实仓库、真实 PR（如有）、描述和标签；PR 数量由 `contributions` 数组长度自动计算。展示组件是 `src/components/base/FeaturedOpenSource.astro`。

## Blog Manager

本地管理工具位于 `tools/blog-manager`，默认只监听 `127.0.0.1`，不使用数据库或线上服务。它可管理文章 Frontmatter、导入 Markdown、维护 Open Source PR/Issue、建立 PR 与文章关系，并启动本地预览或执行构建检查。

首次开发运行：

```powershell
cd D:\Projects\Blog\tools\blog-manager
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

文章正文仍使用 Typora 或 VS Code 编写。关系只存放在 `src/data/open-source.json` 的 contribution `article` 字段，禁止在 Markdown Frontmatter 再维护第二份关系。详细操作、GitHub Fetch 规则、冲突策略、Preview、Build 和 EXE 打包方式见 [`tools/blog-manager/README.md`](tools/blog-manager/README.md)。

## Projects

真实项目放在 `src/content/projects`，每个项目可使用 `.md` 或 `.mdx`。当前 schema：

```yaml
---
name: "真实项目名称"              # 必填，字符串
description: "真实项目描述"       # 必填，字符串
githubUrl: "https://github.com/..." # 必填字符串；没有时填空字符串
website: "https://..."            # 必填字符串；没有时填空字符串
type: "icon"                       # 必填：通常为 icon 或 image
icon: ./assets/icon.png             # 可选；type=image 时使用本地图片
imageClass: "object-contain"        # 可选
star: 0                             # 必填，数字；填写真实值
fork: 0                             # 必填，数字；填写真实值
draft: false                        # 可选，默认 false
---
```

没有真实项目时页面显示空状态，首页不会生成虚假 Selected Projects 区块。

## 简体 / 繁体

- 简体 UI：`/zh-cn/`
- 香港繁体 UI：`/zh-hk/`
- 只有根路径 `/` 会按 `localStorage`、浏览器语言、简体默认值的顺序跳转。
- URL locale 永远是当前页面的事实来源；直接打开 `/zh-hk/...` 不会被旧的本地偏好改回简体。
- 手动切换会保留当前页面路径，并把选择写入 `localStorage` 的 `blog-locale`。
- V1 两个 locale 共用同一份文章正文，仅固定 UI 文案不同。

新增固定 UI 文案时，在 `src/i18n/index.ts` 的简体字典和香港繁体字典中同时增加同一个 key，再通过 `t(locale, 'key')` 使用。

## 主题颜色

技术标签和 Open Source accent token 集中定义在 `src/styles/global.css`。Light/Dark 两套值都在这里维护；不要把零散色值写进组件。

## Litos 内建功能

- Gitalk：`src/config.ts` 的 `COMMENT_CONFIG.enabled` 当前为 `false`，`system` 为 `none`。
- Umami：`src/config.ts` 的 `ANALYTICS_CONFIG.umami.enabled` 当前为 `false`。
- Visit Count：`src/config.ts` 的 `ANALYTICS_CONFIG.vercount.enabled` 当前为 `false`。
- Photos：源码和 `/photos/` 页面保留，但导航入口已隐藏，页面不进入搜索和 sitemap。
- GitHub Contributions：没有 username 时由 `GITHUB_CONFIG.ENABLED: false` 隐藏。

## Future V2

OpenCC 可接在内容读取与渲染之间：保留 `src/content/posts` 的简体源文件，在生成 `/zh-hk/posts/...` 时做 `s2hk` 转换。不要生成并长期维护第二份 Markdown。

## Future Deployment

未来的部署产物是 `dist/`。本地内容和功能确认完成后，再单独设计生产部署。
