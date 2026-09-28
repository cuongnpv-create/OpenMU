# Dump packet giữa client MuMain và server OpenMU

Đã chạy thật end-to-end. Kết quả mẫu: **351 packet** của một phiên đầy đủ
(login → chọn nhân vật → chat → warp → đi bộ → giết 4 con Spider), giải mã
sạch, opcode tra ra tên qua **513 định nghĩa packet** của OpenMU.

---

## 1. Tại sao `tcpdump` không đủ

Traffic tới **game server** được mã hoá. Client quyết định bằng một heuristic
theo port — `MuMain/src/source/Network/Server/WSclient.cpp:356`:

```cpp
// todo: generally, it's a bad idea to assume a specific port number (range).
const bool isEncrypted = Port > 0xADFF || Port < 0xAD00;
```

| Port | Hex | Mã hoá? |
|---|---|---|
| 44405 (connect server) | `0xAD75` | **không** — nằm trong dải `0xAD00..0xADFF` |
| 55901–55906 (game server) | `0xDA5D`+ | **có** |

Lớp mã hoá (`MuMain/ClientLibrary/ConnectionManager.cs:162-163`):

```csharp
var encryptor = new PipelinedXor32Encryptor(
    new PipelinedSimpleModulusEncryptor(output, PipelinedSimpleModulusEncryptor.DefaultClientKey).Writer);
var decryptor = new PipelinedSimpleModulusDecryptor(input, PipelinedSimpleModulusDecryptor.DefaultClientKey);
```

Tức là **client→server** đi qua Xor32 rồi SimpleModulus; **server→client** chỉ
SimpleModulus. `tcpdump` trên port game server chỉ thấy rác.

> Chú thích của OpenMU: khoá SimpleModulus chưa từng đổi từ trước tới nay, nên
> khoá mặc định Season 6 dùng được cho mọi phiên bản. Riêng khoá Xor32 thì
> Webzen đổi liên tục trong thời GMO.

---

## 2. Giải pháp: proxy MITM dùng chính code OpenMU

`mu-proxy/` là một console app .NET ~200 dòng, tham chiếu thẳng
`MUnique.OpenMU.Network.csproj` của repo OpenMU đã clone. Không tự implement
lại crypto — dùng đúng `PipelinedDecryptor` / `PipelinedEncryptor` mà server
dùng, nên bảo đảm khớp tuyệt đối.

```
client --(plaintext)--> :44305 proxy --> :44405 connect server
                        ^ rewrite gói C1 F4 03 ConnectionInfo
client --(encrypted)--> :56901 proxy --> :55901 game server
```

**Mấu chốt là chọn port cho đúng heuristic ở mục 1:**

- Proxy connect server nghe `44305` = `0xAD11` → **trong** dải → client gửi
  plaintext. Đổi ra ngoài dải là client mã hoá và proxy hỏng.
- Proxy game server nghe `56901` → **ngoài** dải → client mã hoá, đúng như
  game server thật.

Connect server trả về gói `C1 F4 03 ConnectionInfo` bảo client đi đâu tiếp
(`docs/Packets/C1-F4-03-ConnectionInfo_by-server.md`):

```
index 4..19  : IpAddress  (chuỗi ASCII 16 byte, pad \0)
index 20..21 : Port       (short little endian)
```

Proxy sửa gói này tại chỗ để client quay lại proxy thay vì đi thẳng, đồng thời
nhớ endpoint gốc để nối đúng nơi. Log thật:

```
rewrite ConnectionInfo 127.127.127.127:55901 -> 127.0.0.1:56901
```

(`127.127.127.127` là IP loopback do `RESOLVE_IP=loopback` — xem [01 — Dựng server](01-dung-server.md).)

### Chạy

```bash
cd mu-proxy && dotnet build -c Release
dotnet run -c Release --no-build -- \
  --cs-listen 44305 --cs-target 127.0.0.1:44405 \
  --gs-listen 56901 --gs-target 127.0.0.1:55901 \
  --out /tmp/mu-packets.jsonl
```

Rồi trỏ client vào proxy:

```bash
./Main /u127.0.0.1 /p44305
```

Output là JSON Lines, mỗi dòng một packet đã giải mã:

```json
{"ms":63544.1,"ch":"GS","dir":"c2s","len":8,"hex":"C108D4000101AF7D"}
```

> Cần thêm `<PackageReference Include="Microsoft.Extensions.Logging" />`:
> project `Network` của OpenMU chỉ tham chiếu `Logging.Abstractions`, không có
> lớp `LoggerFactory` cụ thể.

---

## 3. Decode: `mu-packet-decode.py`

Đọc JSONL, nạp 4 file XML định nghĩa packet của OpenMU
(`src/Network/Packets/*/*.xml`), tra opcode ra tên và parse từng field.

```bash
./mu-packet-decode.py /tmp/mu-packets.jsonl --openmu ~/OpenMU
./mu-packet-decode.py /tmp/mu-packets.jsonl --openmu ~/OpenMU --stats
./mu-packet-decode.py /tmp/mu-packets.jsonl --openmu ~/OpenMU --fields --grep Hit
./mu-packet-decode.py /tmp/mu-packets.jsonl --openmu ~/OpenMU --hex --channel GS
```

### Cách tách frame

| Byte đầu | Ý nghĩa | Header |
|---|---|---|
| `C1` | thường, length 1 byte | `[C1][len][code][subcode?]` |
| `C2` | thường, length 2 byte **big endian** | `[C2][lenHi][lenLo][code][subcode?]` |
| `C3` | như C1 nhưng phần thân được mã hoá | |
| `C4` | như C2 nhưng phần thân được mã hoá | |

Sau khi proxy giải mã, byte đầu vẫn giữ `C3`/`C4` — nó là *nhãn* cho biết gói
đó có mã hoá trên dây, không phải trạng thái hiện tại của dữ liệu.

Một `Code` có thể ứng với nhiều packet khác nhau. Script phân giải theo thứ tự:
**Direction** (`ClientToServer`/`ServerToClient` lấy từ XML) → khớp `SubCode`
→ khớp đúng `Length` → định nghĩa có `Length` rỗng (độ dài động).

---

## 4. Kết quả thật

### Bắt tay và đăng nhập

```
  33925.7 CS <-- C1 00 01  Hello                        (4B)
  35581.9 CS --> C1 F4 06  ServerListRequest            (4B)
  35583.6 CS <-- C2 F4 06  ServerListResponse           (19B)
  54926.5 CS --> C1 F4 03  ConnectionInfoRequest        (6B)
  54930.7 CS <-- C1 F4 03  ConnectionInfo               (22B)
  54931.5 CS <-- C1 00 01  Hello                        (4B)   <- đã sang game server
  55182.5 GS <-- C1 F1 00  GameServerEntered            (12B)
  55374.8 GS --> C3 F1 01  LoginLongPassword            (60B)
  55584.8 GS <-- C1 F1 01  LoginResponse                (5B)
  55603.1 GS --> C1 F3 00  RequestCharacterList         (5B)
  55674.0 GS <-- C1 F3 00  CharacterList                (228B)
  55872.7 GS --> C1 F3 03  SelectCharacter              (14B)
```

### Vào thế giới — server đẩy một loạt trạng thái

```
  55882.5 GS <-- C3 F3 03  CharacterInformationExtended (92B)
  55882.5 GS <-- C1 F3 50  MasterStatsUpdateExtended    (40B)
  55882.5 GS <-- C2 F3 53  MasterSkillList              (12B)
  55882.5 GS <-- C4 F3 10  CharacterInventory           (371B)
  55882.6 GS <-- C1 F3 30  ApplyKeyConfiguration        (32B)
  55882.6 GS <-- C1 A0     LegacyQuestStateList         (6B)
  55882.6 GS <-- C2 12     AddCharacterToScopeExtended  (54B)
  55882.6 GS <-- C2 13     AddNpcsToScope               (45B)
  55882.7 GS <-- C1 0F     WeatherStatusUpdate          (4B)
```

Cả khối này đến trong **cùng 1 mili-giây** — server gom lại đẩy một lần.

### Chiến đấu, parse ra field

```
 148662.5 GS --> C1 11  HitRequest  (7B)
          . TargetId                     = 616
 148664.2 GS <-- C1 17  ObjectGotKilled  (9B)
          . KilledId                     = 616
          . SkillId                      = 0
          . KillerId                     = 512
 149665.8 GS <-- C1 2F  MoneyDroppedExtended  (12B)
          . IsFreshDrop                  = True
          . Id                           = 4
          . PositionX                    = 196
          . PositionY                    = 145
          . Amount                       = 7
```

`512` là id của nhân vật mình trong scope, `616` là con Spider. Đúng 1.7ms từ
lúc gửi `HitRequest` tới lúc nhận `ObjectGotKilled`.

`ObjectHitExtended` mang cờ Rage Fighter và damage nhiều byte:

```
 145716.8 GS <-- C1 11  ObjectHitExtended  (16B)
          . IsRageFighterStreakHit       = False
          . IsDoubleDamage               = False
          . IsTripleDamage               = False
          . ObjectId                     = 512
          . HealthStatus                 = 250
          . HealthDamage                 = 0
          . ShieldDamage                 = 0
```

Đây chính là chỗ protocol **mở rộng** so với Season 6 gốc: bản `...Extended`
cho damage/HP vượt 16 bit — lý do client này không cắm được vào server MU khác.

### Phân bố của cả phiên

```
  <--   193  ObjectWalked            <- quái đi lại quanh mình, áp đảo băng thông
  <--    24  MapObjectOutOfScope
  -->    20  WalkRequest
  <--    17  CurrentStatsExtended    <- server đẩy HP/mana mỗi ~3 giây
  <--    14  AddNpcsToScope
  <--    13  AvailableChatCommand
  <--    10  ObjectHitExtended
  -->     8  Ping
  -->     4  HitRequest
  <--     4  ObjectGotKilled
  <--     3  MoneyDroppedExtended
```

Quan sát đáng chú ý: **193/351 packet là `ObjectWalked`** — chỉ để đồng bộ
đường đi của quái trong tầm nhìn. Đây là khoản tốn băng thông lớn nhất của
MU và là chỗ tối ưu đầu tiên nếu bạn định làm server đông người.

---

## 5. Áp dụng

- **Thêm packet mới**: sửa XML trong `src/Network/Packets/`, OpenMU tự sinh code
  C# và file markdown trong `docs/Packets/`. Client dùng chung XML đó qua
  `ClientLibrary/*.xslt` → hai bên không bao giờ lệch.
- **Debug desync**: so `WalkRequest` client gửi với `ObjectWalked` server trả.
- **Đo tải**: đếm packet theo loại như mục 4 để biết cần tối ưu chỗ nào.
- **Chống hack**: xem client gửi gì khi làm hành động bất thường.

Không cần proxy nếu chỉ muốn xem traffic **connect server** — nó là plaintext,
`tcpdump -i lo -X port 44405` là đủ.

---

## 6. Giới hạn

- Proxy nối cứng tới **một** game server (`--gs-target`). Đổi map server trong
  lúc chơi (Kalima, Devil Square…) có thể trỏ sai — cần mở rộng để proxy nhiều
  endpoint cùng lúc.
- Chat server (55980) chưa được proxy.
- Xor32 dùng khoá mặc định. Server đổi khoá thì phải sửa
  `PreSeason6NetworkEncryptionFactoryPlugIn.Xor32Key` tương ứng.
