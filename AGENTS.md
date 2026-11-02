# 项目协作规则

- 始终使用中文回复。
- 本地负责代码开发；AutoDL 负责训练；GitHub 保存经用户要求归档或实验验证后的代码版本。
- 每次训练前先提交本地 Git，再通过 `scripts/autodl.py sync` 同步对应提交。未经验证的实验不自动推送 GitHub；初始项目归档与同步工具除外。
- 训练必须使用 `/root/autodl-tmp/visdrone-codex/releases/<完整commit>` 中的代码，结果保存到共享 outputs 中独立的实验目录，记录 commit、配置、种子、数据划分、依赖版本和指标。
- 不提交 dataset、pretrained_weights、outputs、runs、模型文件或服务器登录配置。不得在输出、日志或仓库中打印密码。
- `autodl配置.txt` 是本地连接配置，读取时避免显示凭据。同步工具会校验首次保存的 SSH 主机密钥。
- 回退优先新建旧提交分支或使用 git revert，不强制推送或删除已有实验记录。
- 当前只有研究文档、数据及同步工具；接入并验证基线后才启动正式训练。不得把研究假设写成已验证的结果。
