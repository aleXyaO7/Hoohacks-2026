-- Run in Supabase SQL Editor if you want a `category` column on transactions.
-- Without this column, any API code that selects or filters on `category` will fail.

alter table public.transactions
  add column if not exists category text;

comment on column public.transactions.category is 'Optional spending category (e.g. food, transport).';
