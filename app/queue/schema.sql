CREATE TABLE IF NOT EXISTS manifests (
  source_id TEXT NOT NULL,
  source_version TEXT NOT NULL,
  manifest_json JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (source_id, source_version)
);

CREATE TABLE IF NOT EXISTS jobs (
  job_id UUID PRIMARY KEY,
  job_type TEXT NOT NULL,
  lane TEXT NOT NULL,
  status TEXT NOT NULL,
  source_id TEXT NOT NULL,
  source_version TEXT NOT NULL,
  attempts INT NOT NULL DEFAULT 0,
  next_run_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  locked_until TIMESTAMPTZ,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_lane ON jobs(status, lane);
CREATE INDEX IF NOT EXISTS idx_jobs_next_run ON jobs(next_run_at);

CREATE TABLE IF NOT EXISTS run_log (
  run_id UUID PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  lane TEXT NOT NULL,
  component TEXT NOT NULL,
  model TEXT,
  input_json JSONB,
  output_json JSONB,
  error TEXT
);

CREATE TABLE IF NOT EXISTS memory_items (
  memory_id TEXT PRIMARY KEY,
  memory_type TEXT NOT NULL,
  text TEXT NOT NULL,
  topics JSONB,
  entities JSONB,
  source_refs JSONB,
  importance DOUBLE PRECISION NOT NULL DEFAULT 0.5,
  confidence DOUBLE PRECISION NOT NULL DEFAULT 0.7,
  access_count INT NOT NULL DEFAULT 0,
  last_accessed_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ,
  pinned_until TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_memory_type_created ON memory_items(memory_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_expires ON memory_items(expires_at);

CREATE TABLE IF NOT EXISTS embeddings (
  doc_id TEXT NOT NULL,
  segment_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  source_version TEXT NOT NULL,
  text TEXT NOT NULL,
  text_hash TEXT NOT NULL,
  embedding JSONB NOT NULL,
  start_ms BIGINT,
  end_ms BIGINT,
  speaker TEXT,
  source_refs JSONB,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (doc_id, segment_id)
);
