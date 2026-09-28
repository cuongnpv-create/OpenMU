# 05 — Việt hóa OpenMU

Mọi số đo dưới đây lấy từ một lần dựng thật: OpenMU image `munique/openmu:latest`
(Alpine 3.23), .NET 10.0.10, PostgreSQL trong Docker, 28/09/2026.

---

## Kết luận trước

OpenMU **có sẵn hạ tầng đa ngôn ngữ**, và nó hoạt động theo **từng người chơi**.
Nhưng có một cái bẫy trong image chính thức khiến nó im lặng không chạy, và một
giới hạn kiến trúc khiến phần lớn chữ trong game không đổi được từ server.

---

## Hai cơ chế, hai nơi lưu

| Loại chữ | Lưu ở đâu | Đổi thế nào |
|---|---|---|
| Tên item, quái, map, skill, quest | Cột trong PostgreSQL, kiểu `LocalizedString` | `UPDATE` thẳng, hiệu lực ngay |
| 243 thông báo hệ thống | `PlayerMessage.resx` biên dịch vào assembly | Satellite assembly, phải build |

### `LocalizedString` — dịch nằm ngay trong cột

Định dạng nối chuỗi, phần đầu là ngôn ngữ trung tính:

```
Dungeon||vi=Hầm Ngục||de=Verlies
```

Bộ tách nằm ở `src/Interfaces/LocalizedString.cs`, khớp theo
`TwoLetterISOLanguageName`. Không khớp thì rơi về phần đầu, nên map chưa dịch
vẫn hiện tiếng Anh bình thường.

Các trường dùng kiểu này: `ItemDefinition.Name`, `MonsterDefinition.Designation`,
`GameMapDefinition.Name`, `Skill.Name`, `QuestDefinition.Name`,
`CharacterClass.Name`, `ItemOptionDefinition.Name`, `WarpInfo.Name` và một số nữa.

### Ngôn ngữ theo từng người chơi

```
Account.LanguageIsoCode  (DataModel/Entities/Account.cs:78, mặc định "en")
  -> Player.Culture      (GameLogic/Player.cs:290-293)
  -> gom người chơi theo culture (GameLogic/GameContext.cs:384)
  -> lấy chữ theo culture đó     (GameLogic/GameContext.cs:410)
```

Hai người chơi online cùng lúc, một `en` một `vi`, nhận hai bản chữ khác nhau
cho cùng một sự kiện.

**Không có đường nào để người chơi tự chọn.** Grep `LanguageIsoCode` toàn source
chỉ ra định nghĩa model, migration, và **một chỗ đọc** ở `Player.cs`. Không có
gói tin lúc đăng nhập, không có lệnh trong game, không có ô sửa trong admin
panel. Phải `UPDATE` thẳng vào DB:

```sql
UPDATE data."Account" SET "LanguageIsoCode"='vi' WHERE "LoginName"='ten_tk';
```

---

## Cái bẫy: image chính thức chỉ có ICU tiếng Anh

Đây là thứ tốn nhiều thời gian nhất, vì nó **hỏng trong im lặng**.

`Player.cs:290-293` ánh xạ mã ngôn ngữ sang culture bằng:

```csharp
CultureInfo.GetCultures(CultureTypes.AllCultures)
    .FirstOrDefault(cu => cu.TwoLetterISOLanguageName == account.LanguageIsoCode
                       || cu.ThreeLetterISOLanguageName == account.LanguageIsoCode)
    ?? CultureInfo.CurrentCulture;
```

Image `munique/openmu` dựa trên Alpine và chỉ cài gói `icu-data-en`. Đo trong
container thật:

```
GetCultures(AllCultures) trả về:  5
    ''   'en'   'en-001'   'en-GB'   'en-US'
```

Không có `vi` → `FirstOrDefault` trả null → rơi về `CurrentCulture` (rỗng, tức
invariant) → **người chơi không bao giờ nhận tiếng Việt**, dù DB ghi `'vi'`.

Điều đánh lừa: `new CultureInfo("vi")` vẫn tạo được bình thường
(`three=vie`, `Vietnamese`). Nên test satellite riêng lẻ vẫn "đạt". Chỉ khi tái
hiện đúng nguyên văn đoạn code trên mới lộ ra.

**Sửa** — `Dockerfile.vi` thêm một dòng:

```dockerfile
FROM munique/openmu:latest
USER root
RUN apk add --no-cache icu-data-full
```

| | Image gốc | Sau khi sửa |
|---|---|---|
| `GetCultures(AllCultures)` | 5 | **870** |
| Có `vi` | không | `vi`, `vi-VN` |
| `Player.Culture` khi iso=`vi` | `''` | `vi` |

Mỗi lần cập nhật OpenMU phải build lại image này, không thì lỗi quay lại.

---

## Giới hạn kiến trúc: tên trong game không đổi được từ server

Server gửi item, quái và map xuống client bằng **mã số**, không phải chữ:

| Thứ | Mã nguồn | Gửi cái gì |
|---|---|---|
| Item | `GameServer/RemoteView/ItemSerializer.cs:49,114` | `Definition.Number`, `Group << 4` |
| Quái/NPC | `GameServer/RemoteView/World/NewNpcsInScopePlugIn.cs:80` | `TypeNumber` |
| Map | `GameServer/RemoteView/World/MapChangePlugIn.cs:50` | `CurrentMap.Number` |

Client tra tên từ dữ liệu của **chính nó**. Nên dịch DB **không** đổi được tên
trong túi đồ, cửa hàng hay thanh map.

Chỗ bản dịch DB thật sự hiện ra là các **thông báo server gửi kèm tên**:

```csharp
// CastleSiege/Actions/CastleSiegeHuntZoneEnterAction.cs:45-47
player.ShowLocalizedBlueMessageAsync(
    nameof(PlayerMessage.NotEnoughMoneyToEnter),
    targetMap.Name.GetTranslation(player.Culture))

// MiniGames/BloodCastleContext.cs:189-191
player.ShowLocalizedGoldenMessageAsync(
    nameof(PlayerMessage.BloodCastleArchangelAquiredMessageFormat),
    args.Picker.Name,
    definition.Name.GetTranslation(player.Culture))
```

Khung câu lấy từ `PlayerMessage.resx`, tên lấy từ DB. Thiếu satellite thì ra câu
lai: *"You don't have enough money to enter **Hầm Ngục**"*.

**Hệ quả với tên item:** client hiển thị tiếng Anh, nên nếu dịch trọn cả tên set
thì người chơi thấy thông báo ghi một đằng, túi đồ ghi một nẻo. Vì vậy quy ước ở
đây là **chỉ dịch từ chỉ loại, giữ nguyên tên set**:

```
Dragon Knight Boots  ->  Giày Dragon Knight
Hades Armor          ->  Giáp Hades
Cape of Emperor      ->  Áo Choàng Emperor
```

Danh từ riêng thuần (`Balrog`, `Bahamut`, `Aegis 1-7`, tên NPC) không dịch.

---

## Độ phủ đạt được

| Bảng | Đã dịch | Giữ nguyên |
|---|---|---|
| Thông báo hệ thống | **243/243** | 0 |
| Item | 620/676 | 56 |
| Map | 61/73 | 12 |
| Quái | 272/468 | 196 |

Assembly trong image hiện tại dùng 196 message key; cả 196 đều đã có bản dịch.
47 key còn lại đến từ source mới hơn image, sẽ tự có tác dụng khi cập nhật.

---

## Cách dùng

```bash
cd i18n
./build-satellite.sh                              # biên dịch .resx -> .dll
docker build -f Dockerfile.vi -t openmu-vi:latest .   # image + icu-data-full
```

Rồi trong compose của OpenMU: dùng image `openmu-vi:latest`, mount
`./i18n/vi:/app/vi:ro`. Xem `docker-compose.local.yml` làm mẫu.

Sinh lại bản dịch tên sau khi sửa `glossary.py`:

```bash
python3 render.py item    < ten-item.txt > item.json
python3 render.py monster < ten-quai.txt > quai.json
```

Script ghi DB theo phần tiếng Anh trước dấu `||` nên chạy lại nhiều lần không bị
nhân đôi hậu tố.

---

## Việc chưa làm được

**Chưa ai xác nhận dấu tiếng Việt render ra sao trong client MU.** Chữ đã đúng ở
DB, đúng qua `ResourceManager`, đúng trong runtime production — nhưng khâu cuối
là font bitmap của client vẽ `ầ`, `ườ`, `Đ`. Nếu ra ô vuông thì phải làm font
trước khi đi tiếp. Cần một client thật mới trả lời được.
