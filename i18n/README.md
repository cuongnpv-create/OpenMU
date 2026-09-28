# Việt hóa OpenMU

Xem [docs/05 — Việt hóa](../docs/05-viet-hoa.md) để hiểu cơ chế và các cái bẫy.
Đây là phần tra cứu nhanh.

## Nội dung

| File | Vai trò |
|---|---|
| `PlayerMessage.vi.resx` | 243 thông báo hệ thống. Sửa ở đây rồi build lại |
| `build-satellite.sh` | Biên dịch `.resx` thành satellite assembly (qua Docker, không cần .NET SDK) |
| `vi/*.resources.dll` | Kết quả biên dịch, mount vào `/app/vi` của container |
| `Dockerfile.vi` | Image OpenMU + `icu-data-full`. **Bắt buộc** — xem bên dưới |
| `docker-compose.local.yml` | Mẫu compose: mount satellite, khóa admin panel vào localhost |
| `glossary.py` | Bảng thuật ngữ dịch tên: `TYPE`, `MTYPE`, `QUAL`, `SKIP`, `OVERRIDE` |
| `render.py` | Sinh bản dịch tên từ bảng trên |

## Bắt buộc: `icu-data-full`

Image `munique/openmu` chỉ có `icu-data-en`, khiến
`CultureInfo.GetCultures()` trả về đúng 5 culture tiếng Anh. Hệ quả là
`Player.cs:290` không map được `LanguageIsoCode='vi'` và **âm thầm** rơi về
tiếng Anh — không log, không lỗi.

```bash
docker build -f Dockerfile.vi -t openmu-vi:latest .
```

Phải chạy lại mỗi lần cập nhật OpenMU.

## Sửa bản dịch

**Thông báo hệ thống** — sửa `PlayerMessage.vi.resx` rồi `./build-satellite.sh`.
Giữ nguyên số lượng và chỉ số placeholder `{0}`, `{1}`; sai là server ném
`FormatException` đúng lúc gửi thông báo cho người chơi.

**Tên item / quái / map** — sửa một dòng trong `glossary.py` là mọi tên dùng từ
đó đổi theo. Luật chung cho kết quả ngượng thì thêm vào `OVERRIDE`:

```python
OVERRIDE = {
    "Guild Master": "Chủ Guild",
}
```

Đừng sửa luật chung để chữa một tên lẻ. Ví dụ thêm luật "bỏ từ chỉ loại thừa"
để chữa `Cherry Blossom Flower Petal` sẽ biến `Dark Soul Armor` thành
`Giáp Dark`, vì `Soul` cũng nằm trong bảng loại.

## Đặt ngôn ngữ cho tài khoản

```sql
UPDATE data."Account" SET "LanguageIsoCode"='vi' WHERE "LoginName"='ten_tk';
```

Không có cách nào để người chơi tự chọn — OpenMU chưa có đường ghi vào cột này.
