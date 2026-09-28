# -*- coding: utf-8 -*-
# TYPE: tu chi LOAI -> thanh danh tu dung dau trong tieng Viet
TYPE = {
 "Armor":"Giáp","Helm":"Mũ","Helmet":"Mũ","Pants":"Quần","Gloves":"Găng","Boots":"Giày",
 "Shield":"Khiên","Sword":"Kiếm","Blade":"Đao","Axe":"Rìu","Mace":"Chùy","Staff":"Gậy Phép",
 "Stick":"Gậy","Scepter":"Trượng","Bow":"Cung","Crossbow":"Nỏ","Ring":"Nhẫn","Pendant":"Dây Chuyền",
 "Potion":"Bình","Scroll":"Cuộn Phép","Parchment":"Sách Da","Jewel":"Ngọc","Orb":"Ngọc Phép",
 "Wing":"Cánh","Wings":"Cánh","Mask":"Mặt Nạ","Box":"Hộp","Sphere":"Cầu","Seed":"Hạt",
 "Gemstone":"Đá Quý","Stone":"Đá","Feather":"Lông Vũ","Horn":"Sừng","Map":"Bản Đồ",
 "Key":"Chìa Khóa","Invisibility":"Tàng Hình","Cloak":"Áo Choàng","Fruits":"Quả",
 "Dagger":"Dao Găm","Spear":"Thương","Scythe":"Lưỡi Hái","Hammer":"Búa","Katana":"Kiếm Nhật",
 "Rapier":"Kiếm Mảnh","Lance":"Thương Dài","Bracelet":"Vòng Tay","Chest":"Rương","Bag":"Túi",
}
# QUALIFIER: tinh tu chung -> dich, dat o CUOI
QUAL = {
 "Large":"Lớn","Small":"Nhỏ","Medium":"Vừa","Golden":"Vàng","Silver":"Bạc","Bronze":"Đồng",
 "Ancient":"Cổ","Broken":"Vỡ","Packed":"Bó","Blessed":"Ban Phước","Complete":"Hoàn Chỉnh",
}
# Tu chi loai cua QUAI (thuong dung dau trong tieng Viet)
MTYPE = {
 "Skeleton":"Bộ Xương","Soldier":"Lính","Knight":"Hiệp Sĩ","Warrior":"Chiến Binh",
 "Archer":"Cung Thủ","Giant":"Khổng Lồ","Golem":"Golem","Statue":"Tượng","Gate":"Cổng",
 "Guard":"Lính Gác","Trap":"Bẫy","Angel":"Thiên Thần","Queen":"Nữ Hoàng","Chief":"Thủ Lĩnh",
 "Centurion":"Bách Phu Trưởng","Merchant":"Thương Nhân","Wolf":"Sói","Skull":"Đầu Lâu",
 "Ogre":"Quỷ Khổng Lồ","Goblin":"Yêu Tinh","Spider":"Nhện","Worm":"Sâu","Bat":"Dơi",
 "Tree":"Cây","Butterfly":"Bướm","Scorpion":"Bọ Cạp","Dragon":"Rồng","Witch":"Phù Thủy",
 "Wizard":"Pháp Sư","Hunter":"Thợ Săn","Assassin":"Sát Thủ","Rogue":"Đạo Tặc",
 "Guardian":"Vệ Binh","Instructor":"Huấn Luyện Viên","Trainee":"Tân Binh","Researcher":"Nhà Nghiên Cứu",
 "Werewolf":"Người Sói","Shadow":"Bóng Ma","Ghost":"Hồn Ma","Lizard":"Thằn Lằn",
}

TYPE.update({
 "Cape":"Áo Choàng","Book":"Sách","Claw":"Vuốt","Bone":"Xương","Wine":"Rượu","Star":"Ngôi Sao",
 "Petal":"Cánh Hoa","Cake":"Bánh","Flower":"Hoa","Arquebus":"Súng Hỏa Mai","Berdysh":"Rìu Chiến",
 "Falchion":"Đao Cong","Flail":"Chùy Xích","Flamberge":"Kiếm Lượn","Gladius":"Đoản Kiếm",
 "Halberd":"Kích","Buckler":"Khiên Tròn","Arrows":"Mũi Tên","Bolt":"Mũi Nỏ","Antidote":"Thuốc Giải",
 "Apple":"Táo","Ale":"Bia","Firecracker":"Pháo","Ticket":"Vé","Medal":"Huy Chương",
 "Elixir":"Tiên Dược","Talisman":"Bùa","Charm":"Bùa Hộ Mệnh","Coin":"Đồng Xu","Card":"Thẻ",
 "Bless":"Phước Lành","Soul":"Linh Hồn","Life":"Sinh Mệnh","Chaos":"Hỗn Mang",
})
MTYPE.update({
 "Tower":"Tháp","Scout":"Trinh Sát","Fighter":"Đấu Sĩ","Rider":"Kỵ Sĩ","Monster":"Quái Vật",
 "Slaughterer":"Đồ Tể","Keeper":"Người Giữ","Storage":"Kho","Crust":"Giáp Xác","Hound":"Chó Săn",
 "Serpent":"Mãng Xà","Beast":"Dã Thú","Demon":"Ác Quỷ","Devil":"Quỷ","Orc":"Orc","Imp":"Tiểu Quỷ",
 "Mage":"Pháp Sư","Priest":"Tư Tế","Lord":"Chúa Tể","King":"Vua","Master":"Chưởng Môn",
})
SKIP = {"of", "the", "The", "de", "a"}

# Elite la tinh tu bo nghia, khong phai loai quai -> dat cuoi: "Elite Yeti" -> "Yeti Tinh Nhue"
QUAL.update({"Elite":"Tinh Nhuệ"})

# Ngoai le tuong minh: thang tay luat chung. Sua o day khi luat cho ket qua nguong.
OVERRIDE = {
 "Guild Master": "Chủ Guild",
 "Cherry Blossom Flower Petal": "Cánh Hoa Cherry Blossom",
}
