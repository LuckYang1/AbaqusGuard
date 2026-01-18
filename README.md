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
cp .env.example .env

# 编辑配置
notepad .env
```

---

## ⚙️ 配置说明

编辑 `.env` 文件进行配置：

### 📬 通知配置（可选）

| 配置项 | 说明 | 示例 |
|--------|------|------|
| `FEISHU_WEBHOOK_URL` | 飞书 Webhook URL | `https://www.feishu.cn/flow/api/trigger-webhook/xxx` |
| `WECOM_WEBHOOK_URL` | 企业微信 Webhook URL | `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx` |

> 💡 留空则不发送对应渠道的通知，两个渠道可独立配置

### 📝 CSV 记录配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `ENABLE_CSV_LOG` | `true` | 是否启用 CSV 记录 |
| `CSV_PATH` | 空（项目根目录） | CSV 文件保存目录 |
| `CSV_FILENAME` | `abaqus_jobs_%Y%m.csv` | 文件名模板 |
| `CSV_UPDATE_INTERVAL` | `60` | 定时更新间隔（秒） |
| `CSV_OVERWRITE_MODE` | `none` | 覆盖模式 |
| `CSV_MAX_HISTORY` | `5` | 保留历史记录数 |

#### 📋 CSV 覆盖模式说明

| 模式 | 行为 |
|------|------|
| `none` | 📄 每次运行都新增一条记录 |
| `running` | 🔄 覆盖同名且状态为"运行中"的记录（推荐调试时使用） |
| `always` | ♻️ 总是覆盖同名作业的最后一条记录 |

### 🔧 监控配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `WATCH_DIRS` | - | 监控目录列表，多个目录用逗号分隔 |
| `POLL_INTERVAL` | `5` | 轮询间隔（秒） |
| `VERBOSE` | `true` | 是否输出详细日志 |
| `PROGRESS_NOTIFY_INTERVAL` | `3600` | 进度通知间隔（秒） |
| `ENABLE_PROCESS_DETECTION` | `true` | 是否启用进程检测 |
| `LCK_GRACE_PERIOD` | `60` | .lck 文件宽限期（秒） |
| `JOB_END_CONFIRM_PERIOD` | `60` | .lck 删除后的结束确认期（秒），避免 .sta 收尾写入导致误判 |
| `NOTIFY_DEDUPE_TTL` | `3600` | 通知去重窗口（秒），防止相同事件重复发送 |
| `PROGRESS_NOTIFY_MIN_TOTAL_TIME_DELTA` | `0` | Total Time 最小增量阈值（>0 时可用于触发进度推送） |

---

## 🚀 使用方法

### 启动监控

```bash
uv run python run.py
```

### 动态修改监控目录

编辑 `.env` 文件中的 `WATCH_DIRS`，保存后自动生效（无需重启服务）：

```env
# 添加新目录
WATCH_DIRS=C:/Abaqus_Jobs,D:/NewProject

# 移除目录
WATCH_DIRS=C:/Abaqus_Jobs
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
├── 📄 .env                    # 环境配置（需从 .env.example 复制）
├── 📄 .env.example            # 环境配置示例
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
│   │   └── 📄 webhook_client.py   # 飞书通知客户端
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
1. 确认 `.env` 中配置了正确的 Webhook URL
2. 确认网络可以访问飞书/企业微信服务器
3. 查看控制台是否有错误日志

</details>

<details>
<summary><b>📝 如何只使用 CSV 记录，不发送通知？</b></summary>

将 `FEISHU_WEBHOOK_URL` 和 `WECOM_WEBHOOK_URL` 留空即可：
```env
FEISHU_WEBHOOK_URL=
WECOM_WEBHOOK_URL=
```

</details>

<details>
<summary><b>📊 CSV 文件中出现很多重复记录怎么办？</b></summary>

设置覆盖模式为 `running`，调试时会自动覆盖未完成的记录：
```env
CSV_OVERWRITE_MODE=running
CSV_MAX_HISTORY=5
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

直接编辑 `.env` 文件中的 `WATCH_DIRS` 并保存，程序会在下一个轮询周期（默认 5 秒）自动检测变化并生效。

</details>

<details>
<summary><b>📈 进度百分比显示为空是什么原因？</b></summary>

进度百分比需要从 `.inp` 文件中解析总分析步时间。如果 `.inp` 文件不存在或格式不支持，则无法计算百分比。

</details>

---

## 📄 License

MIT License © 2026
