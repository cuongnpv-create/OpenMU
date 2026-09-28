#!/usr/bin/env bash
# Chỉnh exp rate / drop rate của OpenMU qua SQL, kèm sao lưu và khôi phục.
#
# Dùng khi muốn script hoá. Nếu chỉ sửa tay một lần thì admin panel
# (Configuration -> General / Drop item groups) tiện hơn — xem docs/05-mod-rate.md
#
#   ./mu-set-rates.sh show
#   ./mu-set-rates.sh backup
#   ./mu-set-rates.sh exp 50
#   ./mu-set-rates.sh drop --items 0.9 --money 0.35 --special-mult 5 --max-drops 3
#   ./mu-set-rates.sh restore
#   ./mu-set-rates.sh reload
set -euo pipefail

DB_CONTAINER="${DB_CONTAINER:-database}"
DB_USER="${DB_USER:-postgres}"
DB_NAME="${DB_NAME:-openmu}"
DB_PW="${DB_PW:-admin}"
APP_CONTAINER="${APP_CONTAINER:-openmu-startup}"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mLOI: %s\033[0m\n' "$*" >&2; exit 1; }

psql_() { docker exec -e PGPASSWORD="$DB_PW" "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" "$@"; }

docker ps --format '{{.Names}}' | grep -qx "$DB_CONTAINER" || die "khong thay container DB '$DB_CONTAINER'"

cmd_show() {
  say "Rate hien tai"
  psql_ -c 'select "ExperienceRate", "MasterExperienceRate", "ItemDropDuration",
                   "ShouldDropMoney", "MaximumItemOptionLevelDrop"
            from config."GameConfiguration";'
  say "Hai drop group quan trong nhat"
  psql_ -c $'select "Description", "Chance" from config."DropItemGroup"
             where "Description" like \'The common%\' order by "Chance" desc;'
  say "So suat roi moi quai (NumberOfMaximumItemDrops)"
  psql_ -c 'select "NumberOfMaximumItemDrops" as suat, count(*) as so_quai
            from config."MonsterDefinition" group by 1 order by 1;'
  if has_backup; then
    say "Da co ban sao luu day du (backup_rates, backup_drop, backup_monster)"
  else
    say "CHUA co ban sao luu hop le — chay './mu-set-rates.sh backup' truoc khi sua"
  fi
}

cmd_backup() {
  say "Sao luu gia tri goc"
  psql_ -c 'drop table if exists public.backup_rates;
            create table public.backup_rates as
              select "Id","ExperienceRate","MasterExperienceRate" from config."GameConfiguration";'
  psql_ -c 'drop table if exists public.backup_drop;
            create table public.backup_drop as
              select "Id","Chance" from config."DropItemGroup";'
  psql_ -c 'drop table if exists public.backup_monster;
            create table public.backup_monster as
              select "Id","NumberOfMaximumItemDrops" from config."MonsterDefinition";'
  say "Xong. Khoi phuc bat cu luc nao bang './mu-set-rates.sh restore'"
}

has_backup() {
  # Cả ba bảng phải có, và backup_rates phải đúng cột — một bảng cũ thiếu cột
  # sẽ làm 'restore' chết giữa chừng.
  psql_ -tAc "select count(*) from information_schema.tables
              where table_schema='public'
                and table_name in ('backup_rates','backup_drop','backup_monster');" \
    | tr -d ' ' | grep -qx 3 || return 1
  psql_ -tAc "select count(*) from information_schema.columns
              where table_schema='public' and table_name='backup_rates'
                and column_name in ('Id','ExperienceRate','MasterExperienceRate');" \
    | tr -d ' ' | grep -qx 3
}

require_backup() {
  has_backup || die "chua sao luu day du. Chay './mu-set-rates.sh backup' truoc."
}

cmd_exp() {
  local rate="${1:?can mot so, vi du: exp 50}"
  require_backup
  say "ExperienceRate -> $rate"
  psql_ -c "update config.\"GameConfiguration\" set \"ExperienceRate\"=$rate;"
  cat <<EOF

  LUU Y: tien roi duoc tinh bang 'exp nhan duoc + 7'
  (DefaultDropGenerator.cs: droppedMoney = gainedExperience + BaseMoneyDrop).
  Tang exp rate se tang zen roi theo dung ty le. Xem docs/05-mod-rate.md.
EOF
}

cmd_drop() {
  local items=0.9 money=0.35 mult=5 maxdrops=3
  while [ $# -gt 0 ]; do
    case "$1" in
      --items)         items="$2"; shift 2 ;;
      --money)         money="$2"; shift 2 ;;
      --special-mult)  mult="$2";  shift 2 ;;
      --max-drops)     maxdrops="$2"; shift 2 ;;
      *) die "tham so la: $1" ;;
    esac
  done
  require_backup

  # Bat buoc duoi 1.0: Chance >= 1.0 chuyen group sang nhom "guaranteed"
  # (DefaultDropGenerator.PartitionDropGroups) va se chiem het suat roi.
  for v in "$items" "$money"; do
    awk -v x="$v" 'BEGIN{ if (x+0 >= 1.0 || x+0 <= 0) exit 1 }' \
      || die "chance phai nam trong khoang (0, 1.0) — nhan duoc '$v'. Doc muc 'Cai bay 1.0' trong docs/05-mod-rate.md"
  done

  say "Drop: items=$items money=$money special x$mult maxDrops=$maxdrops"
  psql_ -c "update config.\"DropItemGroup\" set \"Chance\"=$items
            where \"Description\" like 'The common drop item group for random items%';"
  psql_ -c "update config.\"DropItemGroup\" set \"Chance\"=$money
            where \"Description\" like 'The common money drop item group%';"
  psql_ -c "update config.\"DropItemGroup\" g set \"Chance\"=least(g.\"Chance\"*$mult, 0.99)
            where g.\"Id\" in (select distinct m.\"DropItemGroupId\"
                               from config.\"GameMapDefinitionDropItemGroup\" m)
              and g.\"Description\" not like 'The common%';"
  # CHI nang quai von da co suat roi. NumberOfMaximumItemDrops = 0 la NPC
  # (Baz The Vault Keeper, Angela the Supplier, linh gac, tuong da...) — de
  # nguyen, khong thi NPC cung roi do.
  psql_ -c "update config.\"MonsterDefinition\" set \"NumberOfMaximumItemDrops\"=$maxdrops
            where \"NumberOfMaximumItemDrops\" > 0 and \"NumberOfMaximumItemDrops\" < $maxdrops;"
}

cmd_restore() {
  require_backup
  say "Khoi phuc gia tri goc"
  psql_ -c 'update config."GameConfiguration" g
              set "ExperienceRate"=b."ExperienceRate", "MasterExperienceRate"=b."MasterExperienceRate"
              from public.backup_rates b where b."Id"=g."Id";'
  psql_ -c 'update config."DropItemGroup" g set "Chance"=b."Chance"
              from public.backup_drop b where b."Id"=g."Id";'
  psql_ -c 'update config."MonsterDefinition" m set "NumberOfMaximumItemDrops"=b."NumberOfMaximumItemDrops"
              from public.backup_monster b where b."Id"=m."Id";'
}

cmd_reload() {
  say "Khoi dong lai game server de nap config"
  docker restart "$APP_CONTAINER" >/dev/null
  for i in $(seq 1 40); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --noproxy localhost http://localhost/ 2>/dev/null || echo 000)
    [ "$code" = "200" ] && { echo "  server len sau $((i*5))s"; return 0; }
    sleep 5
  done
  die "server khong len — xem 'docker logs $APP_CONTAINER'"
}

case "${1:-show}" in
  show)    cmd_show ;;
  backup)  cmd_backup ;;
  exp)     shift; cmd_exp "$@" ;;
  drop)    shift; cmd_drop "$@" ;;
  restore) cmd_restore ;;
  reload)  cmd_reload ;;
  *) die "lenh khong biet: $1 (show|backup|exp|drop|restore|reload)" ;;
esac
