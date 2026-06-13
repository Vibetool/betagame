<?php
// 部署自检端点 — curl 一下就能定位是 DB / Auth header / CORS 哪一步出问题
// 公开可读, 不暴露任何敏感信息
require __DIR__ . '/db.php';

$out = [
    'ok'          => true,
    'php_version' => PHP_VERSION,
    'time'        => date('c'),
    'db'          => null,
    'tables'      => null,
    'auth_header' => null,
    'origin'      => $_SERVER['HTTP_ORIGIN'] ?? null,
];

// 1) DB 连得通否 (能 require 进来 db.php 说明连通; 这里再 ping 一下)
try {
    $ping = $db->query('SELECT 1');
    $out['db'] = $ping->fetchColumn() == 1 ? 'connected' : 'unexpected';
} catch (Throwable $e) {
    $out['ok'] = false;
    $out['db'] = 'error: ' . $e->getMessage();
}

// 2) 三张表都在否
try {
    $rows = $db->query("SHOW TABLES")->fetchAll(PDO::FETCH_COLUMN);
    $need = ['users', 'sessions', 'user_save'];
    $missing = array_diff($need, $rows);
    $out['tables'] = $missing ? ['missing' => array_values($missing)] : 'ok';
    if ($missing) $out['ok'] = false;
} catch (Throwable $e) {
    $out['ok'] = false;
    $out['tables'] = 'error: ' . $e->getMessage();
}

// 3) Authorization 头能不能传到 PHP (Nginx + fastcgi 经常吃头, 这里能直观看到)
$token = bearer_token();
$out['auth_header'] = $token ? 'received (token ' . substr($token, 0, 6) . '…)'
                             : 'no Bearer token in request (正常; 用 curl -H "Authorization: Bearer abcd1234..." 验证传透)';

json_out($out);
