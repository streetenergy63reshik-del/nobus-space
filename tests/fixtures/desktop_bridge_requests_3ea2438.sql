CREATE TABLE IF NOT EXISTS desktop_bridge_requests (
    request_id TEXT PRIMARY KEY,
    ingress_key TEXT NOT NULL UNIQUE,
    tenant_id TEXT NOT NULL,
    author_user_id INTEGER NOT NULL CHECK(author_user_id>0),
    author_identity TEXT NOT NULL,
    chat_id INTEGER NOT NULL CHECK(chat_id!=0),
    topic_id INTEGER CHECK(topic_id>0),
    source_message_id INTEGER NOT NULL CHECK(source_message_id>0),
    operation TEXT NOT NULL CHECK(operation IN ('create','continue','redeliver')),
    project_name TEXT,
    desktop_thread_id TEXT,
    desktop_turn_id TEXT,
    client_message_id TEXT,
    status TEXT NOT NULL CHECK(status IN (
        'received','needs_target','needs_voice_confirmation','dispatching','running',
        'waiting_author','waiting_owner','execution_completed','delivering','delivered',
        'waiting_pc','unknown_dispatch','delivery_partial','delivery_unknown','failed','cancelled'
    )),
    payload_digest TEXT NOT NULL,
    payload BLOB NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
