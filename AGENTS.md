# Alto Macchiato 维护说明

这是基于 Alto / Lapis、使用 Catppuccin Macchiato 配色的 Typora 主题。正文使用霞鹜文楷，代码使用 Maple Mono。保持项目轻量，不增加重复文档、临时辅助脚本或不必要的构建依赖。

## 文件与修改

- `theme/alto-macchiato.css` 是入口，依次加载上游样式、字体声明、项目覆盖。
- `theme/alto-macchiato/overrides.css` 是日常视觉修改的位置；`fonts.css` 声明包内字体。
- `theme/alto-macchiato/vendor/` 平铺四个上游 CSS。层叠顺序为 Lapis → Lapis Dark → Alto → Alto Dark → 本项目覆盖；修改路径时保持顺序。
- `dependencies.lock.json` 固定字体版本、下载地址、大小、SHA-256 及上游样式来源。字体更新须核实来源，不能为绕过校验随意重算摘要。
- `theme/alto-macchiato/THIRD_PARTY_LICENSES.txt` 集中保存第三方版权和许可，更新依赖时同步；根目录 `LICENSE` 属于本项目，构建时复制进主题资源目录。
- README 只介绍预览、安装和来源；维护信息集中在本文件。保留 `examples/showcase.md` 与 README 引用的截图。
- 字体二进制不进 Git。`.cache/fonts/` 是以 SHA-256 命名的缓存，`dist/` 是发布产物，均被忽略。不要提交旧产物、开发备份、系统文件或另建 `docs/`。

## 构建

在仓库根目录运行，Python 3.9+ 标准库即可：

```sh
python3 scripts/build.py --check
python3 scripts/build.py
```

普通构建优先使用缓存，缺失时下载固定版本并校验；字体有 7 个文件：文楷 v1.522 的 Light / Regular / Medium，以及 Maple Mono NF CN v7.9 unhinted 的 Regular / Bold / Italic / BoldItalic。保留原始字体，不做子集化或格式转换。

已有完整缓存时可用 `python3 scripts/build.py --offline`。缺失或损坏的缓存会导致失败；核实原因后只清理对应缓存。`--cache` 可指定缓存目录，`--output` 可指定产物目录。`--check` 仅检查源码与引用，不能替代完整构建。

构建自动检查 CSS 的本地引用、字体及许可摘要，并读回 ZIP 校验所有文件。版本来自 `VERSION`，输出：

- `dist/alto-macchiato-theme-<版本>.zip`
- 同名 `.zip.sha256`

ZIP 顶层固定为 `alto-macchiato-theme/`，里面只有入口 `alto-macchiato.css` 和资源目录 `alto-macchiato/`；后者含样式、完整字体、项目 LICENSE 与第三方许可。不得把源码文档、脚本、锁文件、截图或示例打入安装包。用户将这两项复制到 Typora 的主题目录即可，不需要安装系统字体或联网下载。

## 检查与发布

1. 更新 `VERSION`（不带 `v`），执行源码检查和完整构建。检查 README 本地链接及截图。
2. 用完整包在 Typora 中打开 `examples/showcase.md`，检查正文、标题、表格、代码、列表、公式和 Mermaid；基准字号 17、默认缩放。没有实际执行的视觉或平台检查不得写成通过。
3. 审查 Git 状态，提交并推送本次源码，保证安装包对应已提交的内容。确认远程仓库和 `gh` 登录身份；只在用户授权发布时继续。
4. 为该 commit 创建并推送 `v<版本>` 标签，不覆盖已有版本。用下面的流程上传 ZIP 和校验文件。长说明先写到 `dist/release-notes.md`，介绍本次变化、安装方式与验证范围。

```sh
# 将下面的 0.1.0 替换为 VERSION 的实际值；origin 是已核实的目标远程。
git tag -a v0.1.0 -m "Alto Macchiato v0.1.0"
git push origin v0.1.0
gh release create v0.1.0 \
  dist/alto-macchiato-theme-0.1.0.zip \
  dist/alto-macchiato-theme-0.1.0.zip.sha256 \
  --verify-tag --title "Alto Macchiato v0.1.0" \
  --notes-file dist/release-notes.md --draft
gh release view v0.1.0 --web
# 核对附件与说明；用户已授权正式发布时执行：
gh release edit v0.1.0 --draft=false
```

Release 说明提醒用户下载完整主题 ZIP；GitHub 自动生成的 Source code 不包含字体。不添加 GitHub Actions，发布由 agent 按以上步骤完成。

当前验证边界：基础样式曾在 macOS / Typora 1.14.10 验证；字体精简后的实际视觉效果仍待复核。Windows、Linux、窄窗口与打印 / PDF 导出尚未验证。
