<?php
// 注册 / 登录 / 退出 / 当前用户
require __DIR__ . '/db.php';
send_cors();

$action = $_GET['action'] ?? '';

if ($action === 'signup') {
    if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') fail('method not allowed', 405);
    $body = read_json();
    $email = strtolower(trim($body['email'] ?? ''));
    $password = $body['password'] ?? '';
    if (!filter_var($email, FILTER_VALIDATE_EMAIL)) fail('邮箱格式不正确');
    if (strlen($password) < 6) fail('密码至少 6 位');

    $check = $db->prepare('SELECT 1 FROM users WHERE email = ?');
    $check->execute([$email]);
    if ($check->fetchColumn()) fail('该邮箱已注册', 409);

    $hash = password_hash($password, PASSWORD_BCRYPT);
    $display = mb_substr(strstr($email, '@', true) ?: $email, 0, 32);
    $db->prepare('INSERT INTO users (email, password_hash, display_name) VALUES (?, ?, ?)')
        ->execute([$email, $hash, $display]);
    $user_id = (int)$db->lastInsertId();
    ensure_save_row($db, $user_id);

    $token = bin2hex(random_bytes(32));
    $db->prepare('INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, DATE_ADD(NOW(), INTERVAL ' . SESSION_DAYS . ' DAY))')
        ->execute([$token, $user_id]);

    json_out([
        'token' => $token,
        'user'  => ['email' => $email, 'display_name' => $display],
    ]);
}

if ($action === 'login') {
    if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') fail('method not allowed', 405);
    $body = read_json();
    $email = strtolower(trim($body['email'] ?? ''));
    $password = $body['password'] ?? '';

    $stmt = $db->prepare('SELECT id, email, display_name, password_hash FROM users WHERE email = ? LIMIT 1');
    $stmt->execute([$email]);
    $u = $stmt->fetch();
    if (!$u || !password_verify($password, $u['password_hash'])) {
        // 1 秒延迟降低暴力破解吞吐 (不严格防御, 简单防滥用)
        usleep(800000);
        fail('邮箱或密码不正确', 401);
    }
    ensure_save_row($db, (int)$u['id']);

    $token = bin2hex(random_bytes(32));
    $db->prepare('INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, DATE_ADD(NOW(), INTERVAL ' . SESSION_DAYS . ' DAY))')
        ->execute([$token, (int)$u['id']]);

    json_out([
        'token' => $token,
        'user'  => ['email' => $u['email'], 'display_name' => $u['display_name']],
    ]);
}

if ($action === 'logout') {
    $token = bearer_token();
    if ($token) {
        $db->prepare('DELETE FROM sessions WHERE token = ?')->execute([$token]);
    }
    json_out(['ok' => true]);
}

if ($action === 'me') {
    $u = current_user($db);
    if (!$u) json_out(['user' => null]);
    json_out(['user' => ['email' => $u['email'], 'display_name' => $u['display_name']]]);
}

fail('unknown action');
