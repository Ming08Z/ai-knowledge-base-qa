# AI 知识库问答系统

一个面向个人学习与资料管理的 AI 知识库问答系统。项目采用 TypeScript 前端与 Python/FastAPI 后端，使用 MySQL 保存账号和结构化业务数据，使用本地 Qdrant 保存文档向量，支持知识库问答、原文引用、PDF 原件高亮、历史会话、模拟测验、错题本和自定义模型 API。

## 1. 系统说明

### 1.1 建设目标

系统用于把 Word、PDF、TXT 和 Markdown 文档整理为可检索的个人知识库。用户登录后可以跨浏览器读取自己的知识库、会话和测验记录，并通过语义检索让 AI 依据当前勾选的知识库文件夹回答问题。

系统主要解决以下问题：

- 将分散文档统一上传、解析、分段和索引。
- 让 AI 回答尽量基于知识库原文，而不是脱离资料自由回答。
- 在回答右侧展示实际检索到的参考片段，并在 PDF 原件页面高亮引用位置。
- 将知识库内容转换为单选题、多选题和简答题，用于学习与复习。
- 保存历史会话、测验结果和错题数据，避免更换浏览器后丢失。

### 1.2 当前功能

#### 用户与设置

- 用户注册、登录和退出。
- 登录会话使用 HttpOnly Cookie，默认有效期 30 天。
- 用户数据按账号隔离并保存到 MySQL。
- 设置界面支持小、中、大三档字体。
- 支持亮色/暗色主题。
- 支持中文/英文界面，并在刷新后保留语言设置。
- 登录状态和退出功能集中在设置弹窗中。

#### 知识库

- 创建、选择、重命名和删除知识库文件夹。
- 上传 Word（`.docx`）、PDF（`.pdf`）、TXT（`.txt`）和 Markdown（`.md`）。
- 保存文件原件、解析文本、文件状态、元数据和文档简介。
- 支持服务器重新解析失败文件。
- 解析完成后自动建立语义向量索引。
- 自动识别目录和章节标题，按章节切分后再生成带重叠的文本片段。
- 新解析文件可由 AI 生成简短简介，用户也可手动编辑简介。
- 支持原件和解析后文本预览。
- PDF 引用预览采用按可见区域加载、同文件请求合并和浏览器缓存，减少公网重复下载。

#### AI 会话

- 新建会话、切换会话、重命名和删除会话。
- 首条用户消息作为初始标题；第二轮后总结对话主题，之后不再自动改名。
- 按会话标题和消息内容搜索历史会话，并展示匹配片段及高亮搜索词。
- AI 回答采用流式输出，并支持停止生成。
- 对话可导出为 TXT 或 Word 文档。
- 可在输入框旁勾选一个或多个知识库文件夹，后续新勾选的文件夹会立即参与检索。
- 回答右侧只显示实际检索到的原文片段。
- PDF 参考片段直接渲染原 PDF 页面并高亮引用内容；非 PDF 文件显示对应原文片段。
- 关闭参考片段或更新界面时尽量保持聊天滚动位置。

#### 模型配置

- 内置模型选项：`deepseek-v4-flash`、`deepseek-v4-pro`。
- 每个用户可单独填写自己的 API Key、接口地址和模型名称。
- 预设支持 DeepSeek、OpenAI、通义千问、Moonshot/Kimi、智谱 GLM、SiliconFlow 和 OpenRouter。
- 支持其他兼容 OpenAI Chat Completions 协议的 HTTPS 公网接口。
- 用户 API Key 在后端加密保存，前端只显示掩码，不会读取完整密钥。

#### 测验模式

- 支持单选题、多选题、简答题和混合题型。
- 可选择当前文件夹、多个文件夹或全部知识库作为出题范围。
- 出题时尽量从整本文档和不同章节均匀取材。
- 每题显示分值；简答题提交后进入后台 AI 批改，用户可直接继续下一题。
- 所有简答题批改完成后统一显示得分、参考答案、反馈和测验报告。
- 保存完整测验记录，包括题目、选项、用户答案、正确答案、解析和来源。
- 测验记录可导出为 Excel。
- 历史测验支持查看和删除，删除后同步到账号数据。
- 错题自动进入错题本，统计错误次数、答对次数和薄弱知识点。
- 错题本支持搜索题目、选项、答案、解析、来源和知识点。
- 点击薄弱知识点或题目知识点标签，可筛选对应错题。
- 支持在错题本右上角手动添加单选题、多选题或简答题，并填写答案、解析、知识点、来源和分值。
- 已经答对过的错题可以手动移出错题本。

### 1.3 技术栈

| 层级 | 技术 | 用途 |
| --- | --- | --- |
| 前端 | HTML5、CSS3、TypeScript 5.9 | 页面、状态管理、交互和业务逻辑 |
| 文档预览 | PDF.js、Mammoth.js | PDF 页面渲染、Word 原件转换 |
| 后端 | Python 3.12、FastAPI、Uvicorn | API、静态文件、登录、AI 代理和文件服务 |
| 数据访问 | SQLAlchemy 2、PyMySQL | MySQL ORM 和连接管理 |
| 结构化数据 | MySQL 8.0 | 用户、会话、文件元数据、测验记录和设置 |
| 文档解析 | pypdf、ZIP/XML | PDF、DOCX、TXT、Markdown 文本提取 |
| 向量检索 | Qdrant Local、FastEmbed | 本地向量存储和语义检索 |
| 向量模型 | `BAAI/bge-small-zh-v1.5` | 中英文知识片段向量化 |
| AI 接口 | OpenAI Chat Completions 兼容协议 | 问答、简介生成、出题和简答题批改 |
| 公网访问 | Cloudflare Tunnel | 将本机 `localhost:8000` 暴露为 HTTPS 地址 |

## 2. 概要设计

### 2.1 总体架构

```mermaid
flowchart LR
    B[浏览器 / TypeScript 前端]
    A[FastAPI 后端]
    M[(MySQL 8.0)]
    Q[(Qdrant Local)]
    F[(backend/data 文件存储)]
    L[AI 模型 API]

    B -->|同源页面与 /api 请求| A
    A -->|用户、会话、测验、元数据| M
    A -->|向量写入与语义检索| Q
    A -->|原件与解析文本| F
    A -->|流式 Chat Completions| L
```

项目在源码层面前后端分离：前端源代码位于 `frontend/`，后端位于 `backend/`。部署时由 FastAPI 同源提供 `index.html` 和编译后的 `main.js`，因此浏览器无需单独配置 CORS，登录 Cookie 和 API 请求也使用同一域名。

### 2.2 核心数据流

#### 文件上传与索引

```mermaid
sequenceDiagram
    participant U as 用户浏览器
    participant A as FastAPI
    participant D as 文件存储
    participant M as MySQL
    participant Q as Qdrant

    U->>A: 上传文件与文件元数据
    A->>D: 保存 original.bin 和 parsed.txt
    A->>A: 提取文本、识别目录与章节、切片
    A->>M: 保存文件状态和元数据
    A->>Q: 写入片段向量及用户/文件夹标识
    A-->>U: 返回解析和索引结果
```

文档切片默认每段约 700 个字符，重叠约 120 个字符。索引载荷包含用户 ID、文件 ID、文件夹 ID、文件名、章节名和原文片段，以便检索时进行用户与文件夹过滤。

#### 知识库问答

```mermaid
sequenceDiagram
    participant U as 用户浏览器
    participant S as 语义检索 API
    participant Q as Qdrant
    participant C as AI 代理 API
    participant L as 模型服务

    U->>S: 问题 + 当前勾选的文件夹 ID
    S->>Q: 用户过滤 + 文件夹过滤 + 向量检索
    Q-->>S: 相关原文片段
    S-->>U: 片段、章节、文件和匹配词
    U->>C: 问题、检索上下文、stream=true
    C->>L: Chat Completions 请求
    L-->>C: 流式响应
    C-->>U: 逐块转发回答
```

前端只把当前用户勾选范围内检索到的片段加入提示词。右侧参考面板使用同一批检索结果，因此展示内容与本次回答上下文一致。

#### 测验与错题本

1. 前端按用户选择的知识库范围取得多个章节片段。
2. AI 根据题型、数量、难度和界面语言生成题目。
3. 客观题在前端判分；简答题调用后端 AI 接口异步批改。
4. 全部题目完成后，将题目、作答、得分、答案、解析和来源写入测验记录。
5. 错题本从历史测验动态汇总，同一题按稳定题目特征合并并累计错误频率。

### 2.3 模块划分

```text
ai知识库问答界面/
├─ frontend/
│  ├─ index.html              # 页面结构、CSS、第三方浏览器库入口
│  ├─ src/main.ts             # TypeScript 前端源代码
│  └─ dist/main.js            # TypeScript 编译产物，浏览器实际加载
├─ backend/
│  ├─ app.py                  # FastAPI 应用、健康检查、AI 流式代理、前端静态入口
│  ├─ auth.py                 # 注册、登录、退出、Cookie 会话和密码哈希
│  ├─ database.py             # SQLAlchemy 模型和 MySQL 连接
│  ├─ persistence.py          # 用户状态、文件原件和解析文本接口
│  ├─ document_parser.py      # PDF、DOCX、TXT、Markdown 服务端解析
│  ├─ vector_store.py         # 章节切分、向量索引、检索和重建索引
│  ├─ model_config.py         # 用户自定义模型与加密 API Key
│  ├─ setup_mysql.py          # MySQL 数据库和应用账号初始化
│  ├─ data/                   # 文件原件与解析文本，不应提交到公开仓库
│  └─ vector_data/            # Qdrant 本地向量数据，可由原文重建
├─ tools/README.md            # cloudflared 等本机部署工具的获取说明
├─ environment.yml            # Conda 环境 a1
├─ package.json               # TypeScript 构建脚本
├─ tsconfig.json              # TypeScript 编译配置
├─ start.bat                  # Windows 一键启动脚本
└─ README.md
```

### 2.4 数据库设计

应用启动时使用 SQLAlchemy 自动创建缺失的数据表。

| 表名 | 主要内容 | 关键约束 |
| --- | --- | --- |
| `users` | 用户名、密码哈希、创建时间 | 用户名唯一 |
| `auth_sessions` | 登录令牌哈希、过期时间 | 按用户关联，令牌唯一 |
| `user_preferences` | 字体、主题、语言、当前选择等 | 每个用户一条 |
| `user_model_configs` | 提供商、接口、模型、加密 API Key | 每个用户一条 |
| `knowledge_folders` | 文件夹名称和前端扩展数据 | 用户 ID + 文件夹 ID 复合主键 |
| `conversations` | 会话标题、消息列表、更新时间 | 用户 ID + 会话 ID 复合主键 |
| `quiz_records` | 完整题目、作答、得分和报告 | 用户 ID + 测验 ID 复合主键 |
| `file_metadata` | 文件名、文件夹、状态、简介和存储标识 | 用户 ID + 文件 ID 复合主键 |

密码使用 PBKDF2-SHA256 加盐哈希，当前迭代次数为 310,000。登录 Cookie 中保存随机令牌，MySQL 只保存令牌的 SHA-256 摘要。

### 2.5 文件与向量存储

每个上传文件保存在以下目录：

```text
backend/data/<用户ID>/<文件ID>/
├─ original.bin       # 文件原件
├─ original-name.txt  # 原始文件名
├─ mime.txt           # MIME 类型
└─ parsed.txt         # 解析后的纯文本
```

向量数据保存在 `backend/vector_data/`。Qdrant 中每个向量点都带有 `user_id`，检索接口还会按当前登录用户和选中的 `folder_id` 过滤，避免不同账号或未勾选文件夹之间的数据混用。

### 2.6 API 概览

| 方法 | 路径 | 说明 | 是否登录 |
| --- | --- | --- | --- |
| `GET` | `/api/health` | 后端、MySQL、模型配置和向量库状态 | 否 |
| `POST` | `/api/auth/register` | 注册并创建登录会话 | 否 |
| `POST` | `/api/auth/login` | 登录 | 否 |
| `POST` | `/api/auth/logout` | 退出并删除当前会话 | 否 |
| `GET` | `/api/auth/me` | 获取当前账号 | 是 |
| `GET/PUT` | `/api/state` | 读取或保存用户业务状态 | 是 |
| `PUT` | `/api/files/{id}/payload` | 保存原件和解析文本并建立索引 | 是 |
| `POST` | `/api/files/{id}/reparse` | 服务器重新解析文件 | 是 |
| `GET` | `/api/files/{id}/payload` | 获取解析文本和原件地址 | 是 |
| `GET` | `/api/files/{id}/content` | 获取文件原件 | 是 |
| `DELETE` | `/api/files/{id}/payload` | 删除文件数据和向量索引 | 是 |
| `POST` | `/api/semantic/search` | 按用户和文件夹执行语义检索 | 是 |
| `POST` | `/api/semantic/reindex` | 重建当前用户的全部向量索引 | 是 |
| `GET/PUT` | `/api/model-config` | 读取或保存当前用户的模型配置 | 是 |
| `POST` | `/api/chat/completions` | 同源 AI 接口代理，支持流式输出 | 是 |

## 3. 部署流程

### 3.1 环境要求

- Windows 10/11 或可运行 Python、Node.js 和 MySQL 的服务器。
- Conda/Anaconda。
- Python 3.12。
- Node.js 22。
- MySQL 8.0，服务需在启动应用前运行。
- 可访问所选 AI 服务和模型下载站点的网络。
- 首次使用语义检索时，需要下载 `BAAI/bge-small-zh-v1.5`。

### 3.2 创建 Conda 环境

在项目根目录执行：

```powershell
conda env create -f environment.yml
conda activate a1
npm ci
```

如果 `a1` 已存在，可以更新环境：

```powershell
conda env update -n a1 -f environment.yml --prune
conda activate a1
npm ci
```

### 3.3 初始化 MySQL

先确认 MySQL 8.0 已启动，然后运行：

```powershell
conda activate a1
python backend\setup_mysql.py
```

脚本会提示输入 MySQL 管理员主机、端口、账号和密码，并自动完成：

- 创建数据库 `ai_knowledge_base`。
- 创建最小范围的应用账号 `ai_kb_user`。
- 为应用账号授予该数据库权限。
- 在项目根目录生成 `.env` 中的 `DATABASE_URL`。

MySQL 管理员密码不会写入项目文件。不要把生成后的 `.env` 提交到 Git 或发送给其他人。

### 3.4 配置环境变量

推荐在项目根目录创建或补充 `.env`：

```dotenv
DATABASE_URL=mysql+pymysql://ai_kb_user:请替换为应用密码@127.0.0.1:3306/ai_knowledge_base?charset=utf8mb4
API_KEY=请替换为服务端内置模型的API密钥
BASE_URL=https://api.deepseek.com
MODEL_CONFIG_SECRET=请替换为长期稳定的随机密钥
EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
```

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | 是 | MySQL SQLAlchemy 连接地址，由初始化脚本生成 |
| `API_KEY` | 使用内置模型时必填 | 服务端默认 AI API Key |
| `BASE_URL` | 否 | 默认 `https://api.deepseek.com`，代码会补充 `/chat/completions` |
| `MODEL_CONFIG_SECRET` | 强烈建议 | 加密用户自定义 API Key；部署后应保持不变 |
| `EMBEDDING_MODEL` | 否 | 默认 `BAAI/bge-small-zh-v1.5` |

`backend/config.js` 仅为旧配置兼容入口，后端可能读取其中的 `API_KEY` 和 `BASE_URL`，但该文件不会由网页提供。新部署应优先使用 `.env`，并及时移除旧文件中的真实密钥。

### 3.5 构建前端

修改 `frontend/src/main.ts` 后必须重新编译：

```powershell
conda activate a1
npm run build
```

编译结果写入 `frontend/dist/main.js`。浏览器不会直接执行 `frontend/src/main.ts`。

### 3.6 启动本地服务

方式一：双击或运行一键脚本。

```powershell
.\start.bat
```

方式二：手动启动。

```powershell
conda activate a1
npm run build
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

浏览器访问：

```text
http://localhost:8000/
```

不要直接双击 `frontend/index.html` 或使用 `file://` 打开。登录、文件和 AI 功能依赖后端 `/api`，必须通过 Uvicorn 地址访问。

### 3.7 检查运行状态

在 PowerShell 中执行：

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/health
```

正常响应示例：

```json
{
  "ok": true,
  "apiConfigured": true,
  "databaseConfigured": true,
  "vectorStore": "qdrant-local",
  "embeddingModel": "BAAI/bge-small-zh-v1.5"
}
```

`apiConfigured=false` 表示服务端内置模型密钥未配置；已配置个人 API 的用户仍需先正常登录。`databaseConfigured=false` 表示 MySQL 未启动或 `DATABASE_URL` 无效。

### 3.8 临时公网部署（Cloudflare Quick Tunnel）

适用于演示和临时分享。源码仓库不提交大型可执行文件，请先从 Cloudflare 官方发布页下载 `cloudflared.exe` 并放入 `tools/`。保持本地 Uvicorn 运行，再打开另一个 PowerShell：

```powershell
.\tools\cloudflared.exe tunnel --url http://127.0.0.1:8000 --protocol http2 --no-autoupdate
```

终端会输出一个形如以下格式的 HTTPS 地址：

```text
https://随机名称.trycloudflare.com
```

注意：

- 该地址是临时地址，隧道重启后可能变化。
- 本机、Uvicorn 和 `cloudflared.exe` 必须持续运行。
- 不适合作为长期正式生产域名。
- 如果 QUIC 连接不稳定，保留 `--protocol http2`。

### 3.9 固定域名部署（Cloudflare Named Tunnel）

固定网址需要 Cloudflare 账号和已经接入 Cloudflare 的域名。以下以 `kb.example.com` 为例：

```powershell
.\tools\cloudflared.exe tunnel login
.\tools\cloudflared.exe tunnel create ai-knowledge-base
.\tools\cloudflared.exe tunnel route dns ai-knowledge-base kb.example.com
```

在 Cloudflare 配置目录创建 `config.yml`，将 UUID 和凭据路径替换为实际值：

```yaml
tunnel: <TUNNEL-UUID>
credentials-file: C:\Users\<用户名>\.cloudflared\<TUNNEL-UUID>.json

ingress:
  - hostname: kb.example.com
    service: http://127.0.0.1:8000
  - service: http_status:404
```

启动固定隧道：

```powershell
.\tools\cloudflared.exe tunnel run ai-knowledge-base
```

正式环境建议把 Uvicorn 和 Tunnel 配置为系统服务，并为 MySQL、`backend/data` 和 `.env` 设置严格的文件权限。

### 3.10 Linux/云服务器部署建议

在 Linux 服务器上可使用同样的 Python 和 Node.js 构建流程，完成 MySQL 配置后由 Uvicorn 提供应用：

```bash
conda env create -f environment.yml
conda activate a1
npm ci
npm run build
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

生产环境建议使用 systemd 管理 Uvicorn，通过 Nginx、Caddy 或 Cloudflare Tunnel 提供 HTTPS。当前代码中的登录 Cookie 为本地 HTTP 调试设置了 `secure=False`；如果直接面向正式 HTTPS 域名部署，应把 Cookie 改为仅 HTTPS 发送，并根据实际代理设置可信主机、转发头和安全策略。

## 4. 开发说明

### 4.1 前端开发

```powershell
conda activate a1
npm run watch
```

`npm run watch` 会持续监视 `frontend/src/**/*.ts` 并更新 `frontend/dist/`。页面和大部分样式集中在 `frontend/index.html`，主要业务逻辑位于 `frontend/src/main.ts`。

前端使用原生 TypeScript 和 DOM API，没有引入 React/Vue。状态在登录后以服务器 MySQL 数据为准，同时在浏览器 `localStorage` 保存界面缓存和迁移数据。首次登录时，旧浏览器本地数据可自动迁移一次。

### 4.2 后端开发

开发时可启用自动重载：

```powershell
conda activate a1
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
```

不要在生产环境使用 `--reload`。

### 4.3 重建语义索引

当章节切分算法、Embedding 模型或索引结构发生变化时，可以登录后调用：

```text
POST /api/semantic/reindex
```

也可以删除 `backend/vector_data/` 后重启并重新索引。删除向量目录前必须确保 `backend/data/` 和 MySQL 文件元数据仍完整，否则无法恢复索引。

## 5. 数据备份与恢复

完整备份至少包含三部分：

1. MySQL 数据库 `ai_knowledge_base`。
2. `backend/data/` 中的文件原件和解析文本。
3. 项目根目录 `.env`，应加密保管，不要放进普通压缩包公开传输。

Qdrant 的 `backend/vector_data/` 建议一并备份，但它可以根据 `backend/data/*/parsed.txt` 和 MySQL 元数据重建。

MySQL 备份示例：

```powershell
mysqldump -u root -p --single-transaction --routines --triggers ai_knowledge_base > ai_knowledge_base.sql
```

恢复示例：

```powershell
mysql -u root -p ai_knowledge_base < ai_knowledge_base.sql
```

恢复后确认文件目录中的用户 ID、文件 ID 与数据库记录一致，再启动后端或执行重建索引。

## 6. 安全说明

- 不要提交或公开 `.env`、真实 API Key、数据库密码、Tunnel 凭据和 `backend/data/`。
- 用户密码只保存 PBKDF2 哈希，不保存明文。
- 登录 Cookie 使用 HttpOnly，前端 JavaScript 无法读取会话令牌。
- 自定义模型 API Key 使用 Fernet 对称加密保存；`MODEL_CONFIG_SECRET` 变化后，旧密钥将无法解密，需要用户重新填写。
- 自定义接口必须是 HTTPS 公网地址，后端拒绝 localhost、内网、保留地址和带账号密码的 URL，以降低 SSRF 风险。
- 前端不直接请求模型提供商，所有 AI 请求经后端代理，避免把服务端密钥暴露给浏览器。
- 当前 `/api/state` 使用用户状态快照同步。多人同时使用同一账号修改数据时，后保存的状态可能覆盖先保存的状态，不建议多人共享账号并发编辑。

## 7. 已知限制

- 扫描版 PDF 没有文本层时，当前版本不包含 OCR，可能提示未提取到有效文本。
- PDF.js 和 Mammoth.js 当前从公共 CDN 加载；网络无法访问相应 CDN 时，原件渲染可能失败，但服务端解析文本仍可使用。
- 第一次语义检索会下载并加载 Embedding 模型，速度明显慢于后续请求。
- Qdrant 使用单机本地模式，适合单实例部署；多实例部署应改为独立 Qdrant 服务。
- 文件原件保存在本机磁盘，不会自动复制到其他服务器。
- Cloudflare Quick Tunnel 的网址不是固定域名。
- 内置模型名称是否可用取决于实际模型服务商；如果服务商不支持界面中的名称，请使用“API 与模型设置”填写真实模型名。

## 8. 常见问题

### 页面打开后是空白

不要使用 `file://`。先确认 Uvicorn 正常运行，再打开 `http://localhost:8000/`。如果刚更新前端，执行 `npm run build` 并强制刷新浏览器。

### 已注册账号无法登录

检查 `/api/health` 中 `databaseConfigured` 是否为 `true`，确认浏览器允许当前域名写入 Cookie，并查看 MySQL 服务是否运行。登录必须始终使用同一个 HTTP/HTTPS 域名，不能在 `file://` 页面登录。

### 文件解析失败

- 确认文件扩展名为 `.docx`、`.pdf`、`.txt` 或 `.md`。
- 确认 PDF 不是纯扫描图片。
- 尝试在知识库中点击重新解析。
- 检查 `backend/data/<用户ID>/<文件ID>/original.bin` 是否存在。
- 查看后端终端中的具体异常。

### PDF 预览加载较慢

公网首次打开仍需下载原件。系统会合并同一 PDF 的并发请求、缓存文件并延迟加载屏幕外的引用页；同一页面后续查看通常更快。大文件性能还会受到本机上行带宽和 Tunnel 网络影响。

### 语义检索首次很慢或不可用

首次使用需要下载 Embedding 模型。检查网络和磁盘空间；中国大陆网络默认使用 Hugging Face 镜像。如果修改了模型或章节切分规则，调用 `/api/semantic/reindex` 重建索引。

### 公网地址返回 502 或无法连接

确认以下两个进程都在运行：

1. `python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000`
2. `cloudflared.exe tunnel --url http://127.0.0.1:8000 --protocol http2`

先访问本地 `/api/health`，本地正常后再检查 Tunnel 日志。

### 自定义 API Key 保存后无法使用

确认模型名和接口地址与提供商文档一致。若修改过 `MODEL_CONFIG_SECRET`、`API_KEY` 或数据库连接字符串，旧密钥的加密派生值可能变化，需要在设置中重新填写 API Key。

## 9. 运行检查清单

- [ ] MySQL 8.0 已启动。
- [ ] Conda 环境 `a1` 已创建并安装依赖。
- [ ] 项目根目录 `.env` 已配置且未公开。
- [ ] `npm run build` 已成功生成 `frontend/dist/main.js`。
- [ ] `/api/health` 返回 `databaseConfigured: true`。
- [ ] 可以注册、登录并在刷新后保持登录状态。
- [ ] 文件可以上传、解析、预览和建立索引。
- [ ] 勾选知识库后，问答能返回对应参考片段。
- [ ] 测验记录、错题本和历史会话刷新后仍存在。
- [ ] 公网部署时，本地后端和 Tunnel 均持续运行。

---

本项目当前适合个人学习、毕业设计演示和单机/单实例部署。若用于正式多用户生产环境，建议进一步增加数据库迁移工具、对象存储、独立 Qdrant 服务、任务队列、速率限制、审计日志、自动化测试和完整 HTTPS 安全配置。
