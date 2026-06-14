<?php
// 当前用户的存档读 / 写 / 一局快照 / 最高分
//   GET   /save.php                 -> 拉所有字段
//   POST  /save.php?type=stats      -> 上传 coins / total_deliveries / coin_credited
//   POST  /save.php?type=snapshot   -> 上传 current_game (JSON)
//   POST  /save.php?type=best       -> 仅当传入 score > 旧 best_score 时更新
//   DELETE /save.php?type=snapshot  -> 清空 current_game

require __DIR__ . '/db.php';
send_cors();

$u = require_user($db);
// 兜底: 万一 user_save 行因为某种原因不存在 (历史数据迁移 / 早期 schema), 自补一行
// 否则后续 UPDATE 都会 affected_rows=0 静默无效, 用户以为存档成功但其实丢了
ensure_save_row($db, (int)$u['id']);
$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
$type   = $_GET['type'] ?? 'stats';

if ($method === 'GET') {
    $stmt = $db->prepare(
        'SELECT coins, total_deliveries, coin_credited, best_score, best_score_at, current_game
           FROM user_save WHERE user_id = ? LIMIT 1'
    );
    $stmt->execute([(int)$u['id']]);
    $row = $stmt->fetch();
    if (!$row) {
        $row = [
            'coins' => 0, 'total_deliveries' => 0, 'coin_credited' => 0,
            'best_score' => 0, 'best_score_at' => null, 'current_game' => null,
        ];
    } else {
        $row['coins']            = (int)$row['coins'];
        $row['total_deliveries'] = (int)$row['total_deliveries'];
        $row['coin_credited']    = (int)$row['coin_credited'];
        $row['best_score']       = (int)$row['best_score'];
        if (!empty($row['current_game'])) {
            $row['current_game'] = json_decode($row['current_game'], true);
        } else {
            $row['current_game'] = null;
        }
    }
    json_out($row);
}

if ($method === 'POST' || $method === 'PUT') {
    $body = read_json();
    if ($type === 'stats') {
        $coins = max(0, (int)($body['coins'] ?? 0));
        $td    = max(0, (int)($body['total_deliveries'] ?? 0));
        $cc    = max(0, (int)($body['coin_credited'] ?? 0));
        $db->prepare(
            'UPDATE user_save
                SET coins = ?, total_deliveries = ?, coin_credited = ?
              WHERE user_id = ?'
        )->execute([$coins, $td, $cc, (int)$u['id']]);
        json_out(['ok' => true]);
    }
    if ($type === 'snapshot') {
        $snap = $body['snapshot'] ?? null;
        $json = $snap ? json_encode($snap, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) : null;
        $db->prepare('UPDATE user_save SET current_game = ? WHERE user_id = ?')
            ->execute([$json, (int)$u['id']]);
        json_out(['ok' => true]);
    }
    if ($type === 'best') {
        $score = max(0, (int)($body['score'] ?? 0));
        // 注意: MySQL 单表 UPDATE 的 SET 从左到右求值, 后面的赋值会读到前面刚改过的新值.
        // 所以必须先用旧 best_score 算 best_score_at, 再更新 best_score; 否则破纪录时
        // best_score 先变成新分, CASE 里的 "? > best_score" 永远为假, 时间戳从不写入.
        $db->prepare(
            'UPDATE user_save
                SET best_score_at = CASE WHEN ? > best_score THEN NOW() ELSE best_score_at END,
                    best_score    = GREATEST(best_score, ?)
              WHERE user_id = ?'
        )->execute([$score, $score, (int)$u['id']]);
        json_out(['ok' => true]);
    }
    fail('unknown type');
}

if ($method === 'DELETE' && $type === 'snapshot') {
    $db->prepare('UPDATE user_save SET current_game = NULL WHERE user_id = ?')
        ->execute([(int)$u['id']]);
    json_out(['ok' => true]);
}

fail('method/type not supported', 405);
