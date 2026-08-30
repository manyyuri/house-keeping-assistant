# 三格电（断舍离家务整理 Agent · 省力）

基于本地轻量模型（默认）或云端 API 的断舍离家务管理应用：iPhone 拍照上传 → 视觉模型识别物品 → Agent 结合断舍离理论（山下英子《断舍离》）生成整理计划与任务。

## 架构

```
iPhone Safari ──局域网──► Vite dev :5173 ──proxy──► FastAPI :8000 ──┬─► Ollama :11434（本地，默认）
   (拍照/相册)                                     │              ├─ qwen3-vl:8b（视觉）
                                                   │              └─ needle（Agent 工具调用）
                                                   ├─► 云端 OpenAI 兼容 API（可选，见「云端 API 配置」）
                                                   │     ├─ vision：多模态模型（qwen-vl-plus / gpt-4o-mini / …）
                                                   │     └─ agent：function calling 模型（deepseek-chat / qwen3-max / …）
                                                   ├─ SQLite (server/data/app.db)
                                                   └─ 照片存储 (server/data/photos/yyyy-mm-dd/)
```

> Agent 模型同样默认 `qwen3-vl:8b`（已验证支持 function calling）；如需换回轻量 Agent 模型，可用环境变量 `AGENT_MODEL` 覆盖。

- **视觉与调度分离**：视觉通道只负责图 → 结构化中文 JSON（物品清单/区域/混乱度）；Agent 通道只负责 function calling 与计划编排——任何 provider 下都不混用
- **双通道并存**：本地 Ollama（免费、离线）与云端 API（OpenAI 兼容）可随时切换，视觉与 Agent 还可独立选路（如"照片不出内网 + 云端 Agent"）
- **断舍离理论内置**：`knowledge/duansheli/`（原书全文知识库副本，8 文件）；系统提示词启动时拼入 `cheatsheet.md`
- **评分防幻觉**：断舍离评分由 `server/rules.py` 纯规则计算，LLM 自报分数无效，与 provider 无关
- 通信：REST + SSE（对话流式输出，可随时停止生成）

## 快速开始（Mac）

### 1. 启动 Ollama 并拉取模型

```bash
# 安装 Ollama: https://ollama.com/download/mac
ollama pull qwen3-vl:8b   # 视觉 + Agent 共用（4bit 约 5.5GB 内存）
```

### 2. 启动后端

```bash
cd server
python3 -m venv ../.venv && ../.venv/bin/pip install -r requirements.txt
cd ..
.venv/bin/uvicorn server.main:app --host 0.0.0.0 --port 8000
# 启动日志会打印系统提示词拼装长度（确认断舍离速查表已注入）
```

> 默认 Python 3.9+ 均可运行（代码未使用 3.10+ 语法）。
> 模型/地址可用环境变量覆盖：`OLLAMA_URL`、`VISION_MODEL`、`AGENT_MODEL`。

### 3. 启动前端

```bash
cd web
npm install
npm run dev   # 已开 server.host，局域网可访问，/api 自动代理到 :8000
```

### 4. iPhone 使用

1. iPhone 与 Mac 连同一 Wi-Fi
2. Mac 浏览器打开 `http://localhost:5173`，左侧点「iPhone 扫码访问」
3. iPhone 扫码直达（`http://<Mac-IP>:5173`），对话页点 📷 直接调相机拍照
4. 备用路径：隔空投送照片到 Mac，再在 Mac 浏览器 Attachments 中上传

## 云端 API 配置（可选）

已购买云端 API key（OpenAI 兼容协议）时可随时切换，与本地 Ollama 二选一或混合使用。

### 操作步骤

1. 打开应用左侧「模型设置」（移动端在右上角 ⚙）：视觉模型与 Agent 模型各自独立选择服务商
2. 选「云端 API（OpenAI 兼容）」→ 填 base_url（可下拉选常用服务商）+ API key + 模型名
3. 先点「测试视觉」/「测试 Agent」验证连通与延迟，再保存——保存即生效（下次对话用新配置，无需重启）

### 服务商速查表（均已兼容 OpenAI 协议）

| 服务商 | base_url | 视觉模型示例 | Agent 模型示例 |
| --- | --- | --- | --- |
| 阿里云百炼 DashScope | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-vl-plus` | `qwen3-max` |
| DeepSeek | `https://api.deepseek.com/v1` | —（暂无视觉模型） | `deepseek-chat` |
| SiliconFlow 硅基流动 | `https://api.siliconflow.cn/v1` | `Qwen/Qwen2.5-VL-32B-Instruct` | `Qwen/Qwen3-32B` |
| 月之暗面 Moonshot | `https://api.moonshot.cn/v1` | `moonshot-v1-8k-vision-preview` | `kimi-k2-0905-preview` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` | `gpt-4o-mini` |
| OpenCode Luna | `https://opencode.ai/zen/go/v1` | `deepseek-v4-flash-vision-exp` | `deepseek-v4-flash` |

> 模型名以各家文档为准；Agent 通道需支持 function calling（DeepSeek/qwen3/kimi 均支持）。

### 隐私与安全

- **照片隐私**：视觉通道选云端时，照片（base64）会离开本机上传至该服务商处理；介意隐私可让视觉保持本地 Ollama、仅 Agent 走云端（混合模式）
- **密钥安全**：api_key 只存本机（`server/data/config.json` 已 gitignore，权限 600；或直接读取 `~/.pi/agent/models.json` 的 `opencode-luna` 提供方，不落本项目文件）；所有 GET 接口只回掩码 `sk-****末4位`，启动日志同样只打掩码
- **配置优先级**：环境变量 > `models.json`（opencode-luna）> `config.json`（UI 保存）> 代码默认值；被环境变量锁定的字段在 UI 中置灰且保存不生效
- **models.json 单点**：本机存在 `~/.pi/agent/models.json` 且含 `providers.opencode-luna` 时，视觉/Agent 端点自动使用其 `baseUrl`/`apiKey` 与对应模型（视觉 `deepseek-v4-flash-vision-exp`、Agent `deepseek-v4-flash`），修改即生效；UI 设置弹窗会标注来源。路径可用 `PI_MODELS_JSON` 覆盖

可用环境变量：`VISION_PROVIDER/AGENT_PROVIDER`、`VISION_BASE_URL/AGENT_BASE_URL`、`VISION_MODEL/AGENT_MODEL`、`VISION_API_KEY/AGENT_API_KEY`、`OLLAMA_URL`（本地 Ollama 地址）、`PI_MODELS_JSON`（pi 模型注册表路径）。

### REST 接口（供脚本/集成）

```bash
# 读配置（掩码视图）
curl localhost:8000/api/settings/llm
# 保存（api_key 留空 = 保持不变；切回 ollama 自动清空 key/base_url）
curl -X PUT localhost:8000/api/settings/llm -H 'Content-Type: application/json' \
  -d '{"agent":{"provider":"openai","base_url":"https://api.deepseek.com/v1","api_key":"sk-xx","model":"deepseek-chat"}}'
# 测试连接（用表单当前值，可保存前先测）
curl -X POST localhost:8000/api/settings/llm/test -H 'Content-Type: application/json' \
  -d '{"scope":"agent","endpoint":{"provider":"openai","base_url":"https://api.deepseek.com/v1","api_key":"sk-xx","model":"deepseek-chat"}}'
```

## 功能验收

| 验收项 | 说明 |
| --- | --- |
| 知识库内置 | `knowledge/duansheli/` 8 文件随仓库；启动日志打印 system prompt 长度 |
| 照片 → 计划 | 上传照片 + "帮我按断舍离整理" → SSE 流式返回识别、评估、计划、任务 |
| 评分可信 | `plans.danshari_score` 始终来自 `rules.py`，Needle 无法覆盖；评分语义是「代谢率」——
            该舍未舍（高/中混乱却零丢弃）与未决物品也会扣分，堵住"全 keep 得满分"的幻觉 |
| 物品稳定身份 | 同名物品同张照片内自动合并（`save_items` 归一化去重）；判定按归一化名匹配同批同类全部行，
            并回传 matched 可追溯（`judge_items`）；计划丢/捐/留计数由后端从 items 表实时聚合，不信任 LLM 自报 |
| 可中断 | Sender 取消按钮断开 SSE，后端检测断连终止管道 |
| 犹豫观察期 | hesitate 自动 +90 天，语义是「不急着决定」：到期在「成果统计」页温柔提醒再看一眼；对话首页空态显示「没急着决定的，到期了」横幅，一键跳去复查 |
| 三格电首页 | 打开即问「今天还剩多少力气？」（满格/半格/没电）；电量真的改变内容供给：满格→15 分钟任务+可选菜单，半格→5 分钟任务+直接给晚餐，没电→2 分钟任务（或今天就歇着）+不指责的话；任务显式标「约 X 分钟」 |
| 加分制表达 | 评分规则引擎保留（防幻觉），对外从「扣分制」翻成「加分制」：成果页主角是努力轨迹（这周完成 N 件最小的事，比上周多 X 件），分数降为「代谢率参考」 |
| 反打卡 | 不设连击/绿点/打卡语汇；今天不做没关系，「不急着决定」和「今天就歇着」都是合法选项；兜底建议做了也不记账（诚实，不给云表扬） |
| 时间轴账本 | 家的账（任务完成/计划创建）+ 身体的账（吃掉的餐）共用一条时间轴；任务 done、餐 eaten 打真实时间戳，只记诚实可追溯的事件 |
| HEIC 兼容 | 上传自动转码：EXIF 转正 → RGB → 最长边 1024 JPEG（前端另有 1280 压缩） |
| 捐赠清单 | 物品库勾选 → 一键导出 txt |
| 降级 | Ollama 不可达时提示"请先启动 Ollama 并拉取模型"，视觉非 JSON 输出自动降级 |
| 云端 API | 设置弹窗可切换视觉/Agent 至云端（OpenAI 兼容），保存即生效；key 错误/模型名错/断网均有中文错误提示 |
| 混合模式 | 视觉本地 + Agent 云端（或反向）均可出计划；断舍离评分始终来自 rules.py |
| 二段式识别 | 每张照片两遍扫描：①全局逐一识别 ②小物件专项补扫，新增项标「待确认」，Agent 先向用户确认再入库（knowledge/vision-enhancement）；`VISION_TWO_PASS=0` 可关 |
| 回归测试 | `.venv/bin/python -m server.test_db`（存储层）、`.venv/bin/python -m server.test_battery`（三格电引擎：
            档位上限硬约束/诚实记账/餐食供给）、`.venv/bin/python -m server.test_vision`（识别纯函数）、
            `.venv/bin/python -m server.test_meal_rules`（三餐规则+种子库门禁）、
            `.venv/bin/python -m server.test_agent`（Agent 循环：工具调用/未知工具/最大轮数/去重）、
            `.venv/bin/python -m server.test_chat_pipeline`（SSE 全链路：mock 视觉+Agent，验证事件流与落库） |
| 今日三餐 | 打开「今日三餐」页自动生成今天+明天菜单（拳头法则规则引擎，离线可用）；晚餐后顺手做明日便当（bento 锁：制作日 19:00 后禁换）；换菜自动同步盒马五分区买菜清单；对话可问“今天吃什么”、说“换个晚餐” |

## 开发调试

```bash
# 视觉识别单测（无 Ollama 时用 --mock）
.venv/bin/python -m server.vision <photo_id 或图片路径> --mock

# SSE 事件序列观察
curl -N -G "localhost:8000/api/chat" \
  --data-urlencode "conversation_id=1" \
  --data-urlencode "message=帮我整理衣柜" \
  --data-urlencode "photo_ids=1"

# 模型可用性探测（按当前配置路由到对应 provider）
.venv/bin/python -m server.ollama_client

# provider 抽象层单测（消息转换/配置优先级/掩码，无网络依赖）
.venv/bin/python -m server.test_llm_providers

# 无真实 key 的云端全链路联调（mock openai：vision 返回固定 JSON、agent 按剧本返回 tool_calls）
.venv/bin/python scripts/mock_openai_server.py &   # 默认 127.0.0.1:9101，key 需 sk-good 开头
# 然后 UI/PUT 配置 base_url=http://127.0.0.1:9101/v1 即可跑通 SSE 全流程
```

## 目录结构

```
├── knowledge/
│   ├── duansheli/         # 断舍离理论知识库（cheatsheet 进运行时提示词，其余供维护查阅）
│   └── recipes/           # 三餐种子菜谱库（39 道，含带饭友好标准）
├── scripts/               # 联调工具
│   └── mock_openai_server.py  # mock 云端 API（vision 固定 JSON + agent 剧本 tool_calls）
├── server/                # FastAPI 后端
│   ├── main.py            # REST + /api/chat SSE 管道 + 模型设置三端点 + /api/home + /api/timeline
│   ├── db.py              # SQLite 建表 + DAO（物品/计划/任务/菜谱/餐计划/买菜清单/时间轴账本）
│   ├── battery.py         # 三格电引擎：按当天精力供给最小行动+餐食+努力轨迹（省力概念核心）
│   ├── meals.py           # 三餐推荐引擎（幂等生成/换菜/清单聚合，LLM 仅小贴士可降级）
│   ├── llm_providers.py   # LLM 运行时配置（ENV > config.json > 默认）+ 掩码/锁定
│   ├── ollama_client.py   # 模型访问路由层（对外签名不变）
│   ├── ollama_provider.py # Ollama adapter
│   ├── openai_provider.py # OpenAI 兼容 adapter（消息协议转换 + 错误映射）
│   ├── vision.py          # 视觉识别 + 容错解析（provider 无关）
│   ├── agent.py           # Agent 循环（≤5 轮，provider 无关）
│   ├── tools.py           # 八工具（入库/判定/计划/任务/查询/状态/三餐查询/换菜）
│   ├── prompts.py         # 系统提示词（§8.1 全文 + cheatsheet）
│   ├── rules.py           # 断舍离硬规则（评分/观察期）
│   ├── meal_rules.py      # 拳头法则硬规则（餐模板/份量校验/轮换去重/带饭筛选）
│   └── data/              # 运行时生成：app.db + photos/ + config.json（已 gitignore）
└── web/                   # React 18 + antd 6 + @ant-design/x v2
    └── src/pages/         # BatteryHome（三格电首页）/ ChatPage（对话）/ MealsPage（今日三餐）/ TasksPage / ItemsPage / StatsPage（含时间轴账本）/ SettingsPage（模型设置弹窗）
```

## 断舍离方法论速览（内置规则来源）

- **三层筛子**：垃圾废品直接清 → 自我轴×时间轴 → 必要·合适·愉快终审
- **收纳五指南**：7·5·1 法 / 三分法 / 1 out 1 in / one touch / 自立·自由·自在
- **顺序铁则**：先取舍、后收纳、再清扫——绝不"先买收纳盒"
- **家人之物**：不判定、不代扔，以舒适空间感染对方

详见 `knowledge/duansheli/`（章节精读 / 术语表 / 10 个可复用模式）。
