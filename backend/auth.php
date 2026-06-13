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
    if (strlen($password) < 6 || strlen($password) > 128) fail('密码长度需 6 ~ 128 位');
    if (strlen($email) > 190) fail('邮箱过长');

    $hash = password_hash($password, PASSWORD_BCRYPT);
    $display = mb_substr(strstr($email, '@', true) ?: $email, 0, 32);

    // 预检 + 实际插入都可能撞 UNIQUE; 用 try/catch 兜底竞态 (两个并发请求都通过预检)
    try {
        $db->prepare('INSERT INTO users (email, password_hash, display_name) VALUES (?, ?, ?)')
            ->execute([$email, $hash, $display]);
    } catch (PDOException $e) {
        if ($e->getCode() === '23000') {
            fail('该邮箱已注册', 409);
        }
        throw $e;
    }
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

    // 即使用户不存在, 也跑一次 password_verify 防止通过响应时长枚举有效邮箱
    $hashToVerify = $u ? $u['password_hash']
                       : '$2y$10$' . str_repeat('a', 53);   // 固定假 hash, 仅消耗时间
    $ok = password_verify($password, $hashToVerify);

    if (!$u || !$ok) {
        usleep(800000);   // 简单防滥用降低吞吐
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
