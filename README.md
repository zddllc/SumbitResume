# Resume Studio

Vue 3 / Vite / TypeScript 前端 + Python API 后端，支持 Windows 开发和 Linux 图形桌面运行。

目标部署：**113 同机运行 Nginx、Python API、可见 Chrome**；MongoDB 仍使用 `10.0.0.44` 上的 `resume` 数据库。当前仍为单用户应用，不自动提交申请。

## 本地开发

### 后端

使用已有的 Python 3.11 环境：

```powershell
$python = 'C:\Users\chenli2\AppData\Local\anaconda3\envs\py311\python.exe'
& $python -m pip install -r .\requirements.txt
& $python .\run.py
```

复制 [.env.example](.env.example) 为 `.env` 可配置数据库、路径、字体、主机和 Cookie。已有 `.instance/secrets.json` 必须保留，不能用新生成的密钥替换。

后端由 Waitress 单进程、多请求线程提供服务，浏览器 / LLM 后台任务仍串行执行。默认 API 健康检查：

**http://127.0.0.1:8000/resume/api/health**

后端不再提供旧的 Jinja 页面或静态 JS；访问界面请使用前端地址。

### 前端

需要 **Node.js 22.22.2+**（推荐受支持的 Node 22 LTS）。系统中旧的 Node 18 不适合此构建工具链。

```powershell
Set-Location .\frontend
npm ci
npm run dev
```

访问 **http://127.0.0.1:5173/resume/**。开发服务器将同域的 `/resume/api/` 转发到本机后端，不需要 CORS。

```powershell
npm test
npm run build
```

构建结果为 [frontend/dist](frontend/dist)。生产环境只需要部署这个目录的内容，不需要在 Nginx 上运行 Node。

[frontend/.env.example](frontend/.env.example) 配置构建前缀 `VITE_BASE_PATH=/resume/` 和开发代理目标 `API_PROXY_TARGET`。后端 `APP_BASE_PATH=/resume` 必须匹配。若使用其他路径，两边及 Nginx 一起修改。

## 113 上的 Linux 部署

详细步骤见 [部署说明](deploy/README.md)，配置文件：

- [Nginx 路径配置](deploy/nginx-resume.conf)：前端 SPA 刷新回退、静态资源缓存、API 反代和上传限制；
- [后端环境示例](deploy/resume.env.example)：本机监听、可信域名、持久化目录和 Linux 字体；
- [用户级 systemd 服务](deploy/resume-api.service)：与桌面会话关联，继承图形环境；
- [真实图形 Chrome 检查](deploy/linux-browser-smoke.py)：仅访问合成页面，不登录 LinkedIn。

Nginx 保留完整 `/resume/api/` URI 转发，后端自身挂载在 `/resume`，所以登录 Cookie、CSRF、PDF 查看 / 下载和其他 API 统一支持前缀。

**Chrome 打开在后端机器的桌面，不在访问网页的客户端。** 用户通过 113 的本地 / 远程桌面完成 LinkedIn 登录、验证码和安全检查。不需要额外的虚拟显示或 noVNC，除非以后希望把桌面直接嵌入产品网页。

## 使用流程

1. 首次创建唯一账号，之后关闭注册。密码至少 8 个字符，scrypt 哈希保存；连续 5 次失败限制 10 分钟。
2. **模型设置**：支持 DeepSeek、Azure OpenAI、Azure DeepSeek 和 OpenAI 兼容服务。API key 加密保存且不回显；保存配置不产生模型费用。
3. **简历底板**：上传 DOCX / PDF，授权后由模型解析为独立的待比较结果，选择保留的内容并应用到草稿，再人工修改、确认。已有底板再次进入自动加载，不必重复上传或调用模型。
4. **申请信息 / 外站账号**：自愿填写申请事实和站点凭据。敏感答案、用户名和密码加密存储，不发送模型、不自动推断。
5. **打开受控 Chrome**，在后端桌面手动登录 LinkedIn。
6. **遍历推荐职位**：设置单次上限 1–100，授权后读取职位描述与申请入口，按底板生成结构化职位简历。
7. 在职位详情编辑这份职位简历，工作要点支持增删、修改和上移 / 下移。越靠前表示越重要、越新，不据此推断具体日期。
8. 在职位详情选择 **投递 PDF 模板**（默认“经典灰条 · 044”），再 **确认并生成 PDF**，查看 / 下载实际已保存文件，之后从已保存申请链接出发。也可以直接使用数据库中的职位描述生成或重试，不再访问 LinkedIn。

底板与职位简历使用同一 Vue 编辑组件，但数据副本互相隔离；修改职位简历不覆盖全局底板。修改后必须确认保存，未确认编辑不进入投递文件。

教育、论文、项目、证书和语言在编辑区、上传对比区和页面预览中默认收起，标题显示条目数量，点击标题可展开 / 收起；编辑和对比中的工作经历默认展开，也可手动收起。折叠只改变显示，不丢弃修改、对比选择或数据，也不影响生成的 PDF / Word 内容。

### Jobs 底板变化与 PDF 状态

- 职位简历保留模型生成时的底板快照，不自动用最新底板覆盖已编辑的职位内容。打开详情、窗口重新获得焦点及详情可见时每 10 秒检查最新**已确认**底板；内容变化会提示重新使用模型生成，未确认草稿 / 上传结果不会参与生成。
- **用最新底板重新生成内容（模型）**读取最新已确认底板，沿用已有缓存和审计。任务完成后自动加载该任务实际返回的版本，包括不在历史列表首位的缓存版本；不会凭创建时间猜测结果。生成期间锁定编辑，失败保留原内容，覆盖未保存编辑前需确认。
- **仅补齐空白（不调用模型）**会重新读取已确认底板，补空联系字段、简介、空章节，以及唯一匹配经历 / 论文等的缺失字段和空列表；已有非空字段、工作要点及顺序保持不变。非空章节不擅自追加无法匹配的条目，避免恢复用户有意删掉的经历 / 技能；需要全量更新时使用模型生成。补齐只修改当前职位草稿，需重新核对并生成 PDF，不更改原始生成快照，也不把旧版本标成已由新底板生成。
- PDF 与模型任务分别显示状态。点击确认后显示“正在制作 PDF”的不定进度（不虚报百分比）；排版、校验、存储完成且重新核验最新文件就绪后显示“PDF 已完成，可以下载”。保存成功但状态刷新失败时不冒充完成，需加载最新结果再下载。
- **同一模板、同一内容也可以反复重新生成 PDF**，不调用模型。成功后按钮变为“重新生成 PDF”，保持内容未变时无需切换模板；修改内容 / 模板后重新勾选事实确认。失败显示原因、保留编辑并提供重试；旧文件不冒充本次新文件。查看 / 下载链接使用当前文件 ID 区分，避免浏览器缓存旧 PDF；职位列表也按实际存储的匹配文件判断可下载状态。

### 重新上传与内容选择

上传解析不会覆盖现有草稿或已确认底板。新结果单独保存，刷新或重新登录后仍可继续比较；同一时间只保留一份待处理上传，需要先应用或放弃，才能再次上传。

- 姓名、电话等相同值不提示；个人简介作为整段比较，不拆句自动改写。只忽略空白排版差异，不猜测电话号码等字段的等价格式。
- 工作经历、教育、论文、项目、证书和语言先确定对应条目，再**逐字段选择**，例如保留手工修改的职位名称，只采用新的结束日期。相同字段不重复提示，有差异时默认保留原有非空值。作者名单作为有序字段整体选择，不拼接或重排署名。
- 工作要点、项目要点和补充信息**逐条勾选**。旧要点默认保留，已有条目里的新要点默认不选；可取消某条旧要点并勾选新要点，而不替换整段工作经历。不按行号或相似度猜测要点对应关系；两份都有的要点只展示一次。保留旧要点的相对顺序，新选要点按新文件顺序追加，应用后可再调整顺序。
- 全新条目和技能默认选中，可逐条取消。只在旧内容里存在的字段和条目继续保留，上传缺失值不自动清空旧内容；原来留空的普通字段（如日期、DOI）默认选用新值，已有条目的新要点仍需手动勾选。
- 按公司与职位或开始时间、院校与学位或开始时间、论文 DOI 或标题等确定唯一对应关系，支持在同一条目里比较职位、日期等字段的变化；关系不明确时按新增展示，不模糊猜测覆盖。应用后仍可单独编辑或删除不需要的条目。
- **应用所选内容到草稿**会保存选择结果，但仍不改变已确认底板；**放弃本次上传**保留原内容。之后通过原编辑器逐条修改或删除，再确认保存底板。
- 应用 / 放弃同时校验底板编辑令牌和上传结果 ID；另一页面已修改数据时拒绝过期操作，不覆盖新版本。比较过程本身不调用模型。

## 结构化事实与模型约束

[models.py](resume_app/models.py) 只允许通用简历字段：联系信息、简介、技能、工作经历、教育经历、论文、项目、证书和语言。

论文包括标题、按原文顺序列出的作者、期刊 / 会议、时间、DOI、链接及其他引文备注（卷期、页码、预印本编号等）。解析 prompt 明确要求识别期刊论文、会议论文和预印本，不把论文混入项目，不补造作者身份、发表状态、日期或 DOI，也不联网补全。论文在底板和职位简历中都可增删编辑，两种 PDF 模板及 Word 导出均包含论文。

原有无论文的底板和职位简历在 API 中补为空列表，无需数据库迁移，不因此重跑模型或使旧已确认 PDF 失效。之前解析时没有保存下来的论文，需要重新上传原简历解析，或手动添加。

模型提供简介、已有技能排序 / 选择，以及引用原要点的改写计划。程序保留姓名、公司、职位、日期、教育和论文等事实字段，拒绝新增技能和非法引用。选中的工作要点仍按底板相对顺序排列；论文事实和顺序保留，由用户在职位简历确认前选择编辑。文字改写仍可能出错，必须人工确认。

模型不接收外站账密、敏感问卷答案或申请 URL 的跟踪 / 会话参数。[独立 LLM 工具](utils/llm_client.py) 本身没有数据库、缓存、模型路由或自动供应商切换。

## 数据、复用与 PDF

MongoDB 集合包括 `users`、`resumes`、`llm_settings`、`credentials`、`jobs`、`tailored_resumes`、`tasks`、`metadata`、`llm_calls`；PDF 使用 `resume_pdfs.files` / `resume_pdfs.chunks`，大型审计正文使用 `llm_audit_payloads.files` / `llm_audit_payloads.chunks`。

- 相同用户、职位内容、底板、模型配置与提示词版本复用结果，不再次调用模型。更新申请链接不会破坏简历缓存。
- 新上传解析结果不覆盖现有草稿或已确认底板，需用户对比并应用选择后才更新草稿。任务使用启动时的已确认底板和模型配置快照。
- 推荐列表左侧点击后校验右侧职位 ID，避免拿到上一职位描述。外站入口采集会短暂打开独立标签页，不关闭用户已有页面、不填写表单。
- 对外站 Apply，保存真实落地页及可识别的 Apply now 链接。Easy Apply 标为 LinkedIn 站内申请，不伪造外站链接。
- 用户确认职位简历后按所选模板生成可选择文字的 PDF，实际字节存入 GridFS，并绑定用户、简历版本、内容指纹、模板 ID / 指纹和 SHA-256。
- 下载返回同一份已确认文件，不重新渲染。修改后再次确认生成新 PDF；冲突、缺字、排版或存储失败不会冒充确认成功。
- 后续投递应通过 [read_confirmed_pdf](resume_app/pdf/storage.py) 读取匹配当前确认内容的文件。目前不自动登录外站、上传或提交申请。
- 任务可请求取消；当前浏览器 / API 操作完成后才生效。重启会把未完成任务标为中断，已保存结果可复用。

原 Word 导出 API 保留用于兼容，并使用对应已选模板；界面和后续投递主流程使用 PDF。旧的已确认 PDF 仍可下载，不自动改版或重新渲染。

### 模型 request / response 审计

上传解析和职位改写都会保存独立的 `llm_calls` 记录，关联用户、任务、模型、文件 / 职位、缓存标识和时间。`attempts` 按顺序保存实际 HTTP 交换：发送前记录 request 的方法、地址及完整请求体，收到后在 SDK / JSON / 业务校验前记录 response 的状态码、请求 ID 和完整响应体。请求体包含 system / user messages、简历原文或底板 / JD、Schema 和实际模型参数；响应体保留服务端返回的 usage、reasoning 和其他字段（如服务端提供），不只保存最终文本。HTTP 错误、截断输出及非法 JSON 同样保留；网络中断未取得完整响应时，不伪造响应。

- **严格模式**：审计无法写入时停止，不静默放行。请求审计失败不发送请求；响应或最终审计失败不保存新业务结果，批量职位处理也停止。请求可能已经产生模型费用，不自动重试或切换供应商。HTTP 重定向分别记录，最多 21 次交换，与当前 20 次重定向上限及零 SDK 自动重试一致。
- 不保存认证头、Cookie 或 API key；URL 用户信息和敏感查询值会脱敏，正文中出现当前 API key 的字面值也会脱敏，并标记 `redacted`。其他正文不截断。这里保存的是 HTTP 解码后的正文，不是 TLS 报文。
- UTF-8 正文不超过 256 KiB 时保存在 `body.text`；更大或非 UTF-8 正文原样写入审计 GridFS。统一保存字节数及 SHA-256，避免 MongoDB 单文档 16 MiB 限制。读取校验用户归属、长度及哈希；缺失 / 损坏明确报错。
- `status=response_validated` 只代表模型输出通过程序校验，不代表用户已审核或业务记录已提交；`failed` 附错误类型和阶段，重启遗留的未完成调用标记 `interrupted`。有完整响应时可继续查看原文。
- 应用 / 放弃上传、人工修改简历不会删除审计；命中旧业务缓存不新增模型调用记录。新导入结果和职位简历通过 `llm_call_id` 关联，应用导入后底板保留 `last_import_call_id`。旧调用无法补录，只有升级后实际发生的调用才有完整记录。
- 审计正文包含简历及职位内容，存于 MongoDB，**不自动过期**，需要与业务数据一样限制访问并备份；当前没有新增审核网页或公开审计 API。

后续审核可直接查询 MongoDB，使用 [read_audit_body](resume_app/llm_audit.py) 统一读取内联 / GridFS 正文，例如：

```python
import json
from pymongo import MongoClient
from resume_app.llm_audit import read_audit_body

db = MongoClient("mongodb://10.0.0.44:27017").resume
call = db.llm_calls.find_one({"user_id": "local"}, sort=[("created_at", -1)])
if call is not None and call["attempts"]:
    request = json.loads(read_audit_body(db, "local", call["_id"], "request"))
    # HTTP 错误响应不一定是 JSON，可先按原始 bytes 查看。
    response = read_audit_body(db, "local", call["_id"], "response")
```

### 模板类与 PDF 代码组织

每个设计对应一个模板类，由类定义页面、字体、章节顺序、字段映射、灰条 / 分栏和续页规则。运行时按模板 ID 选择类，直接用 ReportLab 生成 PDF，**不读取参考 Word，不生成中间 DOCX，也不启动 Word / LibreOffice**。不需要安装 Office 或配置 `OFFICE_CONVERTER` / `LIBREOFFICE_PATH`，旧环境文件中这些配置已不使用。

PDF 相关代码统一放在 [resume_app/pdf](resume_app/pdf)：

```text
resume_app/pdf/
  __init__.py              # 模板注册、列表与导出入口
  rendering.py             # 字体、文字校验、段落与输出完整性检查
  storage.py               # 已确认文件的 GridFS 存储与读取
  templates/
    base.py                # 共同渲染流程、模板版本与布局接口
    classic_044.py         # 044 的排版规则、字段映射和兼容 Word 导出
    serif_000.py           # 000 的衬线正文、下划线章节和紧凑论文排版
    simple.py              # 原有简洁单栏版式
  references/
    044.docx               # 仅供开发时对照，不参与运行
    000.docx               # 本地提供版式的占位示例，不包含真实个人简历
```

默认 [Classic044Template](resume_app/pdf/templates/classic_044.py) 保留 044 的衬线字体、A4 页面、居中姓名、灰色章节条和日期 / 经历分栏，正文及长要点可跨页。缺少内容的章节不输出；所有已确认的联系信息、技能、经历、教育、项目、证书和语言均参与生成，不调用模型补写事实。[参考 Word](resume_app/pdf/references/044.docx) 保存在仓库中，方便以后修改模板类时对照；只修改参考文件不会改变实际 PDF。

新增 **衬线履历 · 000**（`serif-000`），由 [Serif000Template](resume_app/pdf/templates/serif_000.py) 生成。参考本地提供的 Word：A4，正文左右 54 pt、上下 72 pt 留白；Garamond 11.5 pt 正文、14 pt 姓名、15 pt Times 下划线章节标题和 10 pt 论文正文。顶部使用姓名 / 邮箱、链接 / 联系信息及细横线，职位行使用 12 pt Calibri 斜体（Linux 优先 Liberation Sans 斜体），不使用 Garamond 斜体。工作经历左侧为加粗公司与地点，右侧为日期，两者在同一行顶部对齐；过长字段各自在列内换行，不挤出页边距。

000 的工作 / 项目要点使用与原稿 Wingdings 箭头相近的矢量箭头，21 pt 悬挂缩进；PDF 不依赖 Wingdings 字体，长要点续页不重复绘制箭头，Word 导出使用原稿的 Wingdings `F0D8` 项目符号。所有结构化章节及论文信息均保留；没有额外加入目标职位标签。当前版式版本为 `reportlab-000-v2`，旧已确认 PDF 不自动改写，选择同一 000 模板后点击“重新生成 PDF”即可得到修正版，不调用模型。

[000.docx](resume_app/pdf/references/000.docx) 是采用该版式重新生成的占位示例，仅含虚构资料，不复制真实简历文字、联系方式、链接或文档元数据，也不修改原始文件。原稿的负右缩进和手工空格对齐没有照搬，改用固定留白与可换行布局，避免动态内容越界；不同系统使用可用的衬线字体 / Unicode 后备字体。000 的 PDF 和兼容 Word 均由代码直接生成，不在运行时读取参考文件或依赖 Office。现有 044、简洁单栏、默认选择及已保存 PDF 均保持不变。

- 前端从 `GET /api/resume-templates` 获取模板列表和默认项；预览图目前为 `null`，显示占位区域。选择后的 `template_id` 与最新编辑的 `profile` 一起提交确认接口。
- 切换模板会清除前端核对勾选并隐藏旧 PDF 入口，需要重新确认生成；失败时不覆盖之前的内容和文件，也不会偷偷退回旧版式。
- `PDF_FONT_PATH` 是所有模板的 Unicode 字体 / 后备字体配置。044 / 000 的西文正文优先使用 Windows Garamond / Times，Linux 使用 Liberation Serif；000 的职位行单独使用 Calibri / Arial 斜体，Linux 使用 Liberation Sans / DejaVu Sans Oblique，无这些字体时使用 Unicode 后备字体。中文按字符使用可嵌入的 Unicode 后备字体，缺字明确报错，不以其他版式掩盖。
- 输出会检查 PDF 文字完整性。确认保存、内容指纹、模板指纹与文件 SHA-256 的逻辑共用；旧的 Word 转换产物和无模板元数据的历史文件仍按原字节下载，不强制重新生成。
- 兼容的 Word 下载也由模板类用代码创建，保留所选模板的主要版式，不读取参考文件；它不是生成 PDF 的中间步骤。

新增模板：继承 [ResumeTemplate](resume_app/pdf/templates/base.py)，实现该设计的 `story()`，声明稳定的 `id`、名称、版本和版面参数，再将实例加入 [TEMPLATES](resume_app/pdf/__init__.py)。需要特殊 Word 导出版式时重写 `render_docx()`，否则沿用通用 Word 导出。新模板不需要修改确认、存储或下载流程。修改影响输出的模板代码时应递增 `version`；保存的 `template_hash` 来自模板 ID / 实现版本，而不是参考 DOCX 的文件哈希。

运行模板检查（仅用合成简历，不访问生产数据库或模型，无需 Office）：

```powershell
$env:PYTHONPATH = "$PWD\tests"
& $python -m unittest test_resume_templates -v
```

## 迁移与隐私

- **保留并安全备份原加密密钥**。数据库已有加密信息而新机器缺少密钥时，后端拒绝启动，不会生成新密钥掩盖迁移错误。
- Linux 上实例目录 / 密钥文件权限限制为 `700` / `600`。浏览器配置应仅归桌面用户所有。
- Windows 的 Chrome 登录目录不直接迁到 Linux，Linux 上重新手动登录并持久保存。
- 账号 Cookie 使用独立名称和部署前缀 Path，HttpOnly / SameSite / CSRF 校验；HTTPS 部署开启 Secure。只信任配置中的域名和单层本机反代。
- Nginx 仅服务构建产物，不服务后端仓库、密钥、浏览器配置或原始上传文件。
- 简历和已确认 PDF 含个人信息。限制 MongoDB 访问权限，并按需要配置鉴权、TLS 和备份。

## 验证

```powershell
& $python -m pip install -r .\requirements-dev.txt
& $python -m unittest discover -s .\tests -q
& $python -m pyright --pythonpath $python
Set-Location .\frontend
npm test
npm run build
```

[CI](.github/workflows/checks.yml) 配置 Windows / Ubuntu 后端测试、Vue 构建与 Linux 图形 Chrome 合成页面检查。测试不访问真实 LinkedIn、不调用收费模型、不写入生产测试账号。

本机 VS Code 的 Conda 解释器配置用于 Windows 开发；Linux 部署使用独立 Python 环境，不依赖工作区中的 Windows 路径。

## 已知边界

仅单用户、单后端实例。支持 DOCX 与有文字层的 PDF（10 MB、PDF 30 页、文字 80,000 字符），不支持旧版 DOC、加密 PDF、扫描件 OCR。LinkedIn DOM 和申请链接可能变化；需要实际账号和具体网站的后续联调，不绕过安全验证。
