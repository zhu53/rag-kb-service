-- W7-D1b 配置态实测：教材 §三 ~ §八 每个数字的来源
-- 用法（Git Bash / PowerShell 都可以，exe 路径按自己机器改）：
--   ./bin/mysql.exe -h 127.0.0.1 -P 3307 -u root --default-character-set=utf8mb4 < probe_config.sql
-- 注意：这个脚本会建/删一个叫 cfg_lab 的库，不碰 kb_dev。

-- ============ 1. 服务端字符集 / 时区 / 隔离级别 / 上限（§2.2、§四、§八） ============
SELECT '--- 1. server 层 ---' AS s;
SHOW VARIABLES LIKE 'character_set_server';
SHOW VARIABLES LIKE 'collation_server';
SHOW VARIABLES LIKE 'character_set_client';
SHOW VARIABLES LIKE 'character_set_connection';
SHOW VARIABLES LIKE 'character_set_results';
SHOW VARIABLES LIKE 'transaction_isolation';
SHOW VARIABLES LIKE 'time_zone';
SHOW VARIABLES LIKE 'system_time_zone';
SHOW VARIABLES LIKE 'wait_timeout';
SHOW VARIABLES LIKE 'max_connections';
SHOW VARIABLES LIKE 'sql_mode';
SHOW VARIABLES LIKE 'innodb_buffer_pool_size';
SHOW VARIABLES LIKE 'lower_case_table_names';

-- ============ 2. 账号与认证插件（§六） ============
SELECT user, host, plugin FROM mysql.user ORDER BY user, host;
SELECT PLUGIN_NAME, PLUGIN_STATUS FROM information_schema.PLUGINS WHERE PLUGIN_NAME LIKE '%password%';

-- ============ 3. 变量从哪来（§8.4，最强排查工具） ============
SELECT VARIABLE_NAME, VARIABLE_SOURCE, VARIABLE_PATH, SET_TIME, SET_USER
FROM performance_schema.variables_info
WHERE VARIABLE_SOURCE <> 'COMPILED'
ORDER BY VARIABLE_SOURCE, VARIABLE_NAME;
SELECT VARIABLE_SOURCE, COUNT(*) AS n
FROM performance_schema.variables_info GROUP BY VARIABLE_SOURCE ORDER BY n DESC;

-- ============ 4. 初始化时字符集落盘（§3.10） ============
SHOW CREATE DATABASE mysql;
SHOW CREATE DATABASE kb_dev;

-- ============ 5. 字符集 / collation / 长度（§3.5 ~ §3.9） ============
DROP DATABASE IF EXISTS cfg_lab;
CREATE DATABASE cfg_lab CHARACTER SET utf8mb4;
USE cfg_lab;

CREATE TABLE t_utf8mb3 (name VARCHAR(20)) CHARACTER SET utf8mb3;
CREATE TABLE t_utf8mb4 (name VARCHAR(20)) CHARACTER SET utf8mb4;
INSERT INTO t_utf8mb4 VALUES ('😀');
SELECT name, CHAR_LENGTH(name) AS 字符数, LENGTH(name) AS 字节数 FROM t_utf8mb4;

-- 下面这条会报 1366，是预期结果（严格模式下 4 字节字符进不了 3 字节列）
-- INSERT INTO t_utf8mb3 VALUES ('😀');

SELECT '--- collation 决定"什么算相等" ---' AS s;
SELECT 'a' = 'A' COLLATE utf8mb4_0900_ai_ci AS ci_a_eq_A,
       'a' = 'A' COLLATE utf8mb4_0900_as_cs AS cs_a_eq_A,
       'a' = 'á' COLLATE utf8mb4_0900_ai_ci AS ai_a_eq_acute,
       'a' = 'á' COLLATE utf8mb4_0900_as_cs AS as_a_eq_acute;
SELECT '--- _bin 是字节序，as_cs 仍按 Unicode 权重 ---' AS s;
SELECT 'a' < 'B' COLLATE utf8mb4_bin AS bin_a_lt_B,
       'a' < 'B' COLLATE utf8mb4_0900_as_cs AS ascs_a_lt_B,
       'A' < 'a' COLLATE utf8mb4_bin AS bin_A_lt_a;
SELECT '--- general_ci vs 0900_ai_ci ---' AS s;
SELECT 'ß' = 'ss' COLLATE utf8mb4_general_ci AS general_ss,
       'ß' = 'ss' COLLATE utf8mb4_0900_ai_ci AS ai0900_ss,
       '①' = '1' COLLATE utf8mb4_general_ci AS general_circle,
       '①' = '1' COLLATE utf8mb4_0900_ai_ci AS ai0900_circle;

-- VARCHAR(N) 的 N 是字符数：5 个中文 = 15 字节，5 个 emoji = 20 字节
CREATE TABLE t_len (name VARCHAR(5)) CHARACTER SET utf8mb4;
INSERT INTO t_len VALUES ('中文中文中'), ('😀😀😀😀😀');
SELECT name, CHAR_LENGTH(name) AS 字符数, LENGTH(name) AS 字节数 FROM t_len;

-- 唯一索引受 collation 影响（ci 下表里已有 Alice，再插 alice 报 1062）
CREATE TABLE t_uniq_ci (name VARCHAR(20) COLLATE utf8mb4_0900_ai_ci UNIQUE);
CREATE TABLE t_uniq_bin (name VARCHAR(20) COLLATE utf8mb4_bin UNIQUE);
INSERT INTO t_uniq_ci VALUES ('Alice');
INSERT INTO t_uniq_bin VALUES ('Alice'), ('alice');
SELECT '--- bin 表两条共存，ci 表再插 alice 会 1062 ---' AS s;
SELECT * FROM t_uniq_bin;

-- ============ 6. 时区：DATETIME 不动，TIMESTAMP 差 8 小时（§4.1） ============
CREATE TABLE t_time (d DATETIME, ts TIMESTAMP NULL);
SET time_zone = '+08:00';
INSERT INTO t_time VALUES (NOW(), NOW());
SELECT @@session.time_zone AS tz, d, ts FROM t_time;
SET time_zone = '+00:00';
SELECT @@session.time_zone AS tz, d, ts, TIMESTAMPDIFF(HOUR, d, ts) AS 差几小时 FROM t_time;

-- ============ 7. 严格模式 vs 非严格模式（§5.1） ============
SET SESSION sql_mode = '';
INSERT INTO t_len VALUES ('abcdef');       -- 超长，非严格模式下被截断
SELECT name, CHAR_LENGTH(name) AS 存了几个字符 FROM t_len WHERE name LIKE 'abc%';

-- ============ 8. 表名大小写（§8.5） ============
CREATE TABLE IF NOT EXISTS CaseTest (id INT);
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'cfg_lab' AND table_name LIKE '%asetest%';

-- ============ 清理 ============
DROP DATABASE cfg_lab;
SELECT 'done' AS s;
