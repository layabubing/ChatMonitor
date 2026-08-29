# 云服务器部署全流程

目标：把系统部署到一台 **Ubuntu 22.04+ / Debian 12** 云服务器，通过 HTTPS 公网访问。

---

## 0. 前置准备

- 一台云服务器（腾讯云/阿里云轻量服务器即可，学生机更便宜），**Ubuntu 22.04** 系统；
- 一个域名（可选但推荐，HTTPS 需要；没有域名可先用 IP + HTTP）；
- 安全组/防火墙放行端口：`80`（HTTP）、`443`（HTTPS）。

---

## 1. 服务器环境

```bash
sudo apt update && sudo apt upgrade -y
# 安装 Python 3.11 与 Nginx
sudo apt install -y python3.11 python3.11-venv python3-pip nginx
python3.11 --version   # 确认 3.11+
```

## 2. 上传项目

```bash
# 本地打包（在项目根目录执行）
cd D:/chat-monitor
tar --exclude=.venv --exclude=data --exclude=reports --exclude=logs -czf chat-monitor.tar.gz .

# 上传到服务器 /opt/
scp chat-monitor.tar.gz root@YOUR_SERVER_IP:/opt/
ssh root@YOUR_SERVER_IP
cd /opt && tar -xzf chat-monitor.tar.gz && mv chat-monitor /opt/chat-monitor
```

## 3. 创建虚拟环境并安装依赖

```bash
cd /opt/chat-monitor
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
mkdir -p data/commands reports logs
sudo chown -R www-data:www-data /opt/chat-monitor   # 运行用户
```

## 4. 配置密钥（重要！）

```bash
cd /opt/chat-monitor/configs
cp app.env.example app.env
cp qq.env.example qq.env
cp dingtalk.env.example dingtalk.env
cp feishu.env.example feishu.env             # 可选：飞书
cp workwechat.env.example workwechat.env     # 可选：企业微信
nano app.env     # 修改: ADMIN_USERNAME / ADMIN_PASSWORD / JWT_SECRET / AI_API_KEY
nano qq.env      # 修改: QQ_APP_ID / QQ_APP_SECRET / QQ_GROUP_OPENIDS
nano dingtalk.env # 修改: DINGTALK_APP_KEY / APP_SECRET / DINGTALK_CHAT_IDS
nano feishu.env   # 修改: FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_CHAT_IDS（长连接，无需公网）
nano workwechat.env  # 修改: WORKWECHAT_CORP_ID / AGENT_ID / SECRET / TOKEN / AES_KEY / CHAT_IDS
```

> ⚠️ 所有密钥只存在服务器上，前端不暴露；`JWT_SECRET` 务必改为随机长字符串：
> `python3 -c "import secrets; print(secrets.token_hex(32))"`
>
> 📌 **企业微信回调**：`WORKWECHAT_TOKEN` / `WORKWECHAT_AES_KEY` 必须与企微后台「应用 → 接收消息」配置一致；
> 回调 URL 填 `https://你的域名/api/workwechat/callback`（见 §6，需 HTTPS 公网）。

## 5. 配置 systemd 服务

```bash
sudo cp deploy/chat-monitor-web.service deploy/chat-monitor-qq.service deploy/chat-monitor-dingtalk.service \
         deploy/chat-monitor-feishu.service deploy/chat-monitor-workwechat.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now chat-monitor-web chat-monitor-qq chat-monitor-dingtalk chat-monitor-feishu chat-monitor-workwechat
sudo systemctl status chat-monitor-web   # 查看状态
```

- 五个服务**互相独立**：一个崩溃/重启不影响其他；
- 未配置的平台 worker 会打印「无启用绑定」自动退出，不影响其余服务（如暂不用飞书可不启动 feishu 服务）；
- 查看日志：`sudo journalctl -u chat-monitor-qq -f`

## 6. Nginx + HTTPS

### 方式一：有域名（推荐，自动 HTTPS）

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo cp deploy/nginx.conf /etc/nginx/sites-available/chat-monitor
sudo nano /etc/nginx/sites-available/chat-monitor   # 把 your-domain.com 换成你的域名
sudo ln -s /etc/nginx/sites-available/chat-monitor /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
# 签发免费证书（自动改 nginx 配置为 HTTPS）
sudo certbot --nginx -d your-domain.com
```

> 📌 **企业微信回调公网可达**：证书生效后确认 `https://your-domain.com/api/workwechat/callback` 能被外网访问
> （浏览器打开应返回 403 JSON「企微回调验证失败」——403 表示路由可达、缺合法签名，属正常）；
> 然后在企微后台「接收消息」页配置该 URL 完成验证。

### 方式二：无域名（先用 IP + HTTP）

```bash
# 简化版 nginx 配置（删掉 443 段，80 直接反代）
sudo tee /etc/nginx/sites-available/chat-monitor <<'EOF'
server {
    listen 80;
    server_name _;
    location / { proxy_pass http://127.0.0.1:8001; proxy_set_header Host $host; }
}
EOF
sudo ln -s /etc/nginx/sites-available/chat-monitor /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

## 7. 验证

- 浏览器访问 `https://your-domain.com` → 应出现登录页；
- 默认账号 `admin` / 密码见 `configs/app.env`（**上线后立即修改**）；
- 登录后：总览页显示 QQ / 钉钉 / 飞书 / 企业微信 平台状态（`运行中` 表示 worker 正常）；
- 在「总览」点「生成报告」→「报告」页可预览/下载。

---

## 8. 日常运维

| 操作 | 命令 |
|------|------|
| 查看 web 日志 | `sudo journalctl -u chat-monitor-web -f` |
| 重启单个 worker | `sudo systemctl restart chat-monitor-qq`（或 dingtalk / feishu / workwechat） |
| 修改配置 | 改 `configs/*.env` 后 `sudo systemctl restart chat-monitor-web chat-monitor-qq chat-monitor-dingtalk chat-monitor-feishu chat-monitor-workwechat` |
| 备份数据 | `sudo tar -czf backup.tar.gz /opt/chat-monitor/data /opt/chat-monitor/configs /opt/chat-monitor/reports` |
| 更新代码 | 重新上传 + `sudo systemctl restart chat-monitor-web chat-monitor-qq chat-monitor-dingtalk chat-monitor-feishu chat-monitor-workwechat` |

---

## 9. 安全注意（上线清单）

**启动即加固（系统内置）**：
- `JWT_SECRET` 为默认值时，首次启动自动生成随机密钥（日志会提示，旧会话失效属正常）；
- 登录限流：同 IP+账号 5 分钟内失败 5 次自动锁定 10 分钟（`logs/web.log` 有审计记录）。

**上线必做清单**：

| # | 事项 | 操作 |
|---|------|------|
| 1 | 修改默认密码 | 登录后「设置 → 修改密码」，或改 `configs/app.env` 的 `ADMIN_PASSWORD` 后重启 |
| 2 | 确认 JWT_SECRET 已随机化 | `grep JWT_SECRET /opt/chat-monitor/configs/app.env`（应是一长串随机 hex） |
| 3 | 公网注册开关 | 编辑 `configs/app.env`：`REGISTER_OPEN=false` 关闭注册，或设置 `REGISTER_INVITE_CODE=xxxx` 启用邀请码 |
| 4 | Cookie 安全标志 | HTTPS 部署后设 `COOKIE_SECURE=true` 并重启 web |
| 5 | 防火墙 | 只开 `80/443`（`sudo ufw allow 80,443/tcp`），FastAPI 只监听 `127.0.0.1` |
| 6 | 密钥保护 | QQ/钉钉/飞书/企微/AI Key 只存服务器，勿提交公开仓库；`configs/` 权限收紧 `chmod 600` |
| 7 | 定期备份 | `sudo tar -czf backup.tar.gz /opt/chat-monitor/data /opt/chat-monitor/configs /opt/chat-monitor/reports` |
| 8 | 监控日志 | 关注 `logs/web.log`（登录失败/锁定/管理操作）与 `sudo journalctl -u chat-monitor-web -f` |
