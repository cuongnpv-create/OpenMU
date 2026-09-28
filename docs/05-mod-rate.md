# Mod exp rate và drop rate

Đo có đối chứng trên server thật: farm Spider/Budge Dragon ở Lorencia bằng
`test1Dw`, trước và sau khi sửa. Nhân vật lên từ **lv11 → lv16** trong vài phút.

| | Trước | Sau |
|---|---|---|
| Exp mỗi con — Spider | 18 – 26 | 716 – 1238 |
| Exp mỗi con — Budge Dragon | 40 – 55 | 1804 – 2841 |
| Trung bình | 35.9 | 1224 |
| Đồ rơi / con | 0.44 | 1.7 |
| Item (không tính Zen) / con | 0.22 | 1.0 |

Đồ rơi thật trong 7 con sau khi sửa: Apple ×2, Short Sword, Small Axe,
Scroll of Archangel +1, Devil's Key +1 ×2, cùng Zen.

---

## 1. Hai cách sửa

### Admin panel — nên dùng khi sửa tay

| Cần sửa | Trang |
|---|---|
| Exp rate, master exp rate, item drop duration, công thức exp | *Configuration → General*<br>route `edit-config/…GameConfiguration/{id}/hide-collections` |
| Tỉ lệ từng nhóm đồ rơi | *Configuration → Drop item groups*<br>route `edit-config-grid/…DropItemGroup/` |
| Số suất rơi mỗi quái, drop riêng của quái | *Configuration → Monsters*<br>route `edit-config-grid/…MonsterDefinition/` |

### SQL — nên dùng khi script hoá

```bash
./scripts/mu-set-rates.sh show
./scripts/mu-set-rates.sh backup          # BẮT BUỘC làm trước khi sửa
./scripts/mu-set-rates.sh exp 50
./scripts/mu-set-rates.sh drop --items 0.9 --money 0.35 --special-mult 5 --max-drops 3
./scripts/mu-set-rates.sh reload
./scripts/mu-set-rates.sh restore         # trả về mặc định
```

### Đổi rồi phải nạp lại

Config được đọc lúc game server khởi động. Sau khi sửa phải một trong hai:

- Admin panel → *Servers* → **Reload configuration and restart all game servers**
- Hoặc restart hẳn process: `docker restart openmu-startup`

Không nạp lại thì server vẫn chạy với config cũ và bạn sẽ tưởng là sửa không ăn.

---

## 2. Exp rate

Một field duy nhất, `GameConfiguration.ExperienceRate`
(`src/DataModel/Configuration/GameConfiguration.cs:34`), được đọc qua
`GameContext.ExperienceRate` (`src/GameLogic/GameContext.cs:116`).

```sql
UPDATE config."GameConfiguration" SET "ExperienceRate" = 50;
```

`MasterExperienceRate` (dòng 119) là field riêng cho master level — đổi exp
thường **không** kéo theo master exp.

### Bẫy: exp và kinh tế dính chặt vào nhau

`src/GameLogic/DefaultDropGenerator.cs:517`:

```csharp
droppedMoney = (uint)(gainedExperience + BaseMoneyDrop);   // BaseMoneyDrop = 7, dòng 19
```

Tiền rơi **bằng đúng exp nhận được cộng 7**. Đo thật:

| Exp nhận | Zen rơi |
|---|---|
| 18 | 25 |
| 26 | 33 |
| 1002 | 1009 |
| 2841 | 2848 |

Khớp tuyệt đối, cả trước lẫn sau khi đổi rate.

Nghĩa là **không thể chỉnh exp rate mà không thổi phồng nền kinh tế**: exp ×50
thì zen rơi cũng ×50. Nếu định mở server rate cao mà muốn giữ kinh tế cân bằng,
chỗ này phải sửa code (tách hệ số tiền ra khỏi `gainedExperience`), không sửa
được bằng config.

---

## 3. Drop rate

### Mô hình

`DefaultDropGenerator.PartitionDropGroups` (dòng 336) chia mọi nhóm đồ rơi làm
hai loại:

```csharp
if (group.Chance >= 1.0)
    this._guaranteedDropGroups.Add(group);   // LUÔN rơi
else
    this._chanceDropGroups.Add(group);       // bốc theo trọng số
```

Rồi `GenerateDrops` (dòng 273) chạy nhóm guaranteed trước, nhóm chance sau, và
cả hai đều bị giới hạn bởi:

```csharp
var remainingDrops = monster.NumberOfMaximumItemDrops;   // dòng 277
```

Quái thường ở Lorencia có `NumberOfMaximumItemDrops = 1` — mỗi lần chết rơi tối
đa **một** món.

### Cái bẫy 1.0

Cách làm trực giác là "nhân hết chance lên rồi cap ở 1.0". **Đừng.**

Cap ở 1.0 không phải là "tăng tỉ lệ lên tối đa" — nó **chuyển nhóm sang loại
khác**. Lần thử đầu mình nhân tất cả ×20 rồi cap 1.0:

```sql
-- SAI
UPDATE config."DropItemGroup" SET "Chance" = least("Chance"*20, 1.0) WHERE ...;
```

Kết quả: drop item về **0**, chỉ còn toàn Zen. Vì cả nhóm tiền lẫn nhóm item
ngẫu nhiên đều lên đúng 1.0 → cùng thành guaranteed → nhóm tiền chạy trước và
chiếm trọn suất rơi duy nhất.

Nhân chance lên mà đồ rơi **ít đi**. Cap phải là `0.99`, không phải `1.0`.

### Cách đúng

```sql
-- ưu tiên item ngẫu nhiên, hạ tiền xuống để nhường trọng số
UPDATE config."DropItemGroup" SET "Chance" = 0.9
  WHERE "Description" LIKE 'The common drop item group for random items%';
UPDATE config."DropItemGroup" SET "Chance" = 0.35
  WHERE "Description" LIKE 'The common money drop item group%';

-- nhóm item đặc biệt ×5, CAP 0.99 để vẫn nằm trong pool có trọng số
UPDATE config."DropItemGroup" g SET "Chance" = least(g."Chance"*5, 0.99)
  WHERE g."Id" IN (SELECT DISTINCT m."DropItemGroupId"
                   FROM config."GameMapDefinitionDropItemGroup" m)
    AND g."Description" NOT LIKE 'The common%';

-- cho phép rơi nhiều món mỗi con
UPDATE config."MonsterDefinition" SET "NumberOfMaximumItemDrops" = 3
  WHERE "NumberOfMaximumItemDrops" > 0 AND "NumberOfMaximumItemDrops" < 3;
```

### Bẫy NPC

Điều kiện `"NumberOfMaximumItemDrops" > 0` ở câu cuối là bắt buộc. Trong DB mặc
định có **135 dòng `MonsterDefinition` với giá trị 0 — đó là NPC**: Baz The
Vault Keeper, Angela the Supplier, Alliance Item Storage, lính gác, tượng đá…

Viết `WHERE "NumberOfMaximumItemDrops" < 3` là cho cả NPC rơi đồ. Chúng nằm
chung bảng với quái, chỉ phân biệt bằng chính field này.

### Ba nhóm chung có sẵn

```
The common money drop item group (50 % drop chance)               Chance 0.5
The common drop item group for random items (30 % drop chance)    Chance 0.3
The common drop item group for random excellent items (0.01 %)    Chance 0.0001
```

Map Lorencia còn gắn thêm 52 nhóm item đặc biệt (Devil's Key, Scroll of
Archangel, Blood Bone, Old Scroll…) mỗi nhóm chance 0.01. Tổng chance của map
mặc định là 1.244; tất cả được bốc theo trọng số, không phải cộng dồn xác suất.

---

## 4. Vài field khác đáng biết

| Field | Mặc định | Ý nghĩa |
|---|---|---|
| `ItemDropDuration` | `00:01:00` | đồ nằm dưới đất bao lâu trước khi biến mất |
| `ShouldDropMoney` | `true` | tắt hẳn rơi tiền |
| `MaximumItemOptionLevelDrop` | 3 | option tối đa của item rơi ra |
| `ExcellentItemDropLevelDelta` | 25 | chênh lệch level cho phép rơi đồ excellent |
| `MonsterDefinition.NumberOfMaximumItemDrops` | 1 (quái) / 0 (NPC) | số suất rơi mỗi lần chết |

---

## 5. Sao lưu và khôi phục

`mu-set-rates.sh backup` tạo ba bảng trong schema `public`:
`backup_rates`, `backup_drop`, `backup_monster`.

`restore` đổ ngược cả ba về. Script từ chối mọi lệnh sửa nếu chưa có đủ ba bảng
với đúng cột — một bảng cũ thiếu cột sẽ làm `restore` chết giữa chừng và bạn mất
đường lùi.

:::warning
`backup` ghi đè bảng sao lưu bằng trạng thái **hiện tại**. Chạy nó sau khi đã mod
là mất luôn giá trị gốc. Chỉ chạy `backup` một lần, trước khi sửa bất cứ thứ gì.
:::

Nếu lỡ mất: có thể khởi tạo lại DB từ *Setup page* của admin panel, hoặc
`docker compose down -v` rồi dựng lại (mất toàn bộ nhân vật).

---

## 6. Tóm tắt các bẫy

1. **Cap `Chance` ở 1.0 làm drop item tệ đi**, không phải tốt lên — nó biến nhóm
   thành guaranteed và chiếm hết suất rơi. Cap ở `0.99`.
2. **Tiền rơi = exp nhận + 7.** Tăng exp rate là tăng luôn zen theo đúng tỉ lệ.
3. **`NumberOfMaximumItemDrops = 0` là NPC**, đừng nâng lên.
4. **Không nạp lại config thì không có gì thay đổi**, dù SQL báo `UPDATE 1`.
5. `MasterExperienceRate` là field riêng, không đi theo `ExperienceRate`.
