--
-- 预约批次、兑现、签核日期与依据版本（ORM create_all 的 DDL 留档）
--
CREATE TABLE IF NOT EXISTS public.branch_states (
    branch character varying(30) NOT NULL,
    revision integer NOT NULL DEFAULT 0,
    CONSTRAINT branch_states_pkey PRIMARY KEY (branch)
);

CREATE TABLE IF NOT EXISTS public.appointment_batches (
    id serial PRIMARY KEY,
    branch character varying(30) NOT NULL,
    service_day character varying(10) NOT NULL,
    quantity integer NOT NULL,
    cancelled integer NOT NULL DEFAULT 0,
    fulfilled integer NOT NULL DEFAULT 0,
    moved_out integer NOT NULL DEFAULT 0,
    note text DEFAULT '',
    rescheduled_from integer,
    created character varying(40) DEFAULT '',
    updated character varying(40) DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_appointment_batches_branch ON public.appointment_batches (branch);
CREATE INDEX IF NOT EXISTS ix_appointment_batches_service_day ON public.appointment_batches (service_day);

CREATE TABLE IF NOT EXISTS public.fulfilments (
    id serial PRIMARY KEY,
    batch_id integer NOT NULL REFERENCES public.appointment_batches(id),
    branch character varying(30) NOT NULL,
    day character varying(10) NOT NULL,
    quantity integer NOT NULL,
    note text DEFAULT '',
    created character varying(40) DEFAULT '',
    CONSTRAINT uq_fulfilment_batch_day UNIQUE (batch_id, day)
);
CREATE INDEX IF NOT EXISTS ix_fulfilments_batch_id ON public.fulfilments (batch_id);
CREATE INDEX IF NOT EXISTS ix_fulfilments_branch ON public.fulfilments (branch);
CREATE INDEX IF NOT EXISTS ix_fulfilments_day ON public.fulfilments (day);

CREATE TABLE IF NOT EXISTS public.appointment_ops (
    id serial PRIMARY KEY,
    request_id character varying(80) NOT NULL UNIQUE,
    branch character varying(30) NOT NULL,
    kind character varying(20) NOT NULL,
    result json,
    created character varying(40) DEFAULT ''
);

CREATE TABLE IF NOT EXISTS public.approved_days (
    id serial PRIMARY KEY,
    branch character varying(30) NOT NULL,
    day character varying(10) NOT NULL,
    staffing_id integer NOT NULL REFERENCES public.staffings(id),
    actor character varying(100) DEFAULT '',
    created character varying(40) DEFAULT '',
    CONSTRAINT uq_approved_branch_day UNIQUE (branch, day)
);

ALTER TABLE public.forecast_runs ADD COLUMN IF NOT EXISTS revision integer DEFAULT 0;
ALTER TABLE public.staffings ADD COLUMN IF NOT EXISTS branch character varying(30);
ALTER TABLE public.staffings ADD COLUMN IF NOT EXISTS revision integer DEFAULT 0;
ALTER TABLE public.staffings ADD COLUMN IF NOT EXISTS basis json;
ALTER TABLE public.staffings ADD COLUMN IF NOT EXISTS approved_by character varying(100) DEFAULT '';
ALTER TABLE public.staffings ADD COLUMN IF NOT EXISTS approved_at character varying(40) DEFAULT '';
ALTER TABLE public.staffings ADD COLUMN IF NOT EXISTS invalid_reason text DEFAULT '';
