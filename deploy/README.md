# 113 Linux 图形桌面部署

这些是部署步骤与示例配置；不会自动修改 113。以下以 Ubuntu / Debian 的普通桌面用户为例，用户、目录、域名和 Python 安装方式需按实际环境调整。

## 1. 先保护现有数据

停止原后端，备份 MongoDB `resume`，并安全备份原 `.instance/secrets.json`。

**先把原密钥文件放到 Linux 的 `INSTANCE_DIR/secrets.json`，再启动后端。** 不要在聊天、前端目录或 Git 中传递密钥。缺少原密钥时已有 API key / 外站账密无法解密。

Chrome 的 Windows 配置不要直接复制到 Linux；Linux 桌面中重新登录 LinkedIn。

## 2. Python、Chrome 和字体

使用 Python 3.11 环境（若系统没有，先通过受信的安装方式准备，不替换系统 Python）。示例代码位置为 `~/apps/SumbitResume`：

```bash
cd ~/apps/SumbitResume
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
sudo apt-get update
sudo apt-get install -y nginx fonts-wqy-zenhei fonts-liberation
```

安装 Google Chrome，或发行版 Chromium 与匹配的 ChromeDriver。自定义 / ARM 环境建议明确设置 `CHROME_PATH`、`CHROMEDRIVER_PATH`。不要为了 root 运行而添加 `--no-sandbox`；使用登录桌面的普通用户。

默认投递 PDF 使用代码中的 044 模板类直接生成，不需要安装 Word / LibreOffice，也不读取仓库中的参考 DOCX。`PDF_FONT_PATH` 为所有模板配置 Unicode 后备字体，044 的西文使用 Liberation Serif。Windows 默认优先使用 Garamond / Times；需要完全一致的字体效果时，应依法安装并在模板字体选择中配置同一套字体。旧的 `OFFICE_CONVERTER` / `LIBREOFFICE_PATH` 配置已不使用。

从 **113 的桌面终端** 执行：

```bash
.venv/bin/python deploy/linux-browser-smoke.py
```

它只打开合成页面，验证可见 Chrome 能启动并响应。失败时先处理图形会话、驱动或沙箱依赖，不要跳过该检查。

## 3. 私有数据与环境文件

```bash
install -d -m 700 ~/.config/resume
install -d -m 700 ~/.local/share/resume/instance
install -d -m 700 ~/.local/share/resume/browser
cp deploy/resume.env.example ~/.config/resume/resume.env
chmod 600 ~/.config/resume/resume.env
```

安全迁入原 `secrets.json` 并确保归桌面用户所有，文件权限 `600`。

编辑环境文件中的：

- `INSTANCE_DIR`、`BROWSER_PROFILE_ROOT`：改为实际用户的绝对路径；
- `TRUSTED_HOSTS`：实际访问域名 / IP，不能填 `*`；
- `COOKIE_SECURE=true`：用于 HTTPS；仅局域网 HTTP 临时测试时设为 `false`；
- MongoDB 鉴权 / TLS、Chrome 和字体路径：按实际环境配置；
- `APP_BASE_PATH=/resume`：与前端和 Nginx 保持一致。

环境文件采用 dotenv 的 `KEY=value`，不要依赖 shell 的 `$HOME` 展开。可以使用示例中的绝对路径。后端通过 `RESUME_ENV_FILE` 读取它，不要把包含数据库密码的文件当作 shell 脚本执行。

## 4. 在桌面用户会话中启动 API

建议先从桌面终端启动，显式加载受保护的环境文件：

```bash
cd ~/apps/SumbitResume
RESUME_ENV_FILE="$HOME/.config/resume/resume.env" .venv/bin/python run.py
```

API 默认仅监听 `127.0.0.1:8000`。可检查：

```bash
curl http://127.0.0.1:8000/resume/api/health
```

正式使用用户级 systemd：

```bash
install -d ~/.config/systemd/user
cp deploy/resume-api.service ~/.config/systemd/user/
systemctl --user import-environment DISPLAY XAUTHORITY WAYLAND_DISPLAY DBUS_SESSION_BUS_ADDRESS
systemctl --user daemon-reload
systemctl --user enable --now resume-api.service
journalctl --user -u resume-api.service -f
```

导入的图形变量必须来自当前有效的桌面会话。若某个变量没有设置，不要虚构它的值；X11 常用 `DISPLAY` / `XAUTHORITY`，Wayland 使用其有效会话环境。不要用 root 系统服务代替桌面用户服务。

服务与桌面会话关联，退出桌面会停止服务。不要配置多 worker 或多个后端实例，不要让两份 Chrome 同时使用一个配置目录。

## 5. 构建并部署 Vue

构建机使用 Node.js 22.22.2+；113 如果只服务静态文件，则不必安装 Node。

```bash
cd frontend
npm ci
npm test
npm run build
```

将 `frontend/dist` 的**内容**部署到专用静态目录 `/srv/resume`，不要部署整个后端仓库。示例：

```bash
sudo install -d -m 755 /srv/resume
sudo rsync -r --chmod=D755,F644 frontend/dist/ /srv/resume/
```

此命令从仓库根目录执行。现有旧哈希资源可以保留，避免已打开页面失效；需要清理时仅清理确认归本应用所有的构建文件。

## 6. Nginx

把 [nginx-resume.conf](nginx-resume.conf) 中的 location 配置包含在现有域名的 server 块中。外层 http 块应已经加载标准 `mime.types`，HTTPS 证书由现有站点配置提供。

API 必须保留完整 URI：

```nginx
location ^~ /resume/api/ {
    proxy_pass http://127.0.0.1:8000;
    # 其余请求头、限制等配置见完整示例。
}
```

**不要改为会截掉 `/resume` 的反代写法。** 后端在 `/resume` 挂载，负责生成带前缀的 Cookie Path 和 PDF URL。

```bash
sudo nginx -t
sudo systemctl reload nginx
```

访问 `https://你的域名/resume/`。第一次进入若数据库已有账号，直接使用原账号登录；不是重新注册。

检查页面刷新、上传、后台任务、职位详情、PDF 预览 / 下载和退出登录。前端点击“打开受控 Chrome”后，在 113 的桌面窗口完成 LinkedIn 登录。

## 7. 换一个部署路径

例如 `/tools/resume/`，需要同时修改：

1. 后端 `APP_BASE_PATH=/tools/resume`；
2. 构建环境 `VITE_BASE_PATH=/tools/resume/` 后重新构建；
3. Nginx 的 location、回退 index 和静态文件对应目录。

不能只改 Nginx 路径却保留旧构建前缀。不要把 API 的 404 回退成 SPA HTML。

## 常见问题

- **403 校验过期**：刷新页面重新获取会话 / CSRF；检查 Cookie Secure、Path、域名及反代是否正确。
- **400 Host 不可信**：配置实际 `TRUSTED_HOSTS`，只信任本机 Nginx 的一层代理头。
- **Linux 没有 DISPLAY**：后端不在桌面会话中；先从桌面终端启动，再正确导入用户服务环境。
- **缺少原密钥而拒绝启动**：恢复原密钥，不要删除数据库中的加密信息来规避检查。
- **PDF 字体缺字**：安装可嵌入的 TrueType 中文字体并配置 `PDF_FONT_PATH`；不要把不兼容的 CFF 字体当作 TTF 使用。
- **PDF 排版失败 / 文字缺失**：检查中英文字体与 `PDF_FONT_PATH`；不要以旧版式静默替代。可运行 `PYTHONPATH=tests .venv/bin/python -m unittest test_resume_templates -v` 验证模板类、多页中英文及已确认文件的读写，无需 Office。
- **ChromeDriver 不匹配**：安装匹配驱动或允许 Selenium Manager 下载；保持普通用户和沙箱。
- **搜索 / 推荐 UI 变化**：选择器在 [linkedin.py](../resume_app/linkedin.py)，安全验证仍需手工完成。

禁止将 ChromeDriver、DevTools 或桌面端口直接暴露到公网。Nginx 只代理本应用 API，不代理浏览器调试端口。
