# FS-ABAQUS 项目实现计划

## 一、项目概述

**项目名称**: FS-ABAQUS - Abaqus 作业监控脚本
**目标**: 监控 Abaqus 仿真计算作业，通过飞书机器人推送通知，并记录日志到飞书多维表格

---

## 二、技术架构

```
FS-ABAQUS/
├── src/
│   ├── __init__.py
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py          # 配置管理（从环境变量加载）
│   ├── core/
│   │   ├── __init__.py
│   │   ├── job_detector.py      # 作业检测器（.lck文件监控）
│   │   ├── job_monitor.py       # 作业监控器（状态追踪）
│   │   ├── progress_parser.py   # .sta文件解析器
│   │   └── process_detector.py  # 进程检测器
│   ├── feishu/
│   │   ├── __init__.py
│   │   ├── webhook_client.py    # Webhook通知客户端
│   │   ├── bitable_client.py    # 多维表格API客户端
│   │   └── auth.py              # 飞书认证（获取tenant_access_token）
│   ├── models/
│   │   ├── __init__.py
│   │   └── job.py               # 作业数据模型
│   └── main.py                  # 主程序入口
├── tests/
│   ├── __init__.py
│   ├── test_progress_parser.py
│   └── test_job_detector.py
├── .env                         # 环境变量配置
├── .env.example                 # 环境变量配置示例
├── .gitignore                   # Git忽略文件
├── pyproject.toml               # uv 项目配置和依赖管理
├── README.md                    # 项目说明
├── PLAN.md                      # 项目实现计划
└── run.py                       # 运行入口
```

---

## 三、核心模块设计

### 3.1 配置模块 (`src/config/settings.py`)

**功能**: 从环境变量加载配置，提供默认值

**配置项**:
| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `FEISHU_APP_ID` | str | - | 飞书应用ID |
| `FEISHU_APP_SECRET` | str | - | 飞书应用密钥 |
| `FEISHU_WEBHOOK_URL` | str | - | Webhook URL |
| `FEISHU_BITABLE_APP_TOKEN` | str | - | 多维表格app_token |
| `FEISHU_TABLE_ID` | str | - | 表格ID（为空则自动创建） |
| `FEISHU_TABLE_NAME` | str | "Abaqus作业日志" | 自动创建时的表格名称 |
| `ENABLE_FEISHU_BITABLE` | bool | true | 启用多维表格 |
| `AUTO_CREATE_TABLE` | bool | true | 当table_id为空时自动创建表格 |
| `WATCH_DIRS` | List[str] | [] | 监控目录列表 |
| `POLL_INTERVAL` | int | 5 | 轮询间隔(秒) |
| `VERBOSE` | bool | True | 详细日志 |
| `PROGRESS_NOTIFY_INTERVAL` | int | 3600 | 进度推送间隔 |
| `ENABLE_PROCESS_DETECTION` | bool | True | 启用进程检测 |
| `LCK_GRACE_PERIOD` | int | 60 | lck宽限期(秒) |

### 3.2 作业数据模型 (`src/models/job.py`)

```python
@dataclass
class JobInfo:
    name: str                    # 作业名称
    work_dir: str                # 工作目录
    computer: str                # 计算机名
    start_time: datetime         # 开始时间
    end_time: Optional[datetime] # 结束时间
    status: JobStatus            # 状态
    result: str                  # 计算结果描述
    odb_size_mb: float           # ODB大小
    total_time: float            # .sta中的Total Time
    frequency: float             # .sta中的Frequency
    step: int                    # 当前Step
    increment: int               # 当前Increment

    enum JobStatus:
        RUNNING = "运行中"
        SUCCESS = "成功"
        FAILED = "失败"
        ABORTED = "异常终止"
```

### 3.3 进度解析器 (`src/core/progress_parser.py`)

**功能**: 解析 .sta 文件获取进度信息

**.sta 文件格式解析**（基于实际 Abaqus/Standard 2024 格式）:
```
Abaqus/Standard 2024                  DATE 14-1月-2026 TIME 05:51:43
SUMMARY OF JOB INFORMATION:
STEP  INC ATT SEVERE EQUIL TOTAL  TOTAL      STEP       INC OF       DOF    IF
               DISCON ITERS ITERS  TIME/    TIME/LPF    TIME/LPF    MONITOR RIKS
               ITERS               FREQ
   1     1   1     6     0     6  0.100      0.100      0.1000
   1     2   1     3     0     3  0.200      0.200      0.1000
...
THE ANALYSIS HAS COMPLETED SUCCESSFULLY
```

**列说明**:
| 列位置 | 字段名 | 说明 |
|--------|--------|------|
| 1 | STEP | 分析步编号 |
| 2 | INC | 增量编号 |
| 3 | ATT | 尝试次数 |
| 4-7 | SEVERE/EQUIL/DISCON/TOTAL ITERS | 迭代信息 |
| 8 | TOTAL TIME/FREQ | 总时间/频率 |
| 9 | STEP TIME/LPF | 步长时间 |
| 10 | INC OF STEP TIME/LPF | 增量步时间 |

**状态判断（最后一行）**:
| 最后一行内容 | 状态 |
|-------------|------|
| `THE ANALYSIS HAS COMPLETED SUCCESSFULLY` | 成功 |
| `THE ANALYSIS HAS NOT BEEN COMPLETED` | 失败 |
| `THE ANALYSIS HAS BEEN TERMINATED DUE TO AN ERROR` | 失败 |
| 其他或文件结束 | 异常终止/运行中 |

**核心方法**:
- `parse_sta_file(file_path) -> Dict[str, Any]` - 解析sta文件返回进度信息
- `get_last_line_status(file_path) -> str` - 获取最后一行状态判断结果
- `extract_job_start_time(file_path) -> datetime` - 从第一行提取作业开始时间

### 3.4 作业检测器 (`src/core/job_detector.py`)

**功能**: 监控 .lck 文件检测作业状态变化

**核心方法**:
- `scan_jobs() -> List[JobInfo]` - 扫描所有监控目录
- `detect_new_jobs() -> List[JobInfo]` - 检测新作业
- `detect_completed_jobs() -> List[JobInfo]` - 检测完成作业
- `is_job_running(job_name, work_dir) -> bool` - 判断作业是否运行

### 3.5 飞书认证 (`src/feishu/auth.py`)

**API端点**: `POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal`

**功能**: 获取 tenant_access_token 用于后续API调用

### 3.6 飞书Webhook客户端 (`src/feishu/webhook_client.py`)

**功能**: 发送消息到飞书机器人

**API端点**: `POST {FEISHU_WEBHOOK_URL}`

**核心方法**:
- `send_job_start(job: JobInfo)` - 发送作业开始通知
- `send_job_progress(job: JobInfo)` - 发送进度更新
- `send_job_complete(job: JobInfo)` - 发送作业完成通知
- `send_job_error(job: JobInfo, error: str)` - 发送异常通知

**消息格式**: Markdown格式，符合需求文档示例

### 3.7 多维表格客户端 (`src/feishu/bitable_client.py`)

**API端点**:
1. **新增记录**: `POST https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records`
2. **更新记录**: `PATCH https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}`
3. **查询记录**: `GET https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records`
4. **获取表格列表**: `GET https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables`
5. **创建表格**: `POST https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables`
6. **获取字段列表**: `GET https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields`

**字段映射**:
| 飞书字段 | 类型 | 对应JobInfo字段 | 说明 |
|----------|------|-----------------|------|
| 编号 | autonumber | - | 格式: SIM-日期-4位编号（如: SIM-20260115-0001） |
| 作业名称 | text | name | |
| 工作目录 | text | work_dir | |
| 计算机 | text | computer | |
| 开始时间 | datetime | start_time | |
| 结束时间 | datetime | end_time | |
| 耗时 | text | end_time - start_time | |
| 状态 | single_select | status | |
| 计算结果 | text | result | |
| ODB大小(MB) | number | odb_size_mb | |
| TOTALTIME/FREQ | text | f"{total_time}/{frequency}" |

**字段定义配置**:
```python
FIELD_DEFINITIONS = [
    # 第一列：自动编号（类型15为autonumber）
    {
        "field_name": "编号",
        "type": 15,
        "property": {
            "prefix": "SIM-",
            "date_format": "YYYYMMDD",
            "num_format": "0000"
        }
    },
    {"field_name": "作业名称", "type": 1},
    {"field_name": "工作目录", "type": 1},
    {"field_name": "计算机", "type": 1},
    {"field_name": "开始时间", "type": 5},  # datetime
    {"field_name": "结束时间", "type": 5},
    {"field_name": "耗时", "type": 1},
    {"field_name": "状态", "type": 3, "property": {"options": [
        {"name": "运行中"}, {"name": "成功"}, {"name": "失败"}, {"name": "异常终止"}
    ]}},
    {"field_name": "计算结果", "type": 1},
    {"field_name": "ODB大小(MB)", "type": 2},  # number
    {"field_name": "TOTALTIME/FREQ", "type": 1},
]
```

**核心方法**:
- `get_tables() -> List[Dict]` - 获取多维表格中所有数据表
- `create_table(table_name: str, fields: List[Dict]) -> str` - 创建新数据表，返回table_id
- `get_fields(table_id: str) -> List[Dict]` - 获取表格字段定义
- `ensure_table_exists(table_name: str) -> str` - 确保表格存在，不存在则创建
- `create_job_record(job: JobInfo) -> str` - 创建记录返回record_id
- `update_job_record(record_id: str, job: JobInfo)` - 更新记录
- `find_record_by_job(job_name: str, work_dir: str) -> str` - 查找现有记录

### 3.8 主程序 (`src/main.py`)

**运行流程**:
```
1. 加载配置
2. 初始化各模块（检测器、解析器、飞书客户端）
3. 启动监控循环:
   a. 扫描监控目录检测新作业
   b. 对运行中作业解析进度
   c. 检测完成的作业
   d. 发送通知/更新多维表格
   e. 等待POLL_INTERVAL后继续
```

---

## 四、飞书多维表格API集成细节

### 4.1 认证流程

```
1. 使用 FEISHU_APP_ID 和 FEISHU_APP_SECRET 获取 tenant_access_token
2. 后续API请求在Header中携带: Authorization: Bearer {tenant_access_token}
3. token有效期2小时，需定期刷新
```

### 4.2 字段配置要求

**方式一：自动创建（推荐）**

配置 `AUTO_CREATE_TABLE=true`，当 `FEISHU_TABLE_ID` 为空时，程序将自动创建多维表格和字段。

**方式二：手动创建**

在飞书中手动创建多维表格，并创建以下字段:

| 字段名 | 字段类型 | 字段ID建议 | 说明 |
|--------|----------|------------|------|
| 编号 | 自动编号 | field_id | 格式: SIM-YYYYMMDD-NNNN |
| 作业名称 | 文本 | field_name | |
| 工作目录 | 文本 | field_work_dir | |
| 计算机 | 文本 | field_computer | |
| 开始时间 | 日期时间 | field_start_time | |
| 结束时间 | 日期时间 | field_end_time | |
| 耗时 | 文本 | field_duration | |
| 状态 | 单选 | field_status | 选项: 运行中/成功/失败/异常终止 |
| 计算结果 | 文本 | field_result | |
| ODB大小(MB) | 数字 | field_odb_size | |
| TOTALTIME/FREQ | 文本 | field_time_freq |

手动创建后，从浏览器 URL 获取 `app_token` 和 `table_id` 填入配置文件。

### 4.3 记录逻辑

1. **作业开始时**: 创建新记录，记录基本信息
2. **进度更新时**: 不更新多维表格（避免频繁API调用）
3. **作业完成时**: 更新记录，填写结束时间、耗时、最终状态

---

## 五、实现步骤

### Phase 1: 项目初始化
- [ ] 使用 `uv init` 初始化项目
- [ ] 创建项目目录结构
- [ ] 配置 `pyproject.toml` 依赖
- [ ] 创建 `.env` 配置文件
- [ ] 创建 `.gitignore` 文件

### Phase 2: 配置模块
- [ ] 实现 `settings.py` 环境变量加载

### Phase 3: 数据模型
- [ ] 定义 `JobInfo` 数据类和 `JobStatus` 枚举

### Phase 4: 核心监控模块
- [ ] 实现 `.sta` 文件解析器
- [ ] 实现作业检测器（.lck文件监控）
- [ ] 实现进程检测器（可选）

### Phase 5: 飞书集成模块
- [ ] 实现飞书认证（获取tenant_access_token）
- [ ] 实现Webhook通知客户端
- [ ] 实现多维表格API客户端（创建/更新/查询记录）
- [ ] 实现自动创建表格和字段功能
  - [ ] `get_tables()` - 获取表格列表
  - [ ] `create_table()` - 创建新表格
  - [ ] `ensure_table_exists()` - 确保表格存在

### Phase 6: 主程序集成
- [ ] 实现监控主循环
- [ ] 整合各模块
- [ ] 异常处理和日志

### Phase 7: 测试与优化
- [ ] 单元测试
- [ ] 集成测试
- [ ] 错误处理优化

---

## 六、Python 环境管理（使用 uv）

### 初始化项目

```bash
# 初始化 uv 项目
uv init

# 安装依赖
uv add python-dotenv requests psutil
uv add --dev pytest

# 运行项目
uv run python -m src.main

# 或激活虚拟环境后运行
uv sync
.venv\Scripts\activate  # Windows
python -m src.main
```

### 依赖列表 (`pyproject.toml`)

```toml
[project]
name = "fs-abaqus"
version = "0.1.0"
requires-python = ">=3.9"
dependencies = [
    "python-dotenv>=1.0.0",
    "requests>=2.31.0",
    "psutil>=5.9.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
]
```

---

## 七、运行方式

```bash
# 开发环境（使用 uv）
uv run python -m src.main

# 或激活虚拟环境后运行
uv sync
.venv\Scripts\activate  # Windows
python -m src.main

# 生产环境
uv run python run.py

# 后台运行（Windows）
uv run pythonw run.py
```

---
