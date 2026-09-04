# Blog Manager

Blog Manager 是这个 Litos/Astro 博客的本地图形化文件编辑器。它直接管理文章 Content Collection 和 `src/data/open-source.json`，不使用数据库，也不连接任何部署环境。

程序只监听 `127.0.0.1`。默认博客根目录由源码位置自动推导为 `D:\Projects\Blog`；打包时会在 EXE 同目录生成 `blog-manager.json` 保存该路径。开发调试时也可使用 `--blog-root D:\Projects\Blog` 明确指定。

双击 EXE 时会先寻找系统 pnpm；如果 Windows Explorer 的 PATH 中没有 pnpm，会自动使用项目内 `tools/blog-manager/runtime/node.exe` 直接运行 Astro 和 Pagefind，不依赖 Codex 终端环境。

## 开发运行

要求 Windows、Python 3.12 和已安装在博客项目中的 pnpm 依赖。

```powershell
cd D:\Projects\Blog\tools\blog-manager
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

默认以 pywebview 桌面窗口启动。浏览器调试可运行：

```powershell
.\.venv\Scripts\python.exe app.py --browser
```

只启动本地 Flask 服务、不打开窗口：

```powershell
.\.venv\Scripts\python.exe app.py --serve --port 8765
```

## Articles 与 Markdown Import

Articles 自动扫描 `src/content/posts` 中的 `.md` 和 `.mdx`，可搜索、按草稿状态过滤、编辑当前 schema 支持的 Frontmatter、修改 slug、查看关联 PR、用 Windows 默认应用打开原文件，以及在输入准确 slug 并再次确认后删除文章。

正文不在管理器中编辑。保存 Frontmatter 时会保留正文原文，并使用同目录临时文件后原子替换。

Import Markdown 支持文件选择和拖放。程序先解析 Frontmatter；缺少 `title`、`description` 或 `pubDate` 时须在表单补齐。目标冲突时必须选择取消、自动重命名或显式确认覆盖，不会静默覆盖。

## Open Source 与 GitHub Fetch

Open Source 读取 `src/data/open-source.json`。项目的 Merged PR 数始终由 `contributions.length` 计算。PR 可添加、编辑、移动项目或确认删除，所有自动获取的字段仍可手工修改。

Add PR 中粘贴完整公开 GitHub PR URL 后点击 Fetch。程序优先匿名调用 GitHub 公共 API，可选读取进程环境变量 `GITHUB_TOKEN`，但不会保存 token。它读取仓库、编号、标题、URL、合并状态/时间和作者。Related Issue 只在 PR 正文中存在唯一可靠的 `fixes/closes/resolves #编号` 关系时自动填写；不从标题猜测。遇到网络错误、API 错误或 rate limit 时，表单保持可编辑，可直接手工完成保存。Summary 永远由用户填写，不做自动生成。

## Relations 与网站双向链接

唯一关系源是 contribution 的可选 `article` 字段，其值必须从当前文章列表选择：

- PR 详情页在有关联时显示 Write-up；
- 文章详情页反向查询并显示 Related Open Source Contribution；
- 没有关联时不渲染空模块；
- Relations 支持 All、Linked、Unlinked，以及 Link、Change、Unlink。

正式域名尚未配置，因此 V1 隐藏 Copy Write-up Link，也不会向 GitHub 写入评论或修改 PR。

## Preview 与 Build

Preview 页面可执行 Start Dev Preview、Stop Dev Preview、Open Blog 和 Build。预览固定运行于 `http://127.0.0.1:4321/zh-cn/`，同一个管理器不会重复启动多个 `pnpm dev`；端口被外部进程占用时会明确提示。关闭桌面窗口时会尝试结束由管理器启动的预览进程。

Build 执行博客根目录的 `pnpm build`，只展示成功/失败和完整输出，不会擅自修改博客代码。

## 测试

```powershell
cd D:\Projects\Blog\tools\blog-manager
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

测试数据只创建在被 Git 忽略的 `tools/blog-manager/.test-workspace`。

## 打包 Windows EXE

默认 onedir 输出保留在项目内并被 Git 忽略：

```powershell
.\.venv\Scripts\python.exe build.py
```

输出：`tools\blog-manager\dist\Blog Manager\Blog Manager.exe`。应用图标来自当前头像，并包含 16、32、48、64、128、256 px 的 ICO 尺寸。

脚本支持可选的外部父目录：

```powershell
.\.venv\Scripts\python.exe build.py --output D:\Applications\03_Productivity\BlogManager
```

为避免误覆盖，只要显式输出目录已存在且非空，脚本就会拒绝继续。当前施工与默认打包不会写到博客目录外。
