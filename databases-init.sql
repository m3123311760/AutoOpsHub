-- AutoOpsHub 本地认证、JWT 会话与 API Key 元数据初始化脚本
-- 由运维/CI 在部署前执行；应用不会自动运行本文件

CREATE TABLE IF NOT EXISTS auth_users (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '用户主键',
  username VARCHAR(191) NOT NULL COMMENT '登录用户名',
  password_hash VARCHAR(255) NOT NULL COMMENT '密码哈希（bcrypt）',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_auth_users_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='本地认证用户';

CREATE TABLE IF NOT EXISTS auth_jwt_sessions (
  jti CHAR(36) NOT NULL COMMENT 'JWT ID',
  subject_username VARCHAR(191) NOT NULL COMMENT '主体用户名',
  expires_at DATETIME NOT NULL COMMENT '过期时间',
  revoked_at DATETIME NULL DEFAULT NULL COMMENT '撤销时间',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (jti),
  KEY idx_auth_jwt_sessions_subject (subject_username),
  KEY idx_auth_jwt_sessions_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='JWT 会话元数据';

CREATE TABLE IF NOT EXISTS auth_api_keys (
  id CHAR(36) NOT NULL COMMENT 'API Key 记录 ID',
  name VARCHAR(191) NOT NULL DEFAULT '' COMMENT '展示名称',
  key_prefix VARCHAR(32) NOT NULL COMMENT '明文前缀用于识别',
  key_hash VARCHAR(255) NOT NULL COMMENT '完整 Key 的哈希',
  revoked_at DATETIME NULL DEFAULT NULL COMMENT '撤销时间',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (id),
  KEY idx_auth_api_keys_prefix (key_prefix)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='API Key 元数据';
