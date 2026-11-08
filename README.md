# vntrans — Bộ công cụ Việt hoá game

Trích xuất toàn bộ chữ trong game → dịch sang tiếng Việt (bằng Claude AI, bằng tay, hoặc kết hợp) → ghi ngược vào game.
Mã điều khiển của game (`\C[2]`, `\N[1]`, `{b}`, `[name]`, `%d`, `<color>`...) được tự động bảo vệ để không bị hỏng.

| Engine / định dạng | Adapter | Tự nhận diện |
|---|---|---|
| RPG Maker MV / MZ (`data/*.json`) | `rpgmaker` | ✔ |
| Ren'Py (`game/tl/<ngôn ngữ>/*.rpy`) | `renpy` | ✔ |
| gettext `.po` (Godot, game indie, mod…) | `po` | ✔ |
| Unity + XUnity.AutoTranslator (`BepInEx/Translation/.../Text/*.txt`) | `xunity` | ✔ |
| Bảng CSV/TSV có cột ngôn ngữ (Godot CSV, Unity Localization, I2…) | `csv` | dùng `--adapter csv` |
| File JSON ngôn ngữ bất kỳ (`en.json`, `locale/*.json`) | `json` | dùng `--adapter json --include ...` |

Kèm theo **plugin runtime `vntrans/assets/VietTranslate.js`** cho RPG Maker: đổi sang font có dấu tiếng Việt và dịch chữ lúc chạy game.

---

## Dùng bản có giao diện: VietHoaGame.exe (khuyên dùng)

1. Mở **VietHoaGame.exe**.
2. Chọn game trong danh sách **Game trên Steam**, hoặc bấm **Chọn thư mục game...** rồi trỏ tới thư mục có file `.exe` của game.
   Dòng *Engine* cho biết game có được hỗ trợ không.
3. Dán **Claude API key** (lần đầu; bấm *Lấy API key* để tạo). Lần sau ứng dụng tự nhớ.
   Muốn thử trước mà không tốn tiền: tích **Chạy thử miễn phí**, chữ trong game sẽ có `[VI]` phía trước.
4. Bấm **▶ VIỆT HOÁ** → ứng dụng báo số câu và chi phí ước tính → bấm *Yes* → đợi đến khi hiện **"Việt hoá xong!"**.
5. Bấm **Chơi game**, hoặc mở game từ Steam như bình thường.

| Engine | Kết quả trong game |
|---|---|
| RPG Maker MV / MZ | Hiện thẳng tiếng Việt, đã có font tiếng Việt và tự xuống dòng khi câu dài. |
| Ren'Py | Hiện tiếng Việt. Nhấn **F8** trong game để chuyển qua lại giữa tiếng Việt và bản gốc. Lần đầu ứng dụng sẽ tự mở game vài giây để quét kịch bản. Chữ giao diện (menu, nút) chưa dịch sẽ được ghi lại khi bạn chơi; bấm *Việt hoá* lần nữa để dịch nốt. |
| Unity (Mono) | Ứng dụng tự cài BepInEx + XUnity.AutoTranslator (cần mạng), sau đó **dịch trực tiếp khi chơi**: chữ hiện lên tới đâu dịch tới đó. **Giữ cửa sổ ứng dụng mở trong lúc chơi.** Câu đã dịch được lưu lại, lần sau hiện ngay. Trong game: Alt+T bật/tắt bản dịch. |
| Unity IL2CPP, RPG Maker XP/VX Ace, Godot .pck, KiriKiri, GameMaker | Chưa hỗ trợ tự động. |

- **Dừng giữa chừng:** bấm *Dừng*. Phần đã dịch vẫn được ghi vào game; bấm *Việt hoá* lần nữa để dịch tiếp, không mất phí cho câu đã dịch.
- **Gỡ Việt hoá:** bấm *Khôi phục bản gốc*. Bản dịch vẫn được giữ trong thư mục `vntrans_vi` của game, nên Việt hoá lại sẽ không tốn phí.
- **Khi Steam cập nhật game:** file game có thể bị ghi đè về tiếng gốc. Chỉ cần bấm *Việt hoá* lại, câu cũ không phải dịch lại.
- Nếu Steam báo lỗi file hoặc tự tải lại file gốc ("Verify integrity"), hãy Việt hoá lại sau khi Steam tải xong.

### Tạo file VietHoaGame.exe

Mã nguồn được viết bằng Python, cần build một lần trên Windows:

- **Cách 1 (trên máy bạn):** cài Python từ python.org (tích *Add python.exe to PATH*), rồi bấm đúp **`build_exe.bat`**. File sẽ nằm ở `dist\VietHoaGame.exe`.
- **Cách 2 (GitHub, không cần cài gì):** đưa thư mục này lên một repository GitHub → tab *Actions* → *Build VietHoaGame.exe* → *Run workflow*. Khi chạy xong, tải file trong mục *Artifacts*.

Chạy không giao diện: `VietHoaGame.exe --auto "D:\Games\MyGame"` (thêm `--dry` để chạy thử, `--restore` để gỡ).

---

## Dùng bằng dòng lệnh (cho người làm Việt hoá)

### Cài đặt

Cần Python 3.9+.

```bash
cd vntrans
pip install -e ".[claude]"
```

Muốn dịch máy bằng Claude thì đặt API key (lấy ở https://platform.claude.com):

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

(Windows PowerShell: `$env:ANTHROPIC_API_KEY="sk-ant-..."`). Không cài cũng được: dùng `python -m vntrans` thay cho `vntrans`.

## Quy trình 4 bước

**Luôn sao lưu game trước khi Việt hoá.**

```bash
# 1. Quét game, tạo project.json chứa mọi câu cần dịch
vntrans extract "D:/Games/MyGame"

# 2. Dịch thử 20 câu để xem chất lượng
vntrans translate --limit 20 --context "RPG fantasy, nhân vật chính là thiếu niên 16 tuổi, giọng hài hước" --glossary glossary.csv

# 3. Dịch hết (dừng giữa chừng không sao — chạy lại sẽ dịch tiếp)
vntrans translate --context "..." --glossary glossary.csv

# 4. Ghi ra bản game đã Việt hoá
vntrans apply -o "D:/Games/MyGame_VI" --copy-all
```

Lệnh khác:

| Lệnh | Tác dụng |
|---|---|
| `vntrans stats` | Xem tiến độ |
| `vntrans check --max-line 50` | Tìm câu mất mã điều khiển / dòng quá dài, đánh dấu `review` |
| `vntrans export-csv -o bang.csv` | Xuất bảng mở bằng Excel / Google Sheets để dịch hoặc sửa tay (cột `vietnamese`) |
| `vntrans import-csv bang.csv` | Nhập lại bảng đã sửa (câu sửa tay có `status=ok`, sẽ không bị dịch máy đè lên) |
| `vntrans export-dict -o vi_dictionary.json` | Xuất từ điển cho plugin runtime |
| `vntrans translate --engine dummy` | Chạy thử không tốn tiền (thêm `[VI]` trước mỗi câu) — để kiểm tra game có hiển thị đúng không |
| `vntrans apply --inplace` | Ghi đè thẳng vào game (tự tạo `*.bak` của file gốc) |

Dùng nhiều dự án: `vntrans -p game2.json extract ...`

### Khi game cập nhật bản mới

Chạy lại `vntrans extract <thư mục game>` với **cùng** `project.json`: câu cũ giữ nguyên bản dịch, chỉ câu mới/thay đổi phải dịch lại.

### Bảng thuật ngữ (glossary.csv)

Giúp tên nhân vật, kỹ năng, địa danh… được dịch nhất quán. Xem `glossary.example.csv`:

```csv
source,vietnamese
Potion,Bình máu
Harold,Harold
Dark Forest,Rừng Hắc Ám
```

### Chi phí và lựa chọn model

Mặc định dùng `claude-opus-5-5` (chất lượng cao nhất cho văn phong). Có thể đổi: `--model claude-sonnet-5-5` (rẻ hơn) hoặc `--model claude-haiku-5-5` (rẻ nhất, hợp với game nhiều chữ UI). `--effort low|medium|high` điều chỉnh độ kỹ. Mỗi câu giống nhau chỉ dịch một lần. Dùng `vntrans stats` (mục `untranslated_chars`) để ước lượng khối lượng trước khi dịch.

---

## Hướng dẫn riêng từng engine

### RPG Maker MV / MZ

```bash
vntrans extract "MyGame"              # MV: tự tìm www/data ; MZ: data
vntrans translate --context "..."
vntrans apply -o MyGame_VI --wrap 45  # --wrap: tự xuống dòng khi dài hơn 45 ký tự
```

- Đã dịch: thoại (Show Text, Scroll Text — gom cả khung thoại để dịch có ngữ cảnh), tên người nói (MZ), lựa chọn, tên/mô tả nhân vật, vật phẩm, vũ khí, giáp, kỹ năng, trạng thái, kẻ địch, tên bản đồ, toàn bộ thuật ngữ trong System.json.
- Khung thoại dài quá 4 dòng: game tự sang trang mới, không mất chữ.
- Nếu game bị **mã hoá** (`.rpgmvp`, `.rgss3a`, `www/data` không có file `.json`…) thì cần giải mã trước bằng công cụ phù hợp.
- Một số plugin so sánh theo **tên** (vd. tên vật phẩm) — nếu lỗi, sửa câu đó về tên gốc trong CSV.

**Font tiếng Việt + plugin runtime**

Font gốc của game Nhật/Trung thường thiếu chữ có dấu (ạ, ặ, ữ…) → hiển thị ô vuông. Cách sửa:

1. Tải font hỗ trợ tiếng Việt (vd. *Be Vietnam Pro*, *Noto Sans*, *Roboto* từ Google Fonts), chép file `.ttf` vào `fonts/` (MV: `www/fonts/`).
2. Chép `vntrans/assets/VietTranslate.js` vào `js/plugins/` (MV: `www/js/plugins/`).
3. Bật plugin, đặt **cuối danh sách**, điền `FontFile` = tên file font. Nếu không có RPG Maker editor, thêm vào cuối mảng trong `js/plugins.js`:
   ```js
   {"name":"VietTranslate","status":true,"description":"","parameters":{"DictionaryFile":"vi_dictionary.json","FontFile":"BeVietnamPro-Regular.ttf","FontSize":"0","TranslateDrawText":"true"}}
   ```
4. (Tuỳ chọn) `vntrans export-dict -o MyGame_VI/www/data/vi_dictionary.json` — plugin sẽ dịch cả chữ nằm trong plugin khác mà `apply` không ghi tới. Không dùng thì để trống `DictionaryFile`.

### Ren'Py

1. Mở Ren'Py Launcher (SDK) → chọn game → **Generate Translations** → Language: `vietnamese` → Generate. (Game đã đóng gói `.rpa`: giải nén trước bằng unrpa; `.rpyc` thì dịch ngược bằng unrpyc.)
2. Chạy:
   ```bash
   vntrans extract MyGame --renpy-lang vietnamese
   vntrans translate --context "..."
   vntrans apply --inplace
   ```
3. Font: tạo file `game/tl/vietnamese/font.rpy`:
   ```renpy
   translate vietnamese python:
       gui.text_font = "BeVietnamPro-Regular.ttf"
       gui.name_text_font = "BeVietnamPro-Regular.ttf"
       gui.interface_text_font = "BeVietnamPro-Regular.ttf"
   ```
   và chép file font vào `game/`.
4. Chọn ngôn ngữ trong Preferences của game, hoặc thêm `define config.default_language = "vietnamese"`.

### Unity (XUnity.AutoTranslator)

Unity biên dịch chữ vào file asset nên cách dễ nhất là dùng mod **BepInEx + XUnity.AutoTranslator**:

1. Cài BepInEx và XUnity.AutoTranslator vào game. Trong `BepInEx/config/AutoTranslatorConfig.ini` đặt `Language=vi` (và `FromLanguage=` ngôn ngữ gốc).
2. Chơi game một lượt để XUnity ghi chữ gặp được vào `BepInEx/Translation/vi/Text/_AutoGeneratedTranslations.txt` (hoặc tự tạo file dạng `Câu gốc=` mỗi dòng một câu).
3. ```bash
   vntrans extract MyUnityGame               # lấy các dòng chưa có bản dịch / bản dịch trùng câu gốc
   vntrans translate --context "..."
   vntrans apply --inplace
   ```
   Thêm `--retranslate` khi extract để dịch lại cả các dòng XUnity đã dịch máy trước đó.
4. Font: trong `AutoTranslatorConfig.ini` đặt `OverrideFont=Arial` (hoặc font hệ thống có tiếng Việt).

Nếu game Unity tự có file ngôn ngữ (CSV/JSON/.po trong `StreamingAssets`), dùng adapter `csv`/`json`/`po` bên dưới.

### Godot / gettext .po

```bash
cp en.po vi.po                    # hoặc tạo từ .pot
vntrans extract MyGame --include "locale/vi.po"
vntrans translate && vntrans apply --inplace
```

Godot CSV (`keys,en,ja`):

```bash
vntrans extract MyGame --adapter csv --include "translations/*.csv" --src-col en --dst-col vi
vntrans translate && vntrans apply --inplace
```

Rồi thêm `vi` vào Project Settings → Localization (cần mã nguồn dự án hoặc file `.translation` đã import).

### File JSON ngôn ngữ chung

```bash
cp lang/en.json lang/vi.json
vntrans extract MyGame --adapter json --include "lang/vi.json"
# chỉ dịch một số khoá:  --json-keys "text,name,description"
vntrans translate && vntrans apply --inplace
```

---

## Thêm hỗ trợ engine mới

Tạo file trong `vntrans/adapters/`, kế thừa `Adapter` với 3 hàm `match`, `extract`, `apply` (xem `xunity.py` — ví dụ ngắn nhất), rồi đăng ký trong `vntrans/adapters/__init__.py`.

## Kiểm thử

```bash
python -m unittest discover -s tests
```

## Lưu ý

Chỉ Việt hoá game bạn sở hữu hợp pháp; khi phát hành bản Việt hoá, nên phát hành dạng bản vá (chỉ các file đã dịch) và tôn trọng điều khoản của nhà phát triển.
