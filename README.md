# 无人机航拍微小目标检测

基于 RT-DETR 的尺度与密度感知训练机制研究。当前仓库保存研究方案与项目同步工具，尚未接入训练代码，尚无实验性能结论。

## 项目内容

- `RTDETR_三创新完整研究方案_2026.docx`：待验证研究方案。
- `师兄论文.pdf`：研究参考文献。
- `数据集说明.txt`：本地数据说明；最终以实际数据审计为准。
- `scripts/autodl.py`：本地到 AutoDL 的传输、远程命令和结果下载工具。

数据集、预训练权重、密码配置和训练产物不进入 GitHub。服务器项目目录为 `/root/autodl-tmp/visdrone-codex`。

## 三端工作方式

1. 本地修改代码，先检查并提交到本地 Git，获得可追溯的 commit。
2. 运行 `python scripts/autodl.py sync`，将当前提交的文件传到服务器对应版本目录；同步要求工作区干净。
3. 在服务器对应版本目录训练。数据和权重通过链接引用共享目录，结果写到共享 `outputs` 下以 commit 和实验名称区分的目录。
4. 下载并检查结果，记录配置、数据划分、随机种子、指标和版本。确认值得保存后再 `git push origin main`。
5. 给验证过的版本添加如 `baseline-verified` 的 Git 标签并推送。回退优先新建旧版本分支或使用 `git revert`，不覆盖已有历史。

GitHub 的初始提交仅表示项目归档，不表示方案已经验证。未经验证的实验也应保留本地提交，便于追溯。

## 同步工具

本地 Python 依赖：`pip install paramiko`。
连接信息读取项目根目录的 `autodl配置.txt`：含 SSH 登录命令，最后一行为密码。该文件始终被忽略。
首次连接的主机密钥保存在 `.local/known_hosts`；后续连接校验该密钥。

```text
python scripts/autodl.py status
python scripts/autodl.py sync
python scripts/autodl.py upload-assets
python scripts/autodl.py exec "远程命令"
python scripts/autodl.py download-results
```

`sync` 只发送 Git 跟踪文件，按完整 commit SHA 建立不可覆盖的代码版本目录，并写入 SHA256 清单。服务器 `current` 链接指向最新同步版本。训练应使用具体版本目录，避免运行期间切换 `current` 影响追溯。

`upload-assets` 单独上传数据和预训练权重，服务器验证归档 SHA256 后解压。大文件上传支持断点续传，已有资源清单相同则跳过。

服务器训练依赖应在基线代码接入后单独锁定。不要将服务器凭据写入脚本、实验日志或 Git。
