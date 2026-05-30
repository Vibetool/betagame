-- ==============================================================
-- Mini Metro · 简洁地铁模拟 — MySQL / MariaDB 表结构
-- 在宝塔 -> 数据库 -> 你的库 -> 导入 -> 选这个文件
-- (或者数据库管理页面里粘贴执行)
-- ==============================================================

CREATE TABLE IF NOT EXISTS users (
  id              INT UNSIGNED   AUTO_INCREMENT PRIMARY KEY,
  email           VARCHAR(190)   NOT NULL UNIQUE,
  password_hash   VARCHAR(255)   NOT NULL,
  display_name    VARCHAR(64)    NOT NULL,
  created_at      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS sessions (
  token        CHAR(64)        NOT NULL PRIMARY KEY,
  user_id      INT UNSIGNED    NOT NULL,
  expires_at   DATETIME        NOT NULL,
  created_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  INDEX idx_sessions_user (user_id),
  INDEX idx_sessions_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS user_save (
  user_id           INT UNSIGNED  NOT NULL PRIMARY KEY,
  coins             INT           NOT NULL DEFAULT 0,
  total_deliveries  INT           NOT NULL DEFAULT 0,
  coin_credited     INT           NOT NULL DEFAULT 0,
  best_score        INT           NOT NULL DEFAULT 0,
  best_score_at     DATETIME      NULL,
  current_game      JSON          NULL,
  updated_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_user_save_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  INDEX idx_user_save_best (best_score)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
