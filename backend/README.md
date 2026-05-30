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

宝塔 -> 站点 -> 设置 -> SSL -> **Let's Encrypt**,域名打勾,申请 -> 强制 HTTPS。

> 没有域名? 自签证书或 IP+http 都不行 — 浏览器会拒绝。最便宜的国内域名 1 块/年,namesilo 国外域名约 60 块/年。或者直接把游戏 HTML 也搬到自己服务器,前后端同域,就不用 CORS 也不用 HTTPS 强制了。

### 6) 自检
浏览器打开 `https://api.your-domain.com/leaderboard.php` -> 应返回 `[]`。
打开 `https://api.your-domain.com/auth.php?action=me` -> 应返回 `{"user":null}`。

如果 500 -> 检查宝塔的 PHP 错误日志 (站点 -> 日志,或者 `/www/wwwlogs/`)。最常见原因:
- `db.php` 里 DB 密码不对
- PHP 没装 `pdo_mysql` 扩展 (宝塔 -> 软件商店 -> PHP 8.x -> 设置 -> 扩展,勾上 pdo_mysql)

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
