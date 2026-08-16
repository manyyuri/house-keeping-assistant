# 断舍离家务整理 Agent

基于本地轻量模型的断舍离家务管理应用：iPhone 拍照上传 → 视觉模型识别物品 → Agent 结合断舍离理论（山下英子《断舍离》）生成整理计划与任务。

## 架构

```
iPhone Safari ──局域网──► Vite dev :5173 ──proxy──► FastAPI :8000 ──► Ollama :11434
   (拍照/相册)                                     │              ├─ qwen3-vl:8b（视觉）
                                                   │              └─ needle（Agent 工具调用）
                                                   ├─ SQLite (server/data/app.db)
                                                   └─ 照片存储 (server/data/photos/yyyy-mm-dd/)
```

- **视觉与调度分离**：qwen3-vl:8b 只负责图 → 结构化中文 JSON（物品清单/区域/混乱度）；needle 只负责 function calling 与计划编排
- **断舍离理论内置**：`knowledge/duansheli/`（原书全文知识库副本，8 文件）；系统提示词启动时拼入 `cheatsheet.md`
- **评分防幻觉**：断舍离评分由 `server/rules.py` 纯规则计算，LLM 自报分数无效
- 通信：REST + SSE（对话流式输出，可随时停止生成）

## 快速开始（Mac）

### 1. 启动 Ollama 并拉取模型

```bash
# 安装 Ollama: https://ollama.com/download/mac
ollama pull qwen3-vl:8b   # 视觉模型（4bit 约 5.5GB 内存；32GB 机器可换 qwen3-vl:30b）
ollama pull needle        # Agent 模型（14MB）
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

## 功能验收

| 验收项 | 说明 |
| --- | --- |
| 知识库内置 | `knowledge/duansheli/` 8 文件随仓库；启动日志打印 system prompt 长度 |
| 照片 → 计划 | 上传照片 + "帮我按断舍离整理" → SSE 流式返回识别、评估、计划、任务 |
| 评分可信 | `plans.danshari_score` 始终来自 `rules.py`，Needle 无法覆盖 |
| 可中断 | Sender 取消按钮断开 SSE，后端检测断连终止管道 |
| 犹豫观察期 | hesitate 自动 +90 天，到期在「成果统计」页提醒复查 |
| HEIC 兼容 | 上传自动转码：EXIF 转正 → RGB → 最长边 1024 JPEG（前端另有 1280 压缩） |
| 捐赠清单 | 物品库勾选 → 一键导出 txt |
| 降级 | Ollama 不可达时提示"请先启动 Ollama 并拉取模型"，视觉非 JSON 输出自动降级 |

## 开发调试

```bash
# 视觉识别单测（无 Ollama 时用 --mock）
.venv/bin/python -m server.vision <photo_id 或图片路径> --mock

# SSE 事件序列观察
curl -N -G "localhost:8000/api/chat" \
  --data-urlencode "conversation_id=1" \
  --data-urlencode "message=帮我整理衣柜" \
  --data-urlencode "photo_ids=1"

# 模型可用性探测
.venv/bin/python -m server.ollama_client
```

## 目录结构

```
├── knowledge/duansheli/   # 断舍离理论知识库（cheatsheet 进运行时提示词，其余供维护查阅）
├── server/                # FastAPI 后端
│   ├── main.py            # REST + /api/chat SSE 管道
│   ├── db.py              # SQLite 建表 + DAO
│   ├── ollama_client.py   # 视觉/Agent 双客户端
│   ├── vision.py          # 视觉识别 + 容错解析
│   ├── agent.py           # Needle 循环（≤5 轮）
│   ├── tools.py           # 六工具（入库/判定/计划/任务/查询/状态）
│   ├── prompts.py         # 系统提示词（§8.1 全文 + cheatsheet）
│   ├── rules.py           # 断舍离硬规则（评分/观察期）
│   └── data/              # 运行时生成：app.db + photos/
└── web/                   # React 18 + antd 6 + @ant-design/x v2
    └── src/pages/         # ChatPage（对话）/ TasksPage / ItemsPage / StatsPage
```

## 断舍离方法论速览（内置规则来源）

- **三层筛子**：垃圾废品直接清 → 自我轴×时间轴 → 必要·合适·愉快终审
- **收纳五指南**：7·5·1 法 / 三分法 / 1 out 1 in / one touch / 自立·自由·自在
- **顺序铁则**：先取舍、后收纳、再清扫——绝不"先买收纳盒"
- **家人之物**：不判定、不代扔，以舒适空间感染对方

详见 `knowledge/duansheli/`（章节精读 / 术语表 / 10 个可复用模式）。
