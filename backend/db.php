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
    http_response_code(500);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode(['error' => 'db connect failed']);
    error_log('[metro] DB connect failed: ' . $e->getMessage());
    exit;
}

function send_cors(): void {
    $origin = $_SERVER['HTTP_ORIGIN'] ?? '';
    if (in_array($origin, CORS_ALLOWED_ORIGINS, true)) {
        header("Access-Control-Allow-Origin: $origin");
        header('Vary: Origin');
    }
    header('Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS');
    header('Access-Control-Allow-Headers: Content-Type, Authorization');
    header('Access-Control-Max-Age: 86400');
    if (($_SERVER['REQUEST_METHOD'] ?? '') === 'OPTIONS') {
        http_response_code(204);
        exit;
    }
}

function read_json(): array {
    $raw = file_get_contents('php://input');
    if ($raw === '' || $raw === false) return [];
    $obj = json_decode($raw, true);
    return is_array($obj) ? $obj : [];
}

function json_out($data, int $code = 200): void {
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
