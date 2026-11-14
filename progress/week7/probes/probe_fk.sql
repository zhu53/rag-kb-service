-- W7-D2 探针：外键约束与级联在真 MySQL 里的行为（教材 §1.1 / §五 引用此输出）
-- 跑法（PowerShell，仓库根执行，先设 UTF-8 否则中文列名乱码）：
--   [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
--   & .\tools\mysql-8.4.0\bin\mysql.exe -h127.0.0.1 -P3307 -uroot -e "source progress/week7/probes/probe_fk.sql"
USE kb_dev;

DROP TABLE IF EXISTS probe_doc_fk;
DROP TABLE IF EXISTS probe_kb_fk;

CREATE TABLE probe_kb_fk (
  id   INT PRIMARY KEY,
  name VARCHAR(50) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE probe_doc_fk (
  id    INT PRIMARY KEY,
  title VARCHAR(60) NOT NULL,
  kb_id INT NOT NULL,
  CONSTRAINT fk_doc_kb FOREIGN KEY (kb_id)
    REFERENCES probe_kb_fk (id)
    ON DELETE CASCADE
) ENGINE=InnoDB;

INSERT INTO probe_kb_fk (id, name) VALUES (1, 'kb-AI');

-- 实验 1：给文档插一个不存在的 kb_id=999，看数据库拦不拦
SELECT '--- 实验 1: 插入孤儿 kb_id=999 ---' AS step;
INSERT INTO probe_doc_fk (id, title, kb_id) VALUES (1, 'ghost-doc', 999);

-- 实验 2：正常插入两篇文档，再删父行，验证 ON DELETE CASCADE
SELECT '--- 实验 2: 正常插入 2 篇 ---' AS step;
INSERT INTO probe_doc_fk (id, title, kb_id) VALUES (2, 'doc-a', 1), (3, 'doc-b', 1);
SELECT COUNT(*) AS docs_before_delete FROM probe_doc_fk;

SELECT '--- 实验 3: 删除父行 kb-AI，看子行还在不在 ---' AS step;
DELETE FROM probe_kb_fk WHERE id = 1;
SELECT COUNT(*) AS docs_after_delete FROM probe_doc_fk;

DROP TABLE probe_doc_fk;
DROP TABLE probe_kb_fk;
