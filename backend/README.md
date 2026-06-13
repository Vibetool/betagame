# 后端部署 (宝塔 + PHP 8 + MySQL)

`backend/` 里 4 个 PHP + 1 张 SQL,放到任意装了宝塔的服务器上即可承担账户和云端存档。

## 文件
- `schema.sql` — 3 张表 (users / sessions / user_save) 的建表语句
- `db.php` — 数据库连接 + CORS + 当前用户工具,在头部修改连接信息
- `auth.php` — `?action=signup | login | logout | me`
- `save.php` — GET 读存档 / `?type=stats|snapshot|best` POST 写
- `leaderboard.php` — 公开 Top N 排行榜 (匿名可读)

## 部署步骤 (~10 分钟)

### 1) 宝塔: 新建站点
- 推荐独立子域名,如 `api.your-domain.com`
- 网站 -> 添加站点 -> 域名填子域名 -> PHP 选 **8.x** -> 创建
- (可选) 顺手在创建对话框里勾上"创建数据库",方便下一步用

### 2) 宝塔: 创建数据库 + 导入表
- 数据库 -> 添加数据库 -> 数据库名 `metro_game`,用户名比如 `metro_user`,生成密码
- 点进该数据库 -> **导入** -> 选择本目录的 `schema.sql` -> 确定
- (或在 phpMyAdmin / Adminer 里粘贴 schema.sql 执行也行)

### 3) 上传 PHP 文件
- 文件 -> 进入站点目录 (默认 `/www/wwwroot/api.your-domain.com/`)
- 把 4 个 PHP 文件上传到根目录
- 删掉宝塔默认生成的 `index.html` / `404.html` (不影响)

### 4) 改 `db.php` 头部 4 行
```php
const DB_HOST = '127.0.0.1';
const DB_NAME = 'metro_game';
const DB_USER = 'metro_user';
const DB_PASS = '你刚才生成的密码';
```
同时检查 `CORS_ALLOWED_ORIGINS` 数组里有你的前端域名 (默认已包含 `https://vibetool.github.io`):
```php
const CORS_ALLOWED_ORIGINS = [
    'https://vibetool.github.io',
    // ...
];
```

### 5) 申请 SSL (必须)
GitHub Pages 是 HTTPS,浏览器**禁止**从 HTTPS 页面 fetch 到 HTTP 后端 (mixed content)。

**申请前先做完这 3 项**, 否则 Let's Encrypt 会反复"验证失败":
1. 云厂商安全组 (阿里云/腾讯云/华为云控制台)放行 **80 + 443** 入站
2. 宝塔 -> 安全 -> 放行 **80 + 443**
3. DNS A 记录已生效 — 命令行 `ping api.your-domain.com` 应该返回你的服务器 IP。第一次 DNS 生效一般 5~30 分钟

确认后:宝塔 -> 站点 -> 设置 -> SSL -> **Let's Encrypt**,域名打勾,申请 -> 强制 HTTPS。

> **注意**: 拿到证书后 80 端口**也不能关**!Let's Encrypt 每 60 天自动续签也走 80,关了下次续签必失败。

> 没有域名? 自签证书或 IP+http 都不行 — 浏览器会拒绝。最便宜的国内域名 1 块/年,namesilo 国外域名约 60 块/年。或者直接把游戏 HTML 也搬到自己服务器,前后端同域,就不用 CORS 也不用 HTTPS 强制了。

### 6) 自检
**先打** `https://api.your-domain.com/health.php` 这个一站式自检端点, 浏览器或 curl 都行。响应里:
- `"ok": true` + `"db": "connected"` + `"tables": "ok"` -> 后端基础设施全通
- `"db": "error: ..."` -> 看到具体 PDO 错误, 改 db.php 里的 DB 配置
- `"tables": {"missing": [...]}` -> schema.sql 没跑完, 回第 2 步重新导入
- `"origin"` 字段 -> 应该是 `null` (curl) 或你的前端域名 (浏览器). 如果是其他, 改 `CORS_ALLOWED_ORIGINS` 加白名单

确认 health.php OK 后再打:
- `https://api.your-domain.com/leaderboard.php` -> 应返回 `[]`
- `https://api.your-domain.com/auth.php?action=me` -> 应返回 `{"user":null}`

测 Authorization 头传透 (Nginx + PHP-FPM 经典坑):
```bash
curl -H "Authorization: Bearer abcd1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcd" \
     https://api.your-domain.com/health.php
```
响应里 `"auth_header": "received (token abcd12…)"` 说明 Nginx 把头传给 PHP 了, OK。
如果是 `"no Bearer token in request ..."` -> Nginx 把头吃了, 改宝塔站点配置文件加:
```nginx
fastcgi_param HTTP_AUTHORIZATION $http_authorization;
```

如果 500 -> 检查宝塔的 PHP 错误日志 (站点 -> 日志,或者 `/www/wwwlogs/`)。最常见原因:
- `db.php` 里 DB 密码不对 (或还是 `'CHANGE_ME'`)
- PHP 没装 `pdo_mysql` 扩展 (宝塔 -> 软件商店 -> PHP 8.x -> 设置 -> 扩展,勾上 pdo_mysql)
- Nginx 没传 `Authorization` 头给 PHP-FPM。db.php 已经做了 `REDIRECT_HTTP_AUTHORIZATION` + `apache_request_headers` 双兜底,正常宝塔默认 Nginx 站不会出问题;如果 `/auth.php?action=me` 带 token 还是返回 `{"user":null}`,在宝塔站点 -> 配置文件加一行:
  ```nginx
  fastcgi_param HTTP_AUTHORIZATION $http_authorization;
  ```
- MySQL 时区跟 PHP 不一致导致 token 立刻过期 — 进 phpMyAdmin 执行 `SELECT NOW();` 跟服务器系统时间比对,差超过 1 小时就在 my.cnf 或宝塔 -> MySQL 改 `default-time-zone = '+08:00'`

如果浏览器报 CORS error 而 curl 直连后端却正常:确认 `db.php` 顶部 `CORS_ALLOWED_ORIGINS` 数组里有你前端的**确切域名**(协议+域+端口,结尾不带 `/`)。

### 7) 配置前端
编辑仓库里 `web/config.js`:
```js
window.METRO_BACKEND_URL = "https://api.your-domain.com";
```
`git commit + push` -> 等 GitHub Actions 部署完 -> 强刷 `https://vibetool.github.io/betagame/`,左上角按钮变成"登录 / 注册"。

## 数据迁移 / 备份
所有数据就在 MySQL 里这 3 张表。宝塔 -> 数据库 -> 备份 一键导出 `.sql.gz` 文件即可。

## 安全说明
- 密码以 bcrypt 哈希存储 (`password_hash`)
- 会话用 64 位十六进制 token,存数据库,60 天过期
- 所有 PDO 调用都用 prepared statement,无 SQL 注入风险
- 排行榜 RPC 只返回 `display_name` (邮箱前缀),不暴露邮箱本身
- `sessions` 表过期行可加宝塔计划任务清理: `DELETE FROM sessions WHERE expires_at < NOW()` 每天跑一次

## 协议结构 (供调试)
| 端点 | 方法 | Body | 响应 |
|---|---|---|---|
| `/auth.php?action=signup` | POST | `{email, password}` | `{token, user:{email, display_name}}` |
| `/auth.php?action=login`  | POST | `{email, password}` | 同上 |
| `/auth.php?action=logout` | POST | — | `{ok:true}` |
| `/auth.php?action=me`     | GET  | — | `{user:{...} \| null}` |
| `/save.php`               | GET  | — | `{coins, total_deliveries, coin_credited, best_score, best_score_at, current_game}` |
| `/save.php?type=stats`    | POST | `{coins, total_deliveries, coin_credited}` | `{ok:true}` |
| `/save.php?type=snapshot` | POST | `{snapshot:{…}}` | `{ok:true}` |
| `/save.php?type=snapshot` | DELETE | — | `{ok:true}` |
| `/save.php?type=best`     | POST | `{score}` | `{ok:true}` |
| `/leaderboard.php?limit=50` | GET | — | `[{display_name, best_score, best_score_at}, …]` |

所有需要登录的端点都通过 HTTP header `Authorization: Bearer <token>` 鉴权,token 由 login/signup 返回,前端存到 localStorage。
