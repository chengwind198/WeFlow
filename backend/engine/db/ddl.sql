-- ============================================================
-- weflow 数据库 DDL
-- 数据库文件: scripts/db/weflow.db
-- 引擎: SQLite 3.35+ (WAL 模式, STRICT 表)
-- ============================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

BEGIN;

-- ============================================================
-- 任务状态码值对照表
-- 状态码采用 10/20/30… 编号，方便排序和扩展
-- ============================================================
-- @table-comment 任务状态码值对照表
CREATE TABLE task_status (
    code        INTEGER PRIMARY KEY,                                  -- @comment 状态码（10/20/30/…）
    name        TEXT    NOT NULL UNIQUE,                              -- @comment 状态名称（如 brief_ready）
    label       TEXT    NOT NULL DEFAULT '',                          -- @comment 中文标签（如 "选题已就绪"）
    description TEXT    NOT NULL DEFAULT '',                          -- @comment 状态说明
    applies_to  TEXT    NOT NULL DEFAULT 'both',                      -- @comment 适用类型: article / image / both
    is_terminal INTEGER NOT NULL DEFAULT 0,                           -- @comment 是否终态: 0=否 1=是（published / abandoned）
    sort_order   INTEGER NOT NULL DEFAULT 0                           -- @comment 排序权重（用于 UI 展示）
) STRICT;

-- 预置状态码数据
INSERT INTO task_status (code, name, label, description, applies_to, is_terminal, sort_order) VALUES
-- 通用（both）
( 0, 'abandoned',         '出错了',   '任务被手动终止',                                    'both',    1, 99),
(10, 'created',           '已创建',   '任务已创建，尚未开始',                               'both',    0,  1),
(20, 'brief_ready',       '选题已就绪','选题简报已编写完成',                               'both',    0,  2),
-- 图文专属（article）
(30, 'research_done',     '调研完成',  '调研已生成',                                'article',    0,  3),
(40, 'draft_ready',       '文章已写好','文章初稿完成',                               'article',    0,  4),
(50, 'humanized',         '人味化完成','反 AI 检测改写 pass 完成',                           'article',    0,  5),
-- 贴图专属（image）
(35, 'cards_planned',     '贴图已规划','已写入贴图占位记录',                         'image', 0,  3),
-- 通用（both）
(60, 'images_generated',  '配图已生成','AI 配图全部生成完毕',                                'both',    0,  6),
-- 图文专属（news）
(70, 'html_converted',    'HTML 已转换','文章排版完成',                             'article',    0,  7),
-- 通用（both）
(80, 'ai_score_passed',   'AI 味通过', 'ai_score.py 检测 PASS',                             'both',    0,  8),
(85, 'ai_score_failed',   'AI 味未过', 'ai_score.py 检测 FAIL/WARN，需返回重写',              'both',    0,  9),
(90, 'published',         '已发布',    '文章已发布到草稿箱/群发',                             'both',    1, 10);

/*
状态流转:

article（图文）:
  10(created) → 20(brief_ready) → 30(research_done) → 40(draft_ready) → 50(humanized)
  → 60(images_generated) → 70(html_converted) → 80(ai_score_passed) → 90(published)
  └→ 85(ai_score_failed) → 50(humanized)（回到人味化重写）

image（贴图）:
  10(created) → 20(brief_ready) → 35(cards_planned) → 60(images_generated)
  → 80(ai_score_passed) → 90(published)
  └→ 85(ai_score_failed) → 20(brief_ready)（回到改写短文本）

通用:
  任意状态 → 0(abandoned)

查询可读状态名:
  SELECT t.id, s.label AS status_name
  FROM task t JOIN task_status s ON s.code = t.status;
*/


-- ============================================================
-- 任务表
-- ============================================================
-- @table-comment 任务主表
CREATE TABLE task (
    id              INTEGER PRIMARY KEY,                                  -- @comment 自增主键
    topic           TEXT    NOT NULL DEFAULT '',                          -- @comment 用户输入的文章话题（title 为 AI 最终返回的标题）
    title           TEXT    NOT NULL DEFAULT '',                          -- @comment AI 最终返回的文章标题
    account         TEXT    NOT NULL DEFAULT 'main',                      -- @comment 目标账号（main/tech）
    type            TEXT    NOT NULL DEFAULT 'article',                   -- @comment 任务类型: article（图文）| image（贴图）
    need_images     INTEGER NOT NULL DEFAULT 1,                           -- @comment 是否需要配图: 0=否（--no-images）1=是
    status          INTEGER NOT NULL DEFAULT 10,                          -- @comment 当前状态码（关联 task_status.code）
    task_path       TEXT    NOT NULL DEFAULT '',                          -- @comment 文章相关本地产出物路径（如 generated/20260731-1729_main_14）
    app_id          TEXT    NOT NULL DEFAULT '',                          -- @comment 初始来源 config.yaml
    author          TEXT    NOT NULL DEFAULT '',                          -- @comment 初始来源 config.yaml
    theme           TEXT    NOT NULL DEFAULT '',                          -- @comment 排版主题名（如 refined-blue），初始来源 config.yaml
    image_style     TEXT    NOT NULL DEFAULT '',                          -- @comment 配图风格名（如 hand-drawn-blue），初始来源 config.yaml
    newspic_image_style TEXT NOT NULL DEFAULT '',                         -- @comment 贴图模式配图风格，初始来源 config.yaml
    article_structure TEXT  NOT NULL DEFAULT '',                          -- @comment 文章结构，初始来源 config.yaml
    opening_hook    TEXT    NOT NULL DEFAULT '',                          -- @comment 开头钩子，初始来源 config.yaml
    voice           TEXT    NOT NULL DEFAULT '',                          -- @comment 语气风格，初始来源 config.yaml
    genre           TEXT    NOT NULL DEFAULT '',                          -- @comment 文章体裁/表达方式，article 模式有效，AI 从 brief.md 提取
    short_text      TEXT    NOT NULL DEFAULT '',                          -- @comment 短文本描述，image 模式有效，AI 从 brief.md 提取
    sync_platforms  TEXT    NOT NULL DEFAULT '',                          -- @comment 同步平台列表（JSON 数组），初始来源 config.yaml
    user_details    TEXT    NOT NULL DEFAULT '',                          -- @comment 用户的要求或细节，初始来源创建任务时传入
    word_count      INTEGER NOT NULL DEFAULT 0,                           -- @comment 终稿字数
    ai_score        REAL    NOT NULL DEFAULT 0.0,                        -- @comment AI 味检测总分（0-100）
    ai_verdict      TEXT    NOT NULL DEFAULT '',                          -- @comment AI 检测结论: PASS / WARN / FAIL
    is_deleted      INTEGER NOT NULL DEFAULT 0,                          -- @comment 软删除标记: 0=正常 1=已删除
    created_at      INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),    -- @comment 创建时间戳
    updated_at      INTEGER NOT NULL DEFAULT (strftime('%s', 'now'))     -- @comment 最后更新时间戳
) STRICT;

CREATE INDEX idx_task_account   ON task(account);
CREATE INDEX idx_task_status    ON task(status);
CREATE INDEX idx_task_type      ON task(type);
CREATE INDEX idx_task_created   ON task(created_at);


-- ============================================================
-- 任务状态历史记录表
-- ============================================================
-- @table-comment 任务状态变更审计日志
CREATE TABLE task_status_history (
    id            INTEGER PRIMARY KEY,                                  -- @comment 自增主键
    task_id       INTEGER NOT NULL,                                     -- @comment 关联任务 ID
    to_status     INTEGER NOT NULL,                                     -- @comment 变更后状态码（关联 task_status.code）
    business_key  TEXT    NOT NULL DEFAULT '',                          -- @comment 业务唯一键（如阶段名：brief/research/draft/…）
    to_info       TEXT    NOT NULL DEFAULT '',                          -- @comment 变更后的信息（如生成的文件路径、上传的 URL 等）
    remark        TEXT    NOT NULL DEFAULT '',                          -- @comment 备注
    operator      TEXT    NOT NULL DEFAULT 'system',                    -- @comment 操作者（system / agent / 用户名）
    duration_s    INTEGER NOT NULL DEFAULT 0,                           -- @comment 上一状态持续秒数
    created_at    INTEGER NOT NULL DEFAULT (strftime('%s', 'now'))      -- @comment 变更时间戳
) STRICT;

CREATE INDEX idx_tsh_task         ON task_status_history(task_id);
CREATE INDEX idx_tsh_to_status    ON task_status_history(to_status);
CREATE INDEX idx_tsh_created      ON task_status_history(created_at);


-- ============================================================
-- 生成的图片表
-- ============================================================
-- @table-comment AI 生成图片记录（含上传状态）
CREATE TABLE task_image (
    id              INTEGER PRIMARY KEY,                                  -- @comment 自增主键
    task_id         INTEGER NOT NULL,                                     -- @comment 关联任务 ID
    message_id      INTEGER NOT NULL DEFAULT 0,                           -- @comment 关联 task_message.id（draft 阶段 assistant 返回的配图规划）
    seq             INTEGER NOT NULL DEFAULT 1,                           -- @comment 文章中的顺序号（01, 02, ...）
    anchor          TEXT    NOT NULL DEFAULT '',                          -- @comment 文章里的图片锚点（如 anchor://image-001）
    description     TEXT    NOT NULL DEFAULT '',                          -- @comment 文章里的图片描述
    prompt          TEXT    NOT NULL,                                     -- @comment 生图提示词
    provider        TEXT    NOT NULL,                                     -- @comment 生图 provider（qwen_image / z_image / …）
    model           TEXT    NOT NULL,                                     -- @comment 模型 ID
    image_style     TEXT    NOT NULL DEFAULT '',                          -- @comment 图片的风格
    size            TEXT    NOT NULL DEFAULT '',                          -- @comment 请求尺寸（如 1024x1024）
    local_path      TEXT    NOT NULL DEFAULT '',                          -- @comment 本地文件完整路径
    local_size      INTEGER NOT NULL DEFAULT 0,                           -- @comment 本地文件大小（字节）
    width           INTEGER NOT NULL DEFAULT 0,                           -- @comment 图片宽度（像素）
    height          INTEGER NOT NULL DEFAULT 0,                           -- @comment 图片高度（像素）
    format          TEXT    NOT NULL DEFAULT 'png',                       -- @comment 图片格式（png/jpg/webp）
    -- 上传相关字段
    upload_status   TEXT    NOT NULL DEFAULT 'pending',                   -- @comment 状态: pending(占位) / generated(已生成) / generate_failed(生成失败) / uploading / uploaded / failed(上传失败) / skipped
    upload_cdn_url  TEXT    NOT NULL DEFAULT '',                          -- @comment 上传后的微信 CDN URL
    upload_media_id TEXT    NOT NULL DEFAULT '',                          -- @comment 上传后的微信 media_id（封面图 / 贴图素材用）
    upload_error    TEXT    NOT NULL DEFAULT '',                          -- @comment 上传失败原因
    is_cover        INTEGER NOT NULL DEFAULT 0,                           -- @comment 是否用作封面图: 0=否 1=是
    tokens_in       INTEGER NOT NULL DEFAULT 0,                           -- @comment 生图消耗的输入 token（估算或 API 返回）
    tokens_out      INTEGER NOT NULL DEFAULT 0,                           -- @comment 生图消耗的输出 token（估算或 API 返回）
    created_at      INTEGER NOT NULL DEFAULT (strftime('%s', 'now'))     -- @comment 创建时间戳
) STRICT;

CREATE INDEX idx_ti_task           ON task_image(task_id);
CREATE INDEX idx_ti_upload_status  ON task_image(upload_status);
CREATE INDEX idx_ti_provider       ON task_image(provider);


-- ============================================================
-- 大模型调用记录表
-- ============================================================
-- @table-comment 大模型 API 调用审计日志
CREATE TABLE llm_call_log (
    id              INTEGER PRIMARY KEY,                                  -- @comment 自增主键
    task_id         INTEGER NOT NULL DEFAULT 0,                           -- @comment 关联任务 ID（0 表示非任务调用）
    call_type       TEXT    NOT NULL,                                     -- @comment 调用类型: text（文本 LLM）| image（生图模型）
    stage           TEXT    NOT NULL DEFAULT '',                          -- @comment 调用阶段: brief / research / draft / humanize / generate / publish
    provider        TEXT    NOT NULL,                                     -- @comment 模型提供商（deepseek / openai / qwen_image / z_image / …）
    model           TEXT    NOT NULL,                                     -- @comment 模型 ID
    -- 请求信息
    prompt          TEXT    NOT NULL DEFAULT '',                          -- @comment 完整提示词
    prompt_chars    INTEGER NOT NULL DEFAULT 0,                           -- @comment 提示词字符数
    -- 响应信息
    response        TEXT    NOT NULL DEFAULT '',                          -- @comment 响应内容（文本回答 或 图片 URL/base64截断）
    tokens_in       INTEGER NOT NULL DEFAULT 0,                           -- @comment 输入 token 数（文本模型适用）
    tokens_out      INTEGER NOT NULL DEFAULT 0,                           -- @comment 输出 token 数（文本模型适用）
    -- 图片模型专属
    image_count     INTEGER NOT NULL DEFAULT 0,                           -- @comment 生成图片数量（图片模型适用）
    image_size      TEXT    NOT NULL DEFAULT '',                          -- @comment 请求尺寸（图片模型适用）
    -- 性能与状态
    duration_ms     INTEGER NOT NULL DEFAULT 0,                           -- @comment API 调用耗时（毫秒）
    status          TEXT    NOT NULL DEFAULT 'pending',                   -- @comment 调用状态: pending / success / failed / retried
    finish_msg      TEXT    NOT NULL DEFAULT '',                          -- @comment 结束信息（finish_reason / 失败原因）
    retry_count     INTEGER NOT NULL DEFAULT 0,                           -- @comment 重试次数
    -- 成本估算
    cost_est        REAL    NOT NULL DEFAULT 0.0,                         -- @comment 估算费用（美元）
    created_at      INTEGER NOT NULL DEFAULT (strftime('%s', 'now'))     -- @comment 创建时间戳
) STRICT;

CREATE INDEX idx_ll_task      ON llm_call_log(task_id);
CREATE INDEX idx_ll_type      ON llm_call_log(call_type);
CREATE INDEX idx_ll_stage     ON llm_call_log(stage);
CREATE INDEX idx_ll_provider  ON llm_call_log(provider);
CREATE INDEX idx_ll_status    ON llm_call_log(status);
CREATE INDEX idx_ll_created   ON llm_call_log(created_at);


-- ============================================================
-- 任务与大模型对话记录表
-- ============================================================
-- @table-comment 任务与大模型对话历史（按 stage / image_id 分组）
CREATE TABLE task_message (
    id              INTEGER PRIMARY KEY,                                  -- @comment 自增主键
    task_id         INTEGER NOT NULL,                                     -- @comment 关联任务 ID
    image_id        INTEGER NOT NULL DEFAULT 0,                           -- @comment 关联 task_image.id（0 表示非文生图对话）
    stage           TEXT    NOT NULL DEFAULT '',                          -- @comment 调用阶段: brief / research / draft / humanize / generate / publish
    provider        TEXT    NOT NULL,                                     -- @comment 模型提供商（deepseek / openai / qwen_image / …）
    model           TEXT    NOT NULL,                                     -- @comment 模型 ID
    role            TEXT    NOT NULL,                                     -- @comment 角色: system / user / assistant / tool
    message         TEXT    NOT NULL DEFAULT '',                          -- @comment 对话消息内容
    created_at      INTEGER NOT NULL DEFAULT (strftime('%s', 'now'))     -- @comment 创建时间戳
) STRICT;

CREATE INDEX idx_tm_task       ON task_message(task_id);
CREATE INDEX idx_tm_task_stage ON task_message(task_id, stage);
CREATE INDEX idx_tm_image      ON task_message(task_id, image_id);
CREATE INDEX idx_tm_role       ON task_message(role);


-- ============================================================
-- 任务发布记录表
-- ============================================================
-- @table-comment 多平台发布记录
CREATE TABLE publish_record (
    id              INTEGER PRIMARY KEY,                                  -- @comment 自增主键
    task_id         INTEGER NOT NULL,                                     -- @comment 关联任务 ID
    platform        TEXT    NOT NULL DEFAULT 'wechat',                    -- @comment 发布平台（wechat / zhihu / juejin / csdn / toutiao / …）
    publish_type    TEXT    NOT NULL DEFAULT 'draft',                     -- @comment 发布方式: draft（草稿箱）| publish（直接群发）
    media_id        TEXT    NOT NULL DEFAULT '',                          -- @comment 平台返回的 media_id / 草稿 ID / 文章 ID
    title           TEXT    NOT NULL DEFAULT '',                          -- @comment 发布时使用的标题
    digest          TEXT    NOT NULL DEFAULT '',                          -- @comment 发布时使用的摘要
    url             TEXT    NOT NULL DEFAULT '',                          -- @comment 发布后的公网 URL（如有）
    image_count     INTEGER NOT NULL DEFAULT 0,                           -- @comment 发布时包含的图片数量
    word_count      INTEGER NOT NULL DEFAULT 0,                           -- @comment 发布时的字数
    ai_score_at_pub REAL    NOT NULL DEFAULT 0.0,                        -- @comment 发布时的 AI 味检测分
    status          TEXT    NOT NULL DEFAULT 'pending',                   -- @comment 发布状态: pending / submitted / success / failed
    error_msg       TEXT    NOT NULL DEFAULT '',                          -- @comment 发布失败原因
    published_at    INTEGER,                                              -- @comment 实际发布时间戳（群发时间，草稿为 NULL）
    created_at      INTEGER NOT NULL DEFAULT (strftime('%s', 'now'))     -- @comment 记录创建时间戳
) STRICT;

CREATE INDEX idx_pr_task      ON publish_record(task_id);
CREATE INDEX idx_pr_platform  ON publish_record(platform);
CREATE INDEX idx_pr_status    ON publish_record(status);
CREATE INDEX idx_pr_pub_at    ON publish_record(published_at);


-- ============================================================
-- 多平台同步记录表
-- ============================================================
-- @table-comment 多平台同步任务记录（每个 task 只保留一条同步记录）
CREATE TABLE task_sync (
    id              INTEGER PRIMARY KEY,
    task_id         INTEGER,                                              -- @comment 关联任务 ID（local/url 来源时为 NULL）
    markdown_content TEXT   NOT NULL DEFAULT '',                          -- @comment 同步时的 Markdown 内容
    platforms       TEXT    NOT NULL DEFAULT '[]',                        -- @comment 同步目标平台（JSON 数组）
    sync_from       TEXT    NOT NULL DEFAULT 'task',                      -- @comment 来源: task / local / url
    url             TEXT,                                                 -- @comment URL 来源时记录目标网址
    file_path       TEXT,                                                 -- @comment .md 文件全路径
    status          TEXT    NOT NULL DEFAULT 'pending',                   -- @comment 同步状态: draft(尚未执行同步) / pending / syncing / success / partial / failed
    created_at      INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),    -- @comment 创建时间戳
    updated_at      INTEGER NOT NULL DEFAULT (strftime('%s', 'now'))     -- @comment 最后更新时间戳
) STRICT;

CREATE INDEX idx_ts_task_id ON task_sync(task_id);
CREATE INDEX idx_ts_status  ON task_sync(status);


-- ============================================================
-- 多平台同步各平台结果记录表
-- ============================================================
-- @table-comment 多平台同步各平台结果
CREATE TABLE task_sync_result (
    id              INTEGER PRIMARY KEY,
    task_sync_id    INTEGER NOT NULL,                                     -- @comment 关联 task_sync.id
    platform        TEXT    NOT NULL,                                     -- @comment 平台标识
    status          TEXT    NOT NULL DEFAULT 'pending',                   -- @comment 同步结果: success / failed
    error_msg       TEXT    NOT NULL DEFAULT '',                          -- @comment 失败原因
    created_at      INTEGER NOT NULL DEFAULT (strftime('%s', 'now'))     -- @comment 记录创建时间戳
) STRICT;

CREATE INDEX idx_tsr_sync_id  ON task_sync_result(task_sync_id);
CREATE INDEX idx_tsr_platform ON task_sync_result(platform);

-- ============================================================
-- 任务审核记录表
-- ============================================================
-- @table-comment 人工审核记录（审核节点暂停任务流程，审核通过后继续）
CREATE TABLE task_review (
    id              INTEGER PRIMARY KEY,                                   -- @comment 自增主键
    task_id         INTEGER NOT NULL,                                      -- @comment 关联任务 ID
    stage           INTEGER NOT NULL,                                      -- @comment 审核节点状态码: 20(简报)/35(卡片)/40(文章)
    status          TEXT    NOT NULL DEFAULT 'pending',                    -- @comment 审核状态: pending / approved / rejected
    reviewer        TEXT    NOT NULL DEFAULT '',                           -- @comment 审核人标识
    comment         TEXT    NOT NULL DEFAULT '',                           -- @comment 审核意见
    created_at      INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),     -- @comment 创建时间戳
    updated_at      INTEGER NOT NULL DEFAULT (strftime('%s', 'now'))      -- @comment 最后更新时间戳
) STRICT;

CREATE INDEX idx_tr_task   ON task_review(task_id);
CREATE INDEX idx_tr_status ON task_review(status);
CREATE INDEX idx_tr_stage  ON task_review(stage);

COMMIT;

-- ============================================================
-- 常用查询示例（注释，不执行）
-- ============================================================
-- 查询某任务的完整状态历史（含中文标签）:
--   SELECT h.id, s_to.label AS 变更后, h.business_key, h.to_info, h.remark, h.operator,
--          datetime(h.created_at, 'unixepoch', 'localtime') AS 时间
--   FROM task_status_history h
--   LEFT JOIN task_status s_to ON s_to.code = h.to_status
--   WHERE h.task_id = ? ORDER BY h.created_at;

-- 查询当前进行中的任务:
--   SELECT t.id, t.title, s.label AS 状态, t.account
--   FROM task t JOIN task_status s ON s.code = t.status
--   WHERE s.is_terminal = 0 AND t.is_deleted = 0 ORDER BY t.created_at DESC;

-- 查询某任务的所有生图记录:
--   SELECT seq, provider, model, local_path, upload_cdn_url, upload_status
--   FROM task_image WHERE task_id = ? ORDER BY seq;

-- 查询某任务的 LLM 调用总成本:
--   SELECT call_type, COUNT(*) AS 调用次数,
--          SUM(tokens_in + tokens_out) AS 总Token,
--          ROUND(SUM(cost_est), 4) AS 总费用美元
--   FROM llm_call_log WHERE task_id = ? GROUP BY call_type;

-- 查询最近 30 天各 provider 调用量:
--   SELECT provider, call_type, COUNT(*) AS 调用次数,
--          ROUND(SUM(duration_ms)/1000.0, 1) AS 总耗时秒,
--          ROUND(SUM(cost_est), 4) AS 总费用美元
--   FROM llm_call_log
--   WHERE created_at > strftime('%s', 'now') - 2592000
--   GROUP BY provider, call_type ORDER BY 总费用美元 DESC;
