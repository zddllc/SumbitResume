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
3. **简历底板**：上传 DOCX / PDF，授权后由模型解析为结构化草稿，人工修改并确认。已有底板再次进入自动加载，不必重复上传或调用模型。
4. **申请信息 / 外站账号**：自愿填写申请事实和站点凭据。敏感答案、用户名和密码加密存储，不发送模型、不自动推断。
5. **打开受控 Chrome**，在后端桌面手动登录 LinkedIn。
6. **遍历推荐职位**：设置单次上限 1–100，授权后读取职位描述与申请入口，按底板生成结构化职位简历。
7. 在职位详情编辑这份职位简历，工作要点支持增删、修改和上移 / 下移。越靠前表示越重要、越新，不据此推断具体日期。
8. **确认并生成 PDF**，查看 / 下载实际已保存文件，之后从已保存申请链接出发。也可以直接使用数据库中的职位描述生成或重试，不再访问 LinkedIn。

底板与职位简历使用同一 Vue 编辑组件，但数据副本互相隔离；修改职位简历不覆盖全局底板。修改后必须确认保存，未确认编辑不进入投递文件。

## 结构化事实与模型约束

[models.py](resume_app/models.py) 只允许通用简历字段：联系信息、简介、技能、工作经历、教育经历、项目、证书和语言。

模型提供简介、已有技能排序 / 选择，以及引用原要点的改写计划。程序保留姓名、公司、职位、日期和教育等事实字段，拒绝新增技能和非法引用。选中的工作要点仍按底板相对顺序排列。文字改写仍可能出错，必须人工确认。

模型不接收外站账密、敏感问卷答案或申请 URL 的跟踪 / 会话参数。[独立 LLM 工具](utils/llm_client.py) 本身没有数据库、缓存、模型路由或自动供应商切换。

## 数据、复用与 PDF

MongoDB 集合包括 `users`、`resumes`、`llm_settings`、`credentials`、`jobs`、`tailored_resumes`、`tasks`、`metadata`；PDF 使用 `resume_pdfs.files` / `resume_pdfs.chunks`。

- 相同用户、职位内容、底板、模型配置与提示词版本复用结果，不再次调用模型。更新申请链接不会破坏简历缓存。
- 新上传草稿不覆盖旧的已确认底板。任务使用启动时的底板和模型配置快照。
- 推荐列表左侧点击后校验右侧职位 ID，避免拿到上一职位描述。外站入口采集会短暂打开独立标签页，不关闭用户已有页面、不填写表单。
- 对外站 Apply，保存真实落地页及可识别的 Apply now 链接。Easy Apply 标为 LinkedIn 站内申请，不伪造外站链接。
- 用户确认职位简历后生成单栏、可选择文字、嵌入字体的 PDF，实际字节存入 GridFS，并绑定用户、简历版本、内容指纹和 SHA-256。
- 下载返回同一份已确认文件，不重新渲染。修改后再次确认生成新 PDF；冲突、缺字、排版或存储失败不会冒充确认成功。
- 后续投递应通过 [read_confirmed_pdf](resume_app/pdf_storage.py) 读取匹配当前确认内容的文件。目前不自动登录外站、上传或提交申请。
- 任务可请求取消；当前浏览器 / API 操作完成后才生效。重启会把未完成任务标为中断，已保存结果可复用。

原 Word 导出 API 保留用于兼容，界面和后续投递主流程使用 PDF。

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
