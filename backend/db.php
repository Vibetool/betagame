<?php
// ==============================================================
// 数据库连接 + 通用工具 (CORS / JSON / 当前用户)
// 把下面 4 行改成你宝塔创建的库 / 用户名 / 密码
// ==============================================================
const DB_HOST = '127.0.0.1';
const DB_NAME = 'metro_game';
const DB_USER = 'metro_user';
const DB_PASS = 'CHANGE_ME';

// 允许哪些前端域名跨域调用本 API (注意结尾不要带 / )
const CORS_ALLOWED_ORIGINS = [
    'https://vibetool.github.io',     // GitHub Pages
    'http://localhost:8765',           // 本地静态调试
    'http://127.0.0.1:8765',
];

// 会话 token 有效期 (天)
const SESSION_DAYS = 60;
// ==============================================================

// ---- CORS 必须在任何可能 exit() 的代码之前发出 ----
// 否则 DB 连接失败 / OPTIONS preflight 时浏览器会看不到 CORS 头, 把真实错误显示成 CORS 错误,
// 部署调试阶段 (尤其是首次填错 DB 密码) 这一步极易把人坑半小时。
function emit_cors_headers(): void {
    $origin = $_SERVER['HTTP_ORIGIN'] ?? '';
    // 即使 origin 不在白名单, 也要发 Vary 让中间缓存不混淆
    header('Vary: Origin');
    if ($origin !== '' && in_array($origin, CORS_ALLOWED_ORIGINS, true)) {
        header("Access-Control-Allow-Origin: $origin");
    }
    header('Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS');
    header('Access-Control-Allow-Headers: Content-Type, Authorization');
    header('Access-Control-Max-Age: 86400');
}

function send_cors(): void {
    emit_cors_headers();
    if (($_SERVER['REQUEST_METHOD'] ?? '') === 'OPTIONS') {
        http_response_code(204);
        exit;
    }
}

// 在 db 连接之前先发 CORS, 并尽早回应 OPTIONS preflight
// (preflight 不需要 DB, 因此 DB 挂掉时仍然能跨域)
send_cors();

try {
    $db = new PDO(
        'mysql:host=' . DB_HOST . ';dbname=' . DB_NAME . ';charset=utf8mb4',
        DB_USER,
        DB_PASS,
        [
            PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES   => false,
        ]
    );
} catch (Throwable $e) {
    // CORS 头已在 send_cors() 里发了, 这里只补 JSON body
    http_response_code(500);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode(['error' => 'db connect failed'], JSON_UNESCAPED_UNICODE);
    error_log('[metro] DB connect failed: ' . $e->getMessage());
    exit;
}

function read_json(): array {
    $raw = file_get_contents('php://input');
    if ($raw === '' || $raw === false) return [];
    $obj = json_decode($raw, true);
    return is_array($obj) ? $obj : [];
}

function json_out($data, int $code = 200): void {
    // 兜底再发一次 CORS (header 重复发送不会出错; 真要拦在 send_cors() 之前调用时这是唯一兜底)
    if (!headers_sent()) emit_cors_headers();
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

function fail(string $msg, int $code = 400): void {
    json_out(['error' => $msg], $code);
}

function bearer_token(): ?string {
    $h = $_SERVER['HTTP_AUTHORIZATION'] ?? '';
    // 某些 fastcgi 把 Authorization 重命名为 REDIRECT_HTTP_AUTHORIZATION
    if ($h === '' && !empty($_SERVER['REDIRECT_HTTP_AUTHORIZATION'])) {
        $h = $_SERVER['REDIRECT_HTTP_AUTHORIZATION'];
    }
    // 兼容 apache_request_headers (并非所有 SAPI 都填 HTTP_AUTHORIZATION)
    if ($h === '' && function_exists('apache_request_headers')) {
        $headers = apache_request_headers();
        foreach ($headers as $k => $v) {
            if (strcasecmp($k, 'Authorization') === 0) { $h = $v; break; }
        }
    }
    if (preg_match('/Bearer\s+([A-Fa-f0-9]{32,128})/', $h, $m)) {
        return $m[1];
    }
    return null;
}

function current_user(PDO $db): ?array {
    $token = bearer_token();
    if (!$token) return null;
    $stmt = $db->prepare(
        'SELECT u.id, u.email, u.display_name
           FROM users u
           JOIN sessions s ON s.user_id = u.id
          WHERE s.token = :tok AND s.expires_at > NOW()
          LIMIT 1'
    );
    $stmt->execute([':tok' => $token]);
    $row = $stmt->fetch();
    return $row ?: null;
}

function require_user(PDO $db): array {
    $u = current_user($db);
    if (!$u) fail('unauthorized', 401);
    return $u;
}

function ensure_save_row(PDO $db, int $user_id): void {
    $db->prepare('INSERT IGNORE INTO user_save (user_id) VALUES (?)')->execute([$user_id]);
}
