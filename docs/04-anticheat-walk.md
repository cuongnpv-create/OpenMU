# WalkRequest vs ObjectWalked — cơ chế chống speedhack của OpenMU

Phân tích từ packet bắt được thật, đối chiếu với source, rồi **inject packet để
thử phá** và quan sát server phản ứng. Kết quả: phát hiện đúng, ban đúng.

---

## 1. Hai gói tin

### WalkRequest — client gửi (`C1 D4`)

```
[0] C1
[1] len
[2] D4                      <- opcode phụ thuộc NGÔN NGỮ client (xem mục 6)
[3] SourceX                 <- client TỰ KHAI mình đang đứng đâu
[4] SourceY
[5] rotation<<4 | stepCount
[6..] mỗi 4 bit một hướng đi
```

Ví dụ thật: `C1 0A D4 C5 92 28 11 11 22 22`
→ nguồn (197,146), 8 bước, hướng `1,1,1,1,2,2,2,2`.

### ObjectWalkedExtended — server trả (`C1 D4`)

```
[0] C1
[1] len
[2] D4
[3..4] ObjectId (big endian)
[5] SourceX                 <- vị trí server CÔNG NHẬN
[6] SourceY
[7] TargetX                 <- đích server CHẤP NHẬN
[8] TargetY
[9] rotation<<4 | stepCount
```

Ví dụ thật: `C1 0A D4 02 00 C5 92 C9 8A 00`
→ object 512, nguồn (197,146), đích (201,138), stepCount 0.

> **Bẫy khi decode:** `ObjectWalked` và `ObjectWalkedExtended` dùng **chung
> opcode `D4`** và đều là độ dài động. Bản thường không có SourceX/SourceY —
> `TargetX` nằm ở index 5. Bản Extended chèn thêm Source nên Target dời sang
> index 7. Bộ decode ban đầu của mình chọn nhầm bản thường và ra toạ độ vô
> nghĩa. MuMain dùng bản **Extended**.

---

## 2. Hệ toạ độ xoay 45 độ

Đây là chỗ dễ sai nhất. `packetByte + 1` ra enum `Direction`
(`GameServer/DirectionExtensions.ParseAsDirection`), rồi
`GameLogic/DirectionExtensions.CalculateTargetPoint` cho offset:

| byte | Direction | offset (dx, dy) |
|---|---|---|
| 0 | West | (−1, −1) |
| 1 | SouthWest | (0, −1) |
| 2 | South | (+1, −1) |
| 3 | SouthEast | (+1, 0) |
| 4 | East | (+1, +1) |
| 5 | NorthEast | (0, +1) |
| 6 | North | (−1, +1) |
| 7 | NorthWest | (−1, 0) |

"South" là `(+1, −1)` chứ không phải `(0, +1)` — lưới game xoay 45° so với lưới
toạ độ. Kiểm chứng: nguồn (197,146) + `[1,1,1,1,2,2,2,2]` = **(201,138)**, khớp
đúng `TargetX/TargetY` server trả về.

---

## 3. Server xử lý thế nào

Luồng: `CharacterWalkBaseHandlerPlugIn` → `Player.WalkToAsync` →
`PlayerMovement.WalkToAsync`.

Handler **không kiểm tra gì cả** — nó lấy thẳng `SourceX/SourceY` client khai
làm điểm xuất phát:

```csharp
WalkRequest request = packet;
await this.WalkAsync(player, request, new Point(request.SourceX, request.SourceY));
```

Kiểm tra nằm hết ở `PlayerMovement.WalkToAsync`, theo thứ tự:

1. **Trạng thái**: `IsFrozen` / `IsStunned` / `IsAsleep` → bỏ qua.
2. **`_walker.StopAsync()`** — huỷ đường đi đang chạy.
3. **`IsWalkRequestValidAsync`** → gồm hai tầng (mục 4).
4. **`GetWalkableStepCount`** — duyệt từng bước trên `terrain.WalkMap`.
   Bước đầu bị chặn → resync. Bước sau bị chặn → **cắt ngắn đường đi** tới ô
   cuối cùng đi được.
5. `InitializeWalkToAsync` + `StartWalkAsync` — server **tự đi từng bước** theo
   `StepDelay`, không phải client quyết.

Điểm cốt lõi: **vị trí là của server**. Client chỉ đề xuất.

Quan sát thực tế trong dump — client khai (156,126) nhưng server trả
`src=(155,126)`: client đang chạy trước server 1 ô, nằm trong dung sai nên được
chấp nhận, và server dùng vị trí của chính nó.

Và `stepCount` trong ObjectWalkedExtended **luôn bằng 0** (0/236 gói có khác 0)
vì `SendWalkDirections` không được bật ở đâu cả — server không echo lại đường
đi, client tự biết.

---

## 4. Hai tầng chống cheat

### Tầng 1 — `SpeedHackDetectPlugIn.WalkCheatCheckAsync`

Không đo quãng đường đi được, mà đo **khoảng cách giữa các điểm xuất phát của
những WalkRequest liên tiếp** so với thời gian trôi qua:

```
RecentWalks: hàng đợi 5 phần tử {time, startPoint}
  - đang ở safezone            -> xoá sạch
  - cách lần trước > 2 giây    -> xoá sạch
  - < 3 phần tử                -> không kiểm tra

cumulativeTiles = tổng khoảng cách Chebyshev giữa các startPoint liên tiếp
scaling         = stepDelay / 300
checkStepDelay  = max(min(50, stepDelay), stepDelay - 50*scaling)
expected        = cumulativeTiles * checkStepDelay
deficit         = expected - elapsed
tolerance       = 900 * scaling

deficit > tolerance  =>  SPEEDHACK
```

Số đo thật của nhân vật test (Blade Knight lv400, `MovementSpeed` = 19):

| Đại lượng | Giá trị |
|---|---|
| `StepDelay` = 4000 / speed | **210.5 ms** |
| `scaling` = 210.5 / 300 | 0.702 |
| `checkStepDelay` | **175.4 ms** |
| `tolerance` = 900 × 0.702 | **631.6 ms** |

### Tầng 2 — `MaxAllowedWalkStartOffset`

```csharp
var startOffset = startPoint.EuclideanDistanceTo(currentPosition);
if (startOffset <= maxAllowedWalkStartOffset)   // mặc định 5
    return true;
// ngược lại: reset state + ResynchronizeClientAsync() -> rubberband
```

Dung sai 5 ô là để bù độ trễ mạng: client luôn chạy trước server một chút.

---

## 5. Thử phá — kết quả thật

Thêm chế độ `--speedhack N` vào proxy: mỗi khi client gửi WalkRequest, proxy
gửi thêm N bản sao cách nhau 20ms, mỗi bản dịch `SourceX` thêm 4 ô về đông.

```
  85600.5  src=(159,126) steps=13  goc tu client
  85620.8  src=(163,126) steps=13  INJECT #1
  85642.5  src=(167,126) steps=13  INJECT #2
  85663.9  src=(171,126) steps=13  INJECT #3
```

Server phản ứng ngay:

```
[Warning] Speedhack detected on walk for player "test400Dk":
          traveled 8 tiles in 40.5591ms (expected at least 1403.5086ms).
          Deficit: 1362.9495ms.
[Warning] WalkToAsync: Player requested to walk from "230, 129",
          but it's currently at "221, 129" (offset 9 > 5). Resynchronizing client.
```

Kiểm chứng phép tính: `1403.5086 / 8 = 175.44ms` = đúng `checkStepDelay` tính ở
mục 4. Deficit 1363ms > tolerance 632ms → bắt.

### Cheat có ăn được gì không?

Có, nhưng ít và không lâu. Đọc vị trí server trong log:

```
15:38:32.199  (221,129)
15:38:35.235  (244,130)
```

23 ô trong 3.04 giây = **7.6 ô/giây**, so với tốc độ hợp lệ 1/0.2105 =
**4.75 ô/giây**. Tức nhanh hơn khoảng **1.6 lần** — không phải teleport, vì
server vẫn tự đi từng bước theo `StepDelay`. Lợi thế đến từ việc lạm dụng dung
sai 5 ô ở mỗi request, không phải từ việc nhảy thẳng tới đích.

### Thang leo trừng phạt

```
Speedhack detected  ->  RecordViolationAsync
  - debounce 5 giây (nhiều lần trong 5s chỉ tính 1 cảnh báo)
  - cảnh báo <= MaxWarnings(3): hiện chữ xanh trong game
  - cảnh báo  > MaxWarnings(3): AutoBan + DisconnectOnViolation
```

Log thật:

```
Total warnings in last hour: 1
Total warnings in last hour: 2
Total warnings in last hour: 3
Total warnings in last hour: 4
[Error] Player "test400Dk" exceeded speedhack warning limit.
        Banning account "test400" and disconnecting.
```

Kiểm tra DB: `Account.State` = **4** (`AccountState.Banned`), client bị đá ra.
Mình đã `update ... set "State"=0` để trả account test về bình thường sau thí
nghiệm.

Tổng thời gian từ lúc bắt đầu cheat tới lúc bị ban: **khoảng 55 giây**.

---

## 6. Nhận xét

**Điểm mạnh**

- Vị trí do server quyết, client chỉ đề xuất → không teleport được.
- `_walker.StopAsync()` ở đầu mỗi request nghĩa là spam WalkRequest sẽ **huỷ**
  đường đi đang chạy. Spam càng nhiều càng dễ tự dẫm chân mình.
- Địa hình kiểm tra từng bước, đường đi bị cắt ngắn chứ không bị từ chối cả gói
  → người chơi lag không bị kẹt cứng.

**Điểm yếu**

- Hàng đợi bị **xoá sạch nếu 2 request cách nhau > 2 giây**. Cheat nào bắn 2
  request nhanh rồi nghỉ > 2 giây sẽ không bao giờ đủ 3 phần tử để bị kiểm tra.
- Vào **safezone là xoá state**. Ra vào town liên tục cũng reset được.
- Kiểm tra dựa trên `startPoint` **do client khai**, không phải vị trí server.
  Cheat khai điểm xuất phát đứng yên (lặp lại toạ độ cũ) thì `cumulativeTiles`
  = 0 và không bị kiểm tra — tuy nhiên khi đó tầng 2 sẽ rubberband.
- Dung sai 5 ô là khoảng "ăn gian" hợp pháp ở mỗi request; đó chính là chỗ thí
  nghiệm trên khai thác để đạt 1.6×.
- `AutoBan = true` mặc định cộng với `MaxWarnings = 3` khá gắt cho server công
  cộng — người chơi mạng tệ có thể dính oan. Chú thích trong source cũng nói
  rõ là đã phải loại `OfflinePlayer` (MU Helper) ra khỏi kiểm tra vì hay báo
  nhầm, mà hình phạt lại là ban vĩnh viễn.

**Muốn siết thì sửa ở đâu**

`SpeedHackDetectConfiguration` — chỉnh qua admin panel, không cần build lại:
`WalkSpeedToleranceMs` (900), `MaxAllowedWalkStartOffset` (5), `MaxWarnings`
(3), `AlertDebounceSeconds` (5), `AutoBan`, `DisconnectOnViolation`.

Muốn bịt lỗ hổng "nghỉ 2 giây": bỏ hoặc nới `HISTORY_RESET_SECONDS`, và cộng
dồn vi phạm theo thời gian dài hơn thay vì chỉ 5 mẫu gần nhất.

---

## 7. Opcode phụ thuộc ngôn ngữ

Walk không phải opcode duy nhất đổi theo `ClientVersion.Language`. Có ít nhất
ba, và **cách gom nhóm tiếng Việt khác nhau ở từng cái** — đây là chỗ dễ sai
nhất khi decode dump của client bản Việt.

| Ngôn ngữ | Walk<br>`ObjectMovedPlugIn:123` | Instant move<br>`ObjectMovedPlugIn:211` | Show hit<br>`ShowHitPlugIn:85` |
|---|---|---|---|
| English | `0xD4` | `0x15` | `0x11` |
| **Vietnamese** | **`0xD9`** | **`0x15`** | **`0xDC`** |
| Chinese | `0xD9` | `0xD7` | `0xD0` |
| Korean | `0xD3` | `0xD7` | `0xDF` |
| Japanese | `0x1D` | `0xDC` | `0xD6` |
| Thai | `0xD7` | `0xD9` | — |
| Filipino | `0xDD` | `0xD6` | `0xDF` |
| Season 0 / < 1 | `0x10` | `0x11` | `0x15` |

Đọc theo hàng tiếng Việt thì thấy ngay cái bẫy:

- **Walk** — Việt đi chung với **Trung** (`0xD9`)
- **Instant move** — Việt đi chung với **Anh** (`0x15`); Trung là `0xD7`
- **Show hit** — Việt **đứng một mình** (`0xDC`)

Nên quy tắc "bản Việt giống bản Trung" chỉ đúng cho walk. Suy rộng ra hai
opcode kia là decode sai.

Thêm một cái bẫy nữa: `0xD9` vừa là walk của Việt/Trung, vừa là instant move
của Thái. Cùng một byte, ngữ cảnh khác nhau — decode mà không biết trước ngôn
ngữ client thì nhầm là chuyện sớm muộn.

Đây là cách Webzen làm khó người viết bot/emulator ngày xưa.

> Lưu ý: `ClientVersion.Language` (bản build của client, quyết định opcode) hoàn
> toàn độc lập với `Account.LanguageIsoCode` (ngôn ngữ server viết thông báo).
> Xem [05 — Việt hóa](05-viet-hoa.md).

---

## 8. File kèm

| File | Nội dung |
|---|---|
| [`scripts/mu-walk-analyze.py`](../scripts/mu-walk-analyze.py) | ghép cặp WalkRequest ↔ ObjectWalkedExtended, tái hiện phép tính của plugin |
| [`samples/mu-walk-analysis.txt`](../samples/mu-walk-analysis.txt) | kết quả chạy trên cả phiên bình thường lẫn phiên inject |
| [`samples/mu-server-anticheat.log`](../samples/mu-server-anticheat.log) | log gốc phía server: phát hiện, rubberband, cảnh báo, ban |
| [`samples/mu-packets-speedhack.jsonl`](../samples/mu-packets-speedhack.jsonl) | dump thô phiên inject |
| [`mu-proxy/Program.cs`](../mu-proxy/Program.cs) | proxy, đã thêm `--speedhack N` |
