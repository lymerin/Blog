# 博客发布与预览

源码保存在 `lymerin/Blog`。GitHub Actions 负责构建和发布，本地 Blog Manager 不参与云端部署。

## 日常使用

1. 在分支上修改前端或文章，提交、推送并创建面向 `main` 的 PR。
2. 等待 `Build and check` 与 `Deploy PR preview` 完成。预览链接显示在 PR 评论和 Actions 的 Summary 中。
3. 打开链接确认效果。继续推送同一个分支会更新同一个 PR 的预览。
4. 手动合并 PR 后，`main` 自动构建并发布到正式网站。不会自动合并 PR。
5. PR 合并或关闭后，对应预览环境自动清理。

直接推送 `main` 也会正式发布。仅推送一个普通分支、不创建 PR，不会产生预览。

### 在 GitHub 上看预览

在 PR 页面找到 Azure 的预览链接，点击即可像访问正式博客一样查看页面，也可以把链接发到手机上检查。以最新一次提交的检查结果为准：旧评论仍可能显示地址，但新的构建失败时它可能还是上一次的页面。

预览满意后才点击 Merge。只是在预览页面浏览、刷新或切换语言，不会触发正式发布。

外部 fork 的 PR 只做构建检查，不接收部署凭证、不自动发布预览。

## 两个发布目标

| 目标 | 托管位置 | 认证方式 |
| --- | --- | --- |
| 正式博客 | Azure Storage `lymerinblog` 的 `$web` 容器 | OIDC，仅信任本仓库 `main` |
| PR 预览 | Azure Static Web Apps Free `lymerin-blog-preview` | 单独的预览部署 token，仅存 GitHub Secrets |

预览链接公开可访问；`robots.txt` 和 `X-Robots-Tag` 用于阻止搜索引擎索引，不是访问控制。生产构建不会公开草稿。

Free 预览资源最多同时保留 3 个预览环境；不需要的 PR 应关闭以释放名额。正式站点不受预览名额影响。

## 权限与配置

GitHub 仓库 Settings → Secrets and variables → Actions 中：

- Variables：`BLOG_AZURE_CLIENT_ID`、`BLOG_AZURE_TENANT_ID`、`BLOG_AZURE_SUBSCRIPTION_ID`、`BLOG_STORAGE_ACCOUNT`、`BLOG_SITE_URL`。
- Secret：`BLOG_PREVIEW_DEPLOY_TOKEN`。不要将其复制到代码、文章或文档。

正式部署身份只具有 `$web` 容器范围的 `Storage Blob Data Contributor` 权限，没有整个订阅的管理权限，也没有读取 Storage Account key 的权限。

身份信任绑定本仓库的不可变 GitHub owner/repository ID 和 `refs/heads/main`。改仓库名、转移仓库、改主分支时需重新核对 OIDC subject，不能照抄旧格式。

工作流中的外部 Actions 固定到 commit SHA；更新时应检查上游来源，不随意替换为浮动分支。

## 构建、失败与回退

使用 Node.js 24 和 pnpm 11.25.0，安装锁文件中的依赖，执行 `pnpm build`（类型检查、静态构建和 Pagefind 索引）。没有升级博客依赖。

构建失败时不发布。正式发布前备份现有网站，并保留 `production-before-<run-id>` 和构建产物 7 天。上传按资源、支持文件、页面、搜索入口顺序进行，旧文件不会批量删除。

Azure Storage 上传不是原子切换：如果上传中途失败，部分文件可能已更新，不能声称线上必然完整保留旧版本。此时检查 Actions 日志，修复后重跑，或使用备份恢复。旧文章 URL 也不会因源文件删除自动清理；涉及删除时需单独核对并清理对应已发布文件。

正常代码回退可用 `git revert` 创建新提交并推送 `main`，重新构建部署；不要用强制推送重写历史。手动触发工作流时只能选择 `main` 进行正式发布。

## 换服务器

构建和上传是分开的 job，不需要修改文章或重写博客：

- 换到另一个 Azure Storage：先准备新站点与容器权限，再修改仓库 Variables 中的订阅、身份、Storage Account 和站点 URL。
- 新地址同时需更新 `src/config.ts` 中的 `SITE.website`，保证 canonical、RSS 和图片元数据一致。
- 换其他静态托管服务：保留 `build` job，替换 `production` job 的认证、备份和上传步骤，继续发布 `dist/`。
- 新目标验证通过前，不删除旧服务器。

不是只填一个 URL 就能迁移到任意服务；不同服务的凭证和上传方式不同。

## 多个静态站点

当前仅配置此博客和其 PR 预览。以后可以复用构建流程，分别增加站点发布 job 或独立仓库；每个目标应有独立凭证和部署串行组，避免互相覆盖。

若同一份内容发布到多个域名，应明确主域名和 canonical；如果是不同网站，应分别构建，不能把本博客的 `dist/` 当成多个独立网站。

首次验收包括：正式 OIDC 部署成功、一个测试 PR 的独立预览可访问、同 PR 更新生效、关闭 PR 后预览清理、简繁切换、搜索、深层页面刷新和 404。
