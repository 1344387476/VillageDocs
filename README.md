# 村务材料管理 V1

Windows 本地桌面工具，包含两个相互独立的顶级模块：

- “村建材料”用于录入建房信息、填写固定 Word 母版、整理附件并输出 Word 或 PDF。
- “会议记录”用于选择记录纸模板、录入会议内容，并输出带自然手写效果的 PDF；固定标签和表格线保持矢量印刷效果。

## 重要业务约束

- 签名、签字、盖章、审批意见及对应签署日期始终留空。
- 不保存、复制或生成任何签名/印章图片。
- 第 12 项建筑平面图不属于 V1；审批表内对应图面区域保留空白。
- 身份证、户口簿和家庭信息只保存在用户选择的本地目录，不上传外部服务。

## 开发运行

1. 使用 Python 3.11–3.13 运行 `scripts\bootstrap.ps1`。
2. 将 LibreOffice 的 Windows x64 程序目录放到 `runtime\libreoffice`，确保存在 `program\soffice.exe`。
3. 运行 `scripts\prepare_templates.ps1` 规范化母版并建立占位符。
4. 运行 `python tools\prepare_meeting_templates.py` 重建会议记录矢量模板和缩略图。
5. 运行 `scripts\run.ps1`。

应用启动时会在程序所在目录自动创建 `resource` 文件夹，并在其中创建 `data`、`projects`、`exports` 和 `logs`。最终 Word/PDF 直接保存到 `resource` 根目录；SQLite 只记录相对路径。程序不再要求用户首次启动时选择目录。

## 构建安装包

安装 Inno Setup 6 后运行：

```powershell
.\scripts\build.ps1
```

输出文件位于 `installer\output\VillageDocs-1.1.0-Setup.exe`。安装包包含应用运行时、规范化母版和 LibreOffice，不要求目标电脑安装 Python、Office 或 LibreOffice。

## 支持的附件

- PDF
- Word 97–2003 / DOCX
- JPEG、PNG、TIFF、BMP、HEIC/HEIF
- DWG/DXF 仅归档，不进入最终 Word/PDF

身份证正反面图片按上传顺序每两张合排到一个 A4 页面，自动纠正图片方向并保持比例缩放。

## 测试数据

自动化测试只能使用虚构姓名、校验正确的虚构身份证号和程序生成的图片/PDF。禁止把真实村民材料复制到 `tests`。
