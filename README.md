# 🛡️ AbaqusGuard

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/Platform-Windows-lightgrey.svg" alt="Platform">
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License">
</p>

<p align="center">
  <b>Abaqus 作业监控守卫</b> - 监控作业状态，支持飞书/企业微信通知和 CSV 记录
</p>

---

## ✨ 功能特性

- 🔍 自动检测 Abaqus 作业的开始、进度和完成
- 📱 支持飞书和企业微信 Webhook 通知
- 📊 CSV 记录作业历史，支持覆盖模式和历史清理
- ☁️ **飞书多维表格实时同步** - 作业数据自动同步到飞书多维表格，随时随地查看
- ⚠️ 检测孤立作业（进程异常终止但 .lck 文件未删除）
- 🔄 支持动态添加/移除监控目录（无需重启服务）
- 📈 进度条显示和 .sta 文件解析
- ⏱️ 从 .inp 文件解析总分析步时间，计算完成百分比

---

## 📦 安装

### 环境要求

- 🖥️ Windows 系统
- 🐍 Python 3.8+
- 📦 [uv](https://github.com/astral-sh/uv)（推荐）或 pip

### 安装步骤

```bash
# 克隆项目
git clone https://github.com/LuckYang1/AbaqusGuard.git
cd AbaqusGuard

# 安装依赖
uv sync

# 复制配置文件
cp config_example.toml config.toml

# 编辑配置
notepad config.toml
```

---

## ⚙️ 配置说明

编辑 `config.toml` 文件进行配置：

### 📬 通知配置（可选）

| 配置项 | 说明 | 示例 |
|--------|------|------|
| `webhook.feishu_url` | 飞书 Webhook URL | `https://www.feishu.cn/flow/api/trigger-webhook/xxx` |
| `webhook.wecom_url` | 企业微信 Webhook URL | `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx` |
| `webhook.routes` | 多机器人路由（数组表） | `[[webhook.routes]]` |

> 💡 留空则不发送对应渠道的通知，两个渠道可独立配置；若设置路由，未匹配规则会回退到默认 URL

#### 多机器人路由（TOML）

```toml
[webhook]
feishu_url = "https://www.feishu.cn/flow/api/trigger-webhook/xxx"
wecom_url = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=yyy"

[[webhook.routes]]
channel = "feishu"
events = ["start", "progress"]
match_dir = "C:/Abaqus_Jobs"
webhook_url = "https://www.feishu.cn/flow/api/trigger-webhook/aaa"

[[webhook.routes]]
channel = "wecom"
events = ["complete", "orphan"]
match_dir = "D:/Projects"
webhook_url = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=bbb"
```

- `events` 固定值：`start`、`progress`、`complete`、`error`、`orphan`
- `match_dir` 为目录前缀匹配，可匹配其子目录
- `match_job` 可选，使用通配符（如 `ProjectA-*`），不填则匹配全部作业
- 未匹配任何规则时，回退到 `webhook.feishu_url` / `webhook.wecom_url`

### 📝 CSV 记录配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `csv.enable` | `true` | 是否启用 CSV 记录 |
| `csv.path` | 空（项目根目录） | CSV 文件保存目录 |
| `csv.filename` | `abaqus_jobs_%Y%m.csv` | 文件名模板 |
| `csv.update_interval` | `60` | 定时更新间隔（秒） |
| `csv.overwrite_mode` | `none` | 覆盖模式 |
| `csv.max_history` | `5` | 保留历史记录数 |

#### 📋 CSV 覆盖模式说明

| 模式 | 行为 |
|------|------|
| `none` | 📄 每次运行都新增一条记录 |
| `running` | 🔄 覆盖同名且状态为"运行中"的记录（推荐调试时使用） |
| `always` | ♻️ 总是覆盖同名作业的最后一条记录 |

### 🔧 监控配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `watch_dirs` | - | 监控目录列表 |
| `poll_interval` | `5` | 轮询间隔（秒） |
| `verbose` | `true` | 是否输出详细日志 |
| `progress_notify_interval` | `3600` | 进度通知间隔（秒） |
| `enable_process_detection` | `true` | 是否启用进程检测 |
| `lck_grace_period` | `60` | .lck 文件宽限期（秒） |
| `job_end_confirm_period` | `60` | .lck 删除后的结束确认期（秒），避免 .sta 收尾写入导致误判 |
| `notify_dedupe_ttl` | `3600` | 通知去重窗口（秒），防止相同事件重复发送 |
| `progress_notify_min_total_time_delta` | `0` | Total Time 最小增量阈值（>0 时可用于触发进度推送） |

### ☁️ 飞书多维表格配置（新功能）

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `bitable.enable` | `false` | 是否启用飞书多维表格同步 |
| `bitable.app_id` | 空 | 飞书应用 ID |
| `bitable.app_secret` | 空 | 飞书应用 Secret |
| `bitable.app_token` | 空 | 多维表格的 App Token |
| `bitable.table_id` | 空 | 数据表的 Table ID |
| `bitable.update_interval` | `60` | 多维表格更新间隔（秒） |
| `bitable.max_history` | `5` | 保留历史记录数（每个作业） |

#### 📌 多维表格配置步骤

**1. 创建飞书应用**

1. 访问[飞书开放平台](https://open.feishu.cn/app)
2. 创建企业自建应用，获取 `app_id` 和 `app_secret`
3. 在应用权限中开通"多维表格"权限，并授予对应多维表格的写入权限

**2. 获取多维表格信息**

在飞书多维表格中创建表格后，从 URL 中获取：
```
https://xxx.feishu.cn/base/bascnXXXXXX?table=tblXXXXXX
                        ↑app_token  ↑table_id
```
- `app_token` = `bascnXXXXXX`
- `table_id` = `tblXXXXXX`

**3. 创建数据表字段**

在多维表格中创建以下字段：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| 作业名称 | 文本 | |
| 工作目录 | 文本 | |
| 计算机 | 文本 | |
| 开始时间 | 日期 | |
| 结束时间 | 日期 | |
| 耗时 | 文本 | 格式："X小时 Y分钟" |
| 进度 | 进度 | 0-100% |
| 状态 | 单选 | 运行中、成功、失败、异常终止 |
| 计算结果 | 文本 | |
| ODB大小(MB) | 数字 | |
| Total Time | 数字 | |
| 更新时间 | 日期 | |

**4. 配置 config.toml**

```toml
[bitable]
enable = true
app_id = "your_app_id"
app_secret = "your_app_secret"
app_token = "bascnXXXXXX"
table_id = "tblXXXXXX"
max_history = 5  # 保留最近 5 条记录
```

> 💡 多维表格同步与 CSV 记录可同时使用，数据会同时写入两者
>
> 💡 多维表格历史记录会在作业完成时自动清理，仅保留最近 N 条记录（由 `max_history` 配置）

---

## 🚀 使用方法

### 启动监控

```bash
uv run run.py
```

### 动态修改监控目录

编辑 `config.toml` 文件中的 `watch_dirs`，保存后自动生效（无需重启服务）：

```toml
# 添加新目录
watch_dirs = ["C:/Abaqus_Jobs", "D:/NewProject"]

# 移除目录
watch_dirs = ["C:/Abaqus_Jobs"]
```

### 📺 控制台日志示例

```
[2026-01-17 20:00:00] === Abaqus 作业监控启动 ===
[2026-01-17 20:00:00] 监控目录: ['C:/Abaqus_Jobs']
[2026-01-17 20:00:05] 作业开始: Test-Job @ C:/Abaqus_Jobs
[2026-01-17 20:00:05] 进度更新: Test-Job - Step:1 Inc:1
[2026-01-17 21:00:05] 进度更新: Test-Job - Step:1 Inc:150
[2026-01-17 22:30:00] 作业完成: Test-Job - 成功
```

---

## 📁 项目结构

```
AbaqusGuard/
├── 📄 run.py                  # 运行入口
├── 📄 main.py                 # 备用入口
├── 📄 pyproject.toml          # 项目配置
├── 📄 config.toml             # 配置文件
├── 📂 src/
│   ├── 📄 __init__.py
│   ├── 📄 main.py             # 主程序
│   ├── 📂 config/
│   │   ├── 📄 __init__.py
│   │   └── 📄 settings.py     # 配置管理
│   ├── 📂 core/
│   │   ├── 📄 __init__.py
│   │   ├── 📄 job_detector.py     # 作业检测器
│   │   ├── 📄 csv_logger.py       # CSV 记录器
│   │   ├── 📄 progress_parser.py  # .sta 文件解析
│   │   ├── 📄 inp_parser.py       # .inp 文件解析
│   │   └── 📄 process_detector.py # 进程检测
│   ├── 📂 feishu/
│   │   ├── 📄 __init__.py
│   │   ├── 📄 webhook_client.py   # 飞书通知客户端
│   │   ├── 📄 bitable_client.py   # 飞书多维表格 API 客户端
│   │   └── 📄 bitable_logger.py   # 飞书多维表格记录器
│   ├── 📂 wecom/
│   │   ├── 📄 __init__.py
│   │   └── 📄 webhook_client.py   # 企业微信通知客户端
│   └── 📂 models/
│       ├── 📄 __init__.py
│       └── 📄 job.py              # 作业数据模型
└── 📂 tests/                  # 测试目录
    └── 📄 __init__.py
```

---

## ❓ 常见问题

<details>
<summary><b>🔔 为什么作业开始后没有收到通知？</b></summary>

请检查以下几点：
1. 确认 `config.toml` 中配置了正确的 Webhook URL
2. 确认网络可以访问飞书/企业微信服务器
3. 查看控制台是否有错误日志

</details>

<details>
<summary><b>📝 如何只使用 CSV 记录，不发送通知？</b></summary>

将 `webhook.feishu_url` 和 `webhook.wecom_url` 留空即可：
```toml
[webhook]
feishu_url = ""
wecom_url = ""
```

</details>

<details>
<summary><b>📊 CSV 文件中出现很多重复记录怎么办？</b></summary>

设置覆盖模式为 `running`，调试时会自动覆盖未完成的记录：
```toml
[csv]
overwrite_mode = "running"
max_history = 5
```

</details>

<details>
<summary><b>⚠️ 作业异常终止后显示"孤立作业"是什么意思？</b></summary>

当 Abaqus 进程已停止，但 `.lck` 文件仍然存在时，会被判定为孤立作业。这通常发生在：
- 手动终止 Abaqus 进程
- 系统崩溃或断电
- Abaqus 异常退出

**解决方法**：手动删除对应的 `.lck` 文件

</details>

<details>
<summary><b>🔄 如何修改监控目录而不重启服务？</b></summary>

直接编辑 `config.toml` 文件中的 `watch_dirs` 并保存，程序会在下一个轮询周期（默认 5 秒）自动检测变化并生效。

</details>

<details>
<summary><b>📈 进度百分比显示为空是什么原因？</b></summary>

进度百分比需要从 `.inp` 文件中解析总分析步时间。如果 `.inp` 文件不存在或格式不支持，则无法计算百分比。

</details>

<details>
<summary><b>☁️ 飞书多维表格同步失败怎么办？</b></summary>

请检查以下几点：
1. 确认飞书应用是否有对应多维表格的写入权限
2. 确认 `app_token` 和 `table_id` 是否正确
3. 查看控制台日志，获取详细的错误信息
4. 如果网络不稳定，系统会自动降级到 CSV 记录，不会影响监控功能

</details>

<details>
<summary><b>☁️ 飞书多维表格和 CSV 可以同时使用吗？</b></summary>

可以！两者完全独立，可以同时启用。作业数据会同时写入 CSV 本地文件和飞书多维表格，为您提供双重备份和更灵活的数据访问方式。

</details>

---

## 📄 License

MIT License © 2026

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=LuckYang1/AbaqusGuard&type=date&legend=bottom-right)](https://www.star-history.com/#LuckYang1/AbaqusGuard&type=date&legend=bottom-right)