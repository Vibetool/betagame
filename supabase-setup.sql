-- ==============================================================
-- Mini Metro · 简洁地铁模拟 — Supabase 表结构 / 策略 / 触发器
-- ==============================================================
-- 用法:
--   1) 打开 https://app.supabase.com/, 创建一个项目 (免费档)
--   2) 左侧 SQL Editor -> New query -> 把整段粘贴 -> Run
--   3) Authentication -> Providers -> Email 默认就开启的, 想免确认
--      邮箱可以把 "Confirm email" 关掉 (开发期方便)
--   4) Project Settings -> API 复制 Project URL + anon key
--      填到 web/config.js 里
-- ==============================================================

-- 1) 单表存所有用户数据 (一行一个用户)
create table if not exists public.user_save (
  user_id            uuid primary key references auth.users(id) on delete cascade,
  display_name       text not null default '玩家',
  coins              int  not null default 0,
  total_deliveries   int  not null default 0,
  coin_credited      int  not null default 0,  -- 已经折算成金币的累计送达数
  best_score         int  not null default 0,  -- 历史最高单局送达
  best_score_at      timestamptz,
  current_game       jsonb,                    -- 当前未结束一局的快照 (可为 null)
  updated_at         timestamptz not null default now()
);

-- 2) RLS: 用户只能读写自己那一行
alter table public.user_save enable row level security;

drop policy if exists "users select own save"  on public.user_save;
drop policy if exists "users insert own save"  on public.user_save;
drop policy if exists "users update own save"  on public.user_save;

create policy "users select own save"
  on public.user_save for select
  using (auth.uid() = user_id);

create policy "users insert own save"
  on public.user_save for insert
  with check (auth.uid() = user_id);

create policy "users update own save"
  on public.user_save for update
  using (auth.uid() = user_id);

-- 3) updated_at 自动维护
create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end $$;

drop trigger if exists trg_user_save_updated_at on public.user_save;
create trigger trg_user_save_updated_at
  before update on public.user_save
  for each row execute function public.touch_updated_at();

-- 4) 新用户注册后自动创建 user_save (用 email 前缀当默认昵称)
create or replace function public.ensure_user_save()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.user_save (user_id, display_name)
  values (
    new.id,
    coalesce(nullif(split_part(new.email, '@', 1), ''), '玩家')
  )
  on conflict (user_id) do nothing;
  return new;
end $$;

drop trigger if exists trg_auth_user_create on auth.users;
create trigger trg_auth_user_create
  after insert on auth.users
  for each row execute function public.ensure_user_save();

-- 5) 排行榜: 用 RPC 函数对外暴露, 不直接 SELECT 整表, 避免泄漏 user_id
create or replace function public.get_leaderboard(limit_n int default 50)
returns table (
  display_name  text,
  best_score    int,
  best_score_at timestamptz
)
language sql
security definer
set search_path = public
as $$
  select display_name, best_score, best_score_at
    from public.user_save
   where best_score > 0
   order by best_score desc, best_score_at asc nulls last
   limit greatest(1, least(limit_n, 200));
$$;

grant execute on function public.get_leaderboard(int) to anon, authenticated;
