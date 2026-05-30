<?php
// 排行榜 (匿名可读) — 只暴露 display_name + best_score, 不暴露 user_id / email
require __DIR__ . '/db.php';
send_cors();

$limit = max(1, min(200, (int)($_GET['limit'] ?? 50)));

$stmt = $db->prepare(
    'SELECT u.display_name, us.best_score, us.best_score_at
       FROM user_save us
       JOIN users u ON u.id = us.user_id
      WHERE us.best_score > 0
      ORDER BY us.best_score DESC, us.best_score_at ASC
      LIMIT ' . $limit
);
$stmt->execute();
$rows = $stmt->fetchAll();

foreach ($rows as &$r) {
    $r['best_score'] = (int)$r['best_score'];
}
unset($r);

json_out($rows);
